package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
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

	// The cached pool is RW (routingDB also serves the manual_review_routing
	// table). When the store.db doesn't yet exist — endpoint that has never
	// held a request — we return an empty list rather than creating an empty
	// database, preserving the previous mode=ro behaviour.
	dbPath := reviewStoreDBPath(config.EndpointsPath, slug)
	if _, err := os.Stat(dbPath); err != nil {
		if os.IsNotExist(err) {
			return []ManualReviewEntry{}, nil
		}
		return nil, fmt.Errorf("failed to stat review database: %w", err)
	}
	db, err := a.routingDB(dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open review database: %w", err)
	}

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
	return a.resolveManualReview(slug, reviewID, manualreview.StatusApproved, "")
}

// RejectManualReview marks a held request as rejected, recording an optional
// reason. Per the current scope this only updates the row's status.
func (a *App) RejectManualReview(slug, reviewID, reason string) error {
	return a.resolveManualReview(slug, reviewID, manualreview.StatusRejected, reason)
}

// resolveManualReview flips one manual_reviews row to a terminal status. The
// UPDATE mirrors ManualReviewPolicy._resolve in policy_manager: status and
// resolved_at are set, pending is cleared, and reject_reason is stored only
// for rejections — so a row resolved here is indistinguishable from one
// resolved by the policy's own approve()/reject() helpers.
//
// After a successful UPDATE we additionally fire publishResolution to deliver
// the outcome (and, on approval, the real held output) back to the caller via
// the manual-review resolution channel. The publish is best-effort: a wire
// failure does NOT roll back the local UPDATE, and the routing row is left
// undelivered for a future reconcile pass to pick up. The publish runs in a
// goroutine so the Wails Approve/Reject call doesn't block on a slow NATS
// round-trip.
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

	// Read-write — this issues an UPDATE. The cached pool already has the
	// busy_timeout + WAL pragmas applied at open time.
	db, err := a.routingDB(dbPath)
	if err != nil {
		return fmt.Errorf("failed to open review database: %w", err)
	}

	if !manualReviewsTableExists(db) {
		return fmt.Errorf("no manual reviews recorded for endpoint %q", slug)
	}

	// reject_reason is recorded only for rejections; approvals leave it NULL.
	var rejectReason any
	if status == manualreview.StatusRejected {
		rejectReason = reason
	}

	resolvedAt := manualreview.NowISO()

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

	// Deliver the resolution over the wire. Fire-and-forget — the UPDATE
	// above is the local source of truth and must not be rolled back on a
	// publish failure. Snapshot the held output BEFORE returning so the
	// goroutine can finish even after the SQLite connection here closes
	// (the goroutine opens its own).
	go a.publishResolution(slug, reviewID, status, reason, resolvedAt)

	return nil
}

