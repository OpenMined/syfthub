package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/wailsapp/wails/v2/pkg/runtime"
	_ "modernc.org/sqlite" // pure-Go SQLite driver, registered as "sqlite"
)

// ManualReviewEntry is one row of an endpoint's manual_reviews table, decoded
// for display. The table is created and populated by the Python
// ManualReviewPolicy (policy_manager): when that policy holds a request, it
// records the real request/response here and hands the caller a placeholder.
//
// The host owns this database file, so the desktop app reads it directly —
// the policy's own docstring sanctions external readers ("Any external process
// with access to the same database file can poll the table").
type ManualReviewEntry struct {
	// ReviewID is the 12-hex identifier the caller was given in the placeholder.
	ReviewID string `json:"reviewId"`
	// PolicyName is the manual_review policy instance that held the request.
	PolicyName string `json:"policyName"`
	// UserID identifies whoever made the held request.
	UserID string `json:"userId"`
	// Status is "pending", "approved", or "rejected".
	Status string `json:"status"`
	// RejectReason is populated only for rejected entries.
	RejectReason string `json:"rejectReason,omitempty"`
	// CreatedAt is the ISO-8601 UTC time the request was held.
	CreatedAt string `json:"createdAt"`
	// ResolvedAt is the ISO-8601 UTC time the entry was approved/rejected.
	ResolvedAt string `json:"resolvedAt,omitempty"`

	// RequestType is the endpoint type recorded on the held request
	// ("model", "data_source", ...).
	RequestType string `json:"requestType,omitempty"`
	// RequestText is the decoded prompt: the query string, or the joined
	// message contents when the request carried a chat transcript.
	RequestText string `json:"requestText,omitempty"`
	// RequestMessages is the chat transcript when the held request carried one.
	RequestMessages []ChatMessage `json:"requestMessages,omitempty"`

	// ResponseText is the decoded held response — the real handler output the
	// caller never received (they got the placeholder instead).
	ResponseText string `json:"responseText,omitempty"`
}

// maxManualReviewRows caps a single fetch so a long-running endpoint with a
// large backlog cannot exhaust memory. Newest entries are returned first.
const maxManualReviewRows = 500

// Manual review statuses, mirroring the values ManualReviewPolicy writes to
// the status column.
const (
	reviewStatusPending  = "pending"
	reviewStatusApproved = "approved"
	reviewStatusRejected = "rejected"
)

// reviewStoreDBPath is the SQLite file ManualReviewPolicy writes to — the
// endpoint's shared policy store, reused because the policy is configured
// without an explicit db_path.
func reviewStoreDBPath(endpointsPath, slug string) string {
	return filepath.Join(endpointsPath, slug, "policy", "store.db")
}

// GetManualReviews returns the manual-review records held for an endpoint.
//
// statusFilter accepts "" / "all" (everything), "pending" (unresolved only),
// "approved", or "rejected". The result is ordered newest-first.
//
// A missing store database or missing manual_reviews table is not an error —
// it simply means the endpoint has never held a request — so an empty slice
// is returned in those cases.
func (a *App) GetManualReviews(slug, statusFilter string) ([]ManualReviewEntry, error) {
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
	config, err := a.getConfig()
	if err != nil {
		return nil, err
	}

	// busy_timeout lets this read coexist with the short-lived policy-runner
	// subprocess, which holds the same WAL-mode database open while writing.
	// mode=ro means a missing database fails the table check below (returning
	// an empty list) rather than being created.
	dbPath := reviewStoreDBPath(config.EndpointsPath, slug)
	db, err := sql.Open("sqlite", "file:"+dbPath+"?_pragma=busy_timeout(5000)&mode=ro")
	if err != nil {
		return nil, fmt.Errorf("failed to open review database: %w", err)
	}
	defer db.Close()

	if !manualReviewsTableExists(db) {
		return []ManualReviewEntry{}, nil
	}

	query, args := manualReviewQuery(statusFilter)
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query manual reviews: %w", err)
	}
	defer rows.Close()

	entries := make([]ManualReviewEntry, 0)
	for rows.Next() {
		entry, err := scanManualReviewRow(rows)
		if err != nil {
			// ctx is nil under unit tests; the Wails logger needs a real one.
			if a.ctx != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("GetManualReviews: skipping unreadable row: %v", err))
			}
			continue
		}
		entries = append(entries, entry)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("failed to read manual reviews: %w", err)
	}

	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf("GetManualReviews: %s (filter=%q) returned %d entries", slug, statusFilter, len(entries)))
	}
	return entries, nil
}

// ApproveManualReview marks a held request as approved. Per the current scope
// this only updates the row's status in the database — the held response is
// not delivered and nothing else happens.
func (a *App) ApproveManualReview(slug, reviewID string) error {
	return a.resolveManualReview(slug, reviewID, reviewStatusApproved, "")
}

// RejectManualReview marks a held request as rejected, recording an optional
// reason. Per the current scope this only updates the row's status.
func (a *App) RejectManualReview(slug, reviewID, reason string) error {
	return a.resolveManualReview(slug, reviewID, reviewStatusRejected, reason)
}

// resolveManualReview flips one manual_reviews row to a terminal status. The
// UPDATE mirrors ManualReviewPolicy._resolve in policy_manager: status and
// resolved_at are set, pending is cleared, and reject_reason is stored only
// for rejections — so a row resolved here is indistinguishable from one
// resolved by the policy's own approve()/reject() helpers.
func (a *App) resolveManualReview(slug, reviewID, status, reason string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
	if reviewID == "" {
		return fmt.Errorf("review id is required")
	}
	config, err := a.getConfig()
	if err != nil {
		return err
	}

	dbPath := reviewStoreDBPath(config.EndpointsPath, slug)
	if _, err := os.Stat(dbPath); err != nil {
		return fmt.Errorf("no manual review database for endpoint %q", slug)
	}

	// Read-write open (no mode=ro) — this issues an UPDATE. busy_timeout lets
	// the write wait out the policy-runner subprocess when it holds the lock.
	db, err := sql.Open("sqlite", "file:"+dbPath+"?_pragma=busy_timeout(5000)")
	if err != nil {
		return fmt.Errorf("failed to open review database: %w", err)
	}
	defer db.Close()

	if !manualReviewsTableExists(db) {
		return fmt.Errorf("no manual reviews recorded for endpoint %q", slug)
	}

	// reject_reason is recorded only for rejections; approvals leave it NULL.
	var rejectReason any
	if status == reviewStatusRejected {
		rejectReason = reason
	}

	// ISO-8601 UTC with microseconds and a +00:00 offset — the same shape
	// Python's datetime.now(UTC).isoformat() writes for created_at.
	resolvedAt := time.Now().UTC().Format("2006-01-02T15:04:05.000000-07:00")

	res, err := db.Exec(
		`UPDATE manual_reviews
		 SET status = ?, pending = 0, reject_reason = ?, resolved_at = ?
		 WHERE review_id = ?`,
		status, rejectReason, resolvedAt, reviewID,
	)
	if err != nil {
		return fmt.Errorf("failed to update review: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to confirm review update: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("review %q not found", reviewID)
	}

	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf("resolveManualReview: %s %s -> %s", slug, reviewID, status))
	}
	return nil
}

// manualReviewsTableExists reports whether the manual_reviews table is present.
// ManualReviewPolicy creates it lazily on the first held request, so a store
// database can exist without it.
func manualReviewsTableExists(db *sql.DB) bool {
	var name string
	err := db.QueryRow(
		"SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'manual_reviews'",
	).Scan(&name)
	return err == nil
}

// manualReviewQuery builds the SELECT and its arguments for the given filter.
func manualReviewQuery(statusFilter string) (string, []any) {
	const cols = `review_id, policy_name, user_id, input, output,
		status, reject_reason, created_at, resolved_at`
	base := "SELECT " + cols + " FROM manual_reviews"
	order := fmt.Sprintf(" ORDER BY created_at DESC LIMIT %d", maxManualReviewRows)

	switch statusFilter {
	case reviewStatusPending:
		return base + " WHERE pending = 1" + order, nil
	case reviewStatusApproved, reviewStatusRejected:
		return base + " WHERE status = ?" + order, []any{statusFilter}
	default: // "", "all", or anything unrecognized
		return base + order, nil
	}
}

// scanManualReviewRow reads one row into a decoded ManualReviewEntry.
func scanManualReviewRow(rows *sql.Rows) (ManualReviewEntry, error) {
	var (
		entry        ManualReviewEntry
		userID       sql.NullString
		input        sql.NullString
		output       sql.NullString
		rejectReason sql.NullString
		resolvedAt   sql.NullString
	)
	if err := rows.Scan(
		&entry.ReviewID, &entry.PolicyName, &userID, &input, &output,
		&entry.Status, &rejectReason, &entry.CreatedAt, &resolvedAt,
	); err != nil {
		return ManualReviewEntry{}, err
	}

	entry.UserID = userID.String
	entry.RejectReason = rejectReason.String
	entry.ResolvedAt = resolvedAt.String

	entry.RequestType, entry.RequestText, entry.RequestMessages = decodeReviewInput(input.String)
	entry.ResponseText = decodeReviewOutput(output.String)
	return entry, nil
}

// decodeReviewInput unpacks the stored request payload into a human-readable
// form. ManualReviewPolicy records the runner's input dict, shaped as
// {"type": ..., "query": ..., "messages": [{"role","content"}, ...]}.
func decodeReviewInput(raw string) (reqType, text string, messages []ChatMessage) {
	if raw == "" {
		return "", "", nil
	}
	var in struct {
		Type     string        `json:"type"`
		Query    string        `json:"query"`
		Messages []ChatMessage `json:"messages"`
	}
	if err := json.Unmarshal([]byte(raw), &in); err != nil {
		// Not the expected shape — surface the raw payload rather than nothing.
		return "", raw, nil
	}

	switch {
	case in.Query != "":
		text = in.Query
	case len(in.Messages) > 0:
		for i, m := range in.Messages {
			if i > 0 {
				text += "\n"
			}
			text += m.Content
		}
	}
	return in.Type, text, in.Messages
}

// decodeReviewOutput unpacks the stored handler output — the held response —
// into readable text. The executor coerces every handler result into a dict,
// so the payload is a JSON object; the real content sits under a conventional
// key ("response" for model/agent endpoints, "result" otherwise).
func decodeReviewOutput(raw string) string {
	if raw == "" {
		return ""
	}
	var obj map[string]any
	if err := json.Unmarshal([]byte(raw), &obj); err != nil {
		return raw // not an object — show verbatim
	}
	for _, key := range []string{"response", "result", "content", "text", "answer"} {
		v, ok := obj[key]
		if !ok {
			continue
		}
		if s, isStr := v.(string); isStr {
			return s
		}
		// Structured payload (e.g. a data_source document list) — pretty-print.
		if b, err := json.MarshalIndent(v, "", "  "); err == nil {
			return string(b)
		}
	}
	// No conventional key — fall back to the whole object.
	if b, err := json.MarshalIndent(obj, "", "  "); err == nil {
		return string(b)
	}
	return raw
}