// publishResolution loads the routing row + the held handler output for a
// resolved review, encrypts the payload to the caller, and publishes via
// the ReviewPublisher. Errors are logged + recorded on the routing row but
// not propagated — the local UPDATE in resolveManualReview is already
// committed by the time we run.
//
// No publisher (HTTP mode, no JetStream, app not yet set up) → quiet no-op.
// No routing row (capture failed, or pre-feature legacy hold) → quiet no-op.
func (a *App) publishResolution(slug, reviewID, status, reason, resolvedAt string) {
	a.mu.RLock()
	pub := a.reviewPublisher
	a.mu.RUnlock()
	if pub == nil {
		return
	}

	config, err := a.getConfig()
	if err != nil {
		a.logWarn("publishResolution: getConfig failed: %v", err)
		return
	}
	dbPath := reviewStoreDBPath(config.EndpointsPath, slug)

	// Look up the routing row. routingRecorder hands back a wrapper over the
	// App-cached pool; its Close is a no-op so the deferred call is safe.
	recorder, err := a.routingRecorder(dbPath)
	if err != nil {
		a.logWarn("publishResolution: open recorder: %v", err)
		return
	}
	defer recorder.Close()

	routing, err := recorder.Load(reviewID)
	if err != nil {
		a.logWarn("publishResolution: load routing %s: %v", reviewID, err)
		return
	}
	if routing == nil {
		// No routing row was ever captured (legacy hold, or recorder was
		// absent at capture time). Nothing to do; the caller's "manual"
		// override path is the only remaining channel.
		a.logDebug("publishResolution: no routing row for %s (legacy hold)", reviewID)
		return
	}
	if routing.DeliveredAt != "" {
		// Already delivered (a re-resolve or a startup-replay race) — nothing
		// to do. MarkDelivered's COALESCE keeps the original timestamp.
		return
	}

	// Snapshot the held output + policy name from manual_reviews so we can
	// hand them to the publisher. We open the same DB read-only here; the
	// recorder's connection is for the routing table only.
	heldOutput, policyName, endpointName := a.loadHeldOutput(dbPath, reviewID, slug)

	payload := manualreview.ResolvedPayload{
		ReviewID:       reviewID,
		Status:         status,
		ResolvedAt:     resolvedAt,
		ResponseText:   resolutionResponseText(status, heldOutput),
		RejectReason:   resolutionRejectReason(status, reason),
		ResolverUserID: a.currentIdentity(),
	}

	pubCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	seq, err := pub.PublishWithMeta(pubCtx, *routing, payload,
		a.currentIdentity(), slug, endpointName, policyName)
	if err != nil {
		a.logWarn("publishResolution: %s -> %s: %v", reviewID, routing.InboxSubject, err)
		if rerr := recorder.RecordAttempt(reviewID,
			manualreview.NowISO(), err.Error()); rerr != nil {
			a.logWarn("publishResolution: record attempt: %v", rerr)
		}
		return
	}
	if err := recorder.MarkDelivered(reviewID,
		manualreview.NowISO()); err != nil {
		a.logWarn("publishResolution: mark delivered: %v", err)
	}
	a.logDebug("publishResolution: delivered %s seq=%d", reviewID, seq)
}

// resolutionResponseText returns the held output as text for an approval,
// empty otherwise. Even though the payload could carry the full held output
// on rejection too, sending it would leak the real answer to a caller whose
// request was deemed unfit — that's the whole point of rejection.
func resolutionResponseText(status, heldOutput string) string {
	if status == manualreview.StatusApproved {
		return heldOutput
	}
	return ""
}

// resolutionRejectReason returns the reason for a rejection, empty otherwise.
func resolutionRejectReason(status, reason string) string {
	if status == manualreview.StatusRejected {
		return reason
	}
	return ""
}

// loadHeldOutput reads the held handler output (the real answer the caller
// never received) plus the policy_name and endpoint_name for one review_id.
// Returns empty strings on any error — best-effort so a partial DB doesn't
// block the publish.
func (a *App) loadHeldOutput(dbPath, reviewID, slug string) (heldOutput, policyName, endpointName string) {
	db, err := a.routingDB(dbPath)
	if err != nil {
		return "", "", ""
	}

	var (
		rawOutput string
		policy    string
	)
	err = db.QueryRow(
		`SELECT IFNULL(output, ''), IFNULL(policy_name, '') FROM manual_reviews WHERE review_id = ?`,
		reviewID,
	).Scan(&rawOutput, &policy)
	if err != nil {
		return "", "", ""
	}
	heldOutput = decodeReviewOutput(rawOutput)
	policyName = policy
	// endpoint_name isn't in manual_reviews; fall back to slug. The caller's
	// frontend resolves the display name from the path on its end.
	endpointName = slug
	return heldOutput, policyName, endpointName
}

// logWarn / logDebug are nil-ctx-safe wrappers around the Wails logger so
// unit tests (a.ctx == nil) can exercise these methods without panicking.
func (a *App) logWarn(format string, args ...any) {
	if a.ctx != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf(format, args...))
	}
}
func (a *App) logDebug(format string, args ...any) {
	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf(format, args...))
	}
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
	case manualreview.StatusPending:
		return base + " WHERE pending = 1" + order, nil
	case manualreview.StatusApproved, manualreview.StatusRejected:
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
