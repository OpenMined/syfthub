package main

// Client-side manual-review ledger.
//
// When a chat user sends a turn to an agent protected by a Manual Review
// policy, the host holds the real response and returns a placeholder. The
// host's own "Requests" tab (manual_review_operations.go) tracks that from the
// endpoint owner's side. This file is the mirror image: the *caller's* durable
// record of every request they submitted that is (or was) under review.
//
// The ledger is a small SQLite database the desktop app owns outright — a
// sibling of settings.json — so a held request survives app restarts and chat
// sessions. It is scoped by identity: the desktop app can be used by different
// logged-in users, and one user must never see another's submissions.

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
	"github.com/wailsapp/wails/v2/pkg/runtime"
	_ "modernc.org/sqlite" // pure-Go SQLite driver, registered as "sqlite"
)

// SentReviewInput is the payload the chat frontend supplies when it captures a
// manual-review hold (see use-agent-workflow.ts). The Go backend stamps the
// identity, owner/slug, timestamp and initial status itself — the frontend
// only forwards what it observed on the held agent.message event.
type SentReviewInput struct {
	// ReviewID is the host's 12-hex handle, taken from the policy notice's
	// review_id field (surfaced structurally by P0).
	ReviewID string `json:"reviewId"`
	// EndpointPath is the "owner/slug" of the agent the request was sent to.
	EndpointPath string `json:"endpointPath"`
	// EndpointName is the agent's display name, as shown in the chat.
	EndpointName string `json:"endpointName"`
	// EndpointType is the endpoint kind; the desktop chat only calls agents,
	// so it defaults to "agent" when empty.
	EndpointType string `json:"endpointType"`
	// PolicyName is the manual_review policy instance that held the turn.
	PolicyName string `json:"policyName"`
	// RequestMessages is what the user actually sent on the held turn — the
	// heart of "context", preserved independently of the ephemeral transcript.
	RequestMessages []ChatMessage `json:"requestMessages"`
	// Placeholder is the substitute text the caller received instead of the
	// real response.
	Placeholder string `json:"placeholder"`
}

// SentReviewEntry is one row of the client-side review ledger, decoded for
// display in the "Sent for Review" view.
type SentReviewEntry struct {
	ReviewID      string `json:"reviewId"`
	Identity      string `json:"identity"`
	EndpointPath  string `json:"endpointPath"`
	EndpointOwner string `json:"endpointOwner"`
	EndpointSlug  string `json:"endpointSlug"`
	EndpointName  string `json:"endpointName"`
	EndpointType  string `json:"endpointType"`
	PolicyName    string `json:"policyName,omitempty"`
	// RequestMessages is the held turn's messages — what the user asked.
	RequestMessages []ChatMessage `json:"requestMessages,omitempty"`
	// Placeholder is the substitute text the caller received.
	Placeholder string `json:"placeholder,omitempty"`
	// SubmittedAt is the ISO-8601 UTC time the hold was captured (client clock).
	SubmittedAt string `json:"submittedAt"`
	// Status is "pending", "approved", or "rejected".
	Status string `json:"status"`
	// StatusSource records how Status was last set: "captured" (recorded as
	// pending on the hold), "manual" (the user set it from an out-of-band
	// outcome), or "queried" (host-confirmed — Phase 2).
	StatusSource string `json:"statusSource"`
	// ResolvedAt is set when the entry left the pending state.
	ResolvedAt string `json:"resolvedAt,omitempty"`
	// RejectReason is populated only for rejected entries.
	RejectReason string `json:"rejectReason,omitempty"`
	// ResponseText is the real approved response, retrieved in Phase 2. Always
	// empty under Phase 1.
	ResponseText string `json:"responseText,omitempty"`
	// UserNote is optional free text the requester added to the entry.
	UserNote string `json:"userNote,omitempty"`
	// HostResolvedAt is the host-reported resolution timestamp, distinct
	// from ResolvedAt which records the local clock when the row entered
	// its terminal state. Same value for "queried" rows (the host's clock
	// is authoritative); empty for "captured" and "manual" rows.
	HostResolvedAt string `json:"hostResolvedAt,omitempty"`
	// DeliverySeq is the JetStream sequence number of the resolution
	// envelope that produced the current state. Used as a monotonic
	// idempotency guard — a re-delivered message with seq <= stored seq
	// must not overwrite a newer resolution. Zero until the first
	// host-delivered resolution lands.
	DeliverySeq uint64 `json:"deliverySeq,omitempty"`
}

// statusSource* records how a ledger entry's Status was last set.
const (
	statusSourceCaptured = "captured" // recorded as pending when the hold arrived
	statusSourceManual   = "manual"   // the user set it from an out-of-band outcome
	statusSourceQueried  = "queried"  // host-confirmed (reserved for Phase 2)
)

// maxSentReviewRows caps a single fetch so a heavy chat history cannot exhaust
// memory. Newest entries are returned first.
const maxSentReviewRows = 1000

// sentReviewsCreateTable / sentReviewsCreateIndex are run on every open — both
// use IF NOT EXISTS, so a fresh or already-initialized ledger is self-healing.
//
// host_resolved_at and delivery_seq were added in schema v2 (see
// sentReviewsSchemaVersion). They are part of CREATE TABLE so a brand-new
// install gets the right shape, and they are also ALTER-added in
// migrateSentReviewsSchema for installs that predate Phase 2.0.
const sentReviewsCreateTable = `CREATE TABLE IF NOT EXISTS sent_reviews (
	review_id        TEXT PRIMARY KEY,
	identity         TEXT NOT NULL,
	endpoint_path    TEXT NOT NULL,
	endpoint_owner   TEXT,
	endpoint_slug    TEXT,
	endpoint_name    TEXT,
	endpoint_type    TEXT NOT NULL DEFAULT 'agent',
	policy_name      TEXT,
	request_messages TEXT,
	placeholder      TEXT,
	submitted_at     TEXT NOT NULL,
	status           TEXT NOT NULL DEFAULT 'pending',
	status_source    TEXT NOT NULL DEFAULT 'captured',
	resolved_at      TEXT,
	reject_reason    TEXT,
	response_text    TEXT,
	user_note        TEXT,
	host_resolved_at TEXT,
	delivery_seq     INTEGER
)`

const sentReviewsCreateIndex = `CREATE INDEX IF NOT EXISTS
	idx_sent_reviews_identity ON sent_reviews (identity, status)`

// sentReviewsSchemaVersion is the on-disk schema version this code expects
// to read and write. Bumped when a column is added; migrateSentReviewsSchema
// upgrades older databases in place. Older builds opening a newer DB will
// see PRAGMA user_version > theirs and refuse — that's the contract.
const sentReviewsSchemaVersion = 2

// sentReviewCols is the column list shared by every SELECT, kept in one place
// so it stays in step with scanSentReviewRow.
const sentReviewCols = `review_id, identity, endpoint_path, endpoint_owner,
	endpoint_slug, endpoint_name, endpoint_type, policy_name, request_messages,
	placeholder, submitted_at, status, status_source, resolved_at,
	reject_reason, response_text, user_note, host_resolved_at, delivery_seq`

// sentReviewsDBFile resolves the client review ledger's SQLite path — a
// sibling of settings.json. It is a var so tests can point it at a temp dir.
var sentReviewsDBFile = func() (string, error) {
	dir, err := getSettingsDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "sent-reviews.db"), nil
}

// openSentReviewsDB opens (creating if absent) the review ledger and ensures
// its schema. busy_timeout + WAL let a frontend-triggered read coexist with a
// capture write without either failing on a momentary lock.
//
// On open we run migrateSentReviewsSchema which uses PRAGMA user_version to
// advance the DB through schema versions. A fresh install gets every column
// from the CREATE TABLE directly; an upgrade install (Phase 1 → Phase 2.0)
// picks up host_resolved_at and delivery_seq via ALTER TABLE.
func openSentReviewsDB() (*sql.DB, error) {
	path, err := sentReviewsDBFile()
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("failed to create settings directory: %w", err)
	}
	db, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)")
	if err != nil {
		return nil, fmt.Errorf("failed to open review ledger: %w", err)
	}
	if _, err := db.Exec(sentReviewsCreateTable); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to initialize review ledger: %w", err)
	}
	if _, err := db.Exec(sentReviewsCreateIndex); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to index review ledger: %w", err)
	}
	if err := migrateSentReviewsSchema(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("migrate review ledger: %w", err)
	}
	return db, nil
}

// migrateSentReviewsSchema advances the database through schema versions.
//
// The version is stored in PRAGMA user_version (a 32-bit integer baked into
// the SQLite file header). Going from version 0 (a Phase 1 install where
// the field never existed) to version 2 requires ALTER TABLE-adding the two
// columns CREATE TABLE writes for a fresh install. ALTER TABLE ADD COLUMN
// in SQLite is fast — it rewrites only the schema metadata, not the data.
//
// We skip migration entirely on a brand-new DB (version 0 with no rows
// would still need the ALTER, but CREATE TABLE already wrote the new
// columns above — checking for column existence via PRAGMA table_info is
// the safe way to decide).
func migrateSentReviewsSchema(db *sql.DB) error {
	var current int
	if err := db.QueryRow("PRAGMA user_version").Scan(&current); err != nil {
		return fmt.Errorf("read user_version: %w", err)
	}
	if current >= sentReviewsSchemaVersion {
		return nil
	}

	// Version 0 (pre-v2 install) → version 2: add host_resolved_at and
	// delivery_seq. We add columns only if they don't already exist — a DB
	// created fresh by sentReviewsCreateTable above already has them, so the
	// ALTER would error.
	hasHost, err := columnExists(db, "sent_reviews", "host_resolved_at")
	if err != nil {
		return err
	}
	if !hasHost {
		if _, err := db.Exec(`ALTER TABLE sent_reviews ADD COLUMN host_resolved_at TEXT`); err != nil {
			return fmt.Errorf("add host_resolved_at: %w", err)
		}
	}
	hasSeq, err := columnExists(db, "sent_reviews", "delivery_seq")
	if err != nil {
		return err
	}
	if !hasSeq {
		if _, err := db.Exec(`ALTER TABLE sent_reviews ADD COLUMN delivery_seq INTEGER`); err != nil {
			return fmt.Errorf("add delivery_seq: %w", err)
		}
	}

	// Stamp the version. PRAGMA user_version takes a bare integer, no params.
	if _, err := db.Exec(fmt.Sprintf("PRAGMA user_version = %d", sentReviewsSchemaVersion)); err != nil {
		return fmt.Errorf("stamp user_version: %w", err)
	}
	return nil
}

// columnExists reports whether table has a column with the given name. Uses
// PRAGMA table_info — cheap, no full-table scan.
func columnExists(db *sql.DB, table, column string) (bool, error) {
	rows, err := db.Query(fmt.Sprintf("PRAGMA table_info(%s)", table))
	if err != nil {
		return false, fmt.Errorf("table_info(%s): %w", table, err)
	}
	defer rows.Close()
	for rows.Next() {
		var (
			cid     int
			name    string
			ctype   string
			notnull int
			dflt    sql.NullString
			pk      int
		)
		if err := rows.Scan(&cid, &name, &ctype, &notnull, &dflt, &pk); err != nil {
			return false, err
		}
		if name == column {
			return true, nil
		}
	}
	return false, rows.Err()
}

// currentIdentity returns the logged-in user's username, or "" when not
// authenticated. It is the ledger's scoping key.
func (a *App) currentIdentity() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	return a.username
}

// splitEndpointPath splits an "owner/slug" path. A path with no slash is
// treated as a bare slug with no owner.
func splitEndpointPath(path string) (owner, slug string) {
	if parts := strings.SplitN(path, "/", 2); len(parts) == 2 {
		return parts[0], parts[1]
	}
	return "", path
}

// joinEndpointPath reverses splitEndpointPath. When both halves are empty it
// returns "" (rather than "/") so callers don't have to special-case it.
func joinEndpointPath(owner, slug string) string {
	if owner == "" && slug == "" {
		return ""
	}
	return owner + "/" + slug
}

// RecordSentReview durably records a manual-review hold the user just received
// in the chat. It is idempotent on review_id: a re-render or a duplicate agent
// event carrying the same id will not create a second row.
func (a *App) RecordSentReview(input SentReviewInput) error {
	if strings.TrimSpace(input.ReviewID) == "" {
		return fmt.Errorf("review id is required")
	}
	if strings.TrimSpace(input.EndpointPath) == "" {
		return fmt.Errorf("endpoint path is required")
	}
	identity := a.currentIdentity()
	if identity == "" {
		return fmt.Errorf("not authenticated — cannot record a review")
	}

	owner, slug := splitEndpointPath(input.EndpointPath)
	endpointType := input.EndpointType
	if endpointType == "" {
		endpointType = "agent"
	}
	messagesJSON, err := json.Marshal(input.RequestMessages)
	if err != nil {
		return fmt.Errorf("failed to encode request messages: %w", err)
	}
	submittedAt := time.Now().UTC().Format(manualreview.ISOMicroLayout)

	db, err := openSentReviewsDB()
	if err != nil {
		return err
	}
	defer db.Close()

	// INSERT OR IGNORE makes capture idempotent — the PRIMARY KEY on review_id
	// silently drops a duplicate rather than erroring.
	_, err = db.Exec(
		`INSERT OR IGNORE INTO sent_reviews
			(review_id, identity, endpoint_path, endpoint_owner, endpoint_slug,
			 endpoint_name, endpoint_type, policy_name, request_messages,
			 placeholder, submitted_at, status, status_source)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		input.ReviewID, identity, input.EndpointPath, owner, slug,
		input.EndpointName, endpointType, input.PolicyName, string(messagesJSON),
		input.Placeholder, submittedAt, reviewStatusPending, statusSourceCaptured,
	)
	if err != nil {
		return fmt.Errorf("failed to record review: %w", err)
	}
	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf(
			"RecordSentReview: %s (%s) for %s", input.ReviewID, input.EndpointPath, identity))
	}
	return nil
}

// GetSentReviews returns the current user's recorded reviews, newest-first.
//
// statusFilter accepts "" / "all" (everything), or "pending" / "approved" /
// "rejected". When no user is logged in an empty slice is returned — the view
// simply shows nothing rather than erroring.
func (a *App) GetSentReviews(statusFilter string) ([]SentReviewEntry, error) {
	identity := a.currentIdentity()
	if identity == "" {
		return []SentReviewEntry{}, nil
	}

	db, err := openSentReviewsDB()
	if err != nil {
		return nil, err
	}
	defer db.Close()

	query, args := sentReviewQuery(identity, statusFilter)
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query sent reviews: %w", err)
	}
	defer rows.Close()

	entries := make([]SentReviewEntry, 0)
	for rows.Next() {
		entry, err := scanSentReviewRow(rows)
		if err != nil {
			// ctx is nil under unit tests; the Wails logger needs a real one.
			if a.ctx != nil {
				runtime.LogWarning(a.ctx, fmt.Sprintf("GetSentReviews: skipping unreadable row: %v", err))
			}
			continue
		}
		entries = append(entries, entry)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("failed to read sent reviews: %w", err)
	}
	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf(
			"GetSentReviews: filter=%q returned %d entries", statusFilter, len(entries)))
	}
	return entries, nil
}

// sentReviewQuery builds the identity-scoped SELECT and its arguments.
func sentReviewQuery(identity, statusFilter string) (string, []any) {
	base := "SELECT " + sentReviewCols + " FROM sent_reviews WHERE identity = ?"
	order := fmt.Sprintf(" ORDER BY submitted_at DESC LIMIT %d", maxSentReviewRows)
	switch statusFilter {
	case reviewStatusPending, reviewStatusApproved, reviewStatusRejected:
		return base + " AND status = ?" + order, []any{identity, statusFilter}
	default: // "", "all", or anything unrecognized
		return base + order, []any{identity}
	}
}

// scanSentReviewRow reads one row into a decoded SentReviewEntry.
func scanSentReviewRow(rows *sql.Rows) (SentReviewEntry, error) {
	var (
		entry          SentReviewEntry
		policyName     sql.NullString
		messagesJSON   sql.NullString
		placeholder    sql.NullString
		resolvedAt     sql.NullString
		rejectReason   sql.NullString
		responseText   sql.NullString
		userNote       sql.NullString
		hostResolvedAt sql.NullString
		deliverySeq    sql.NullInt64
	)
	if err := rows.Scan(
		&entry.ReviewID, &entry.Identity, &entry.EndpointPath, &entry.EndpointOwner,
		&entry.EndpointSlug, &entry.EndpointName, &entry.EndpointType, &policyName,
		&messagesJSON, &placeholder, &entry.SubmittedAt, &entry.Status,
		&entry.StatusSource, &resolvedAt, &rejectReason, &responseText, &userNote,
		&hostResolvedAt, &deliverySeq,
	); err != nil {
		return SentReviewEntry{}, err
	}
	entry.PolicyName = policyName.String
	entry.Placeholder = placeholder.String
	entry.ResolvedAt = resolvedAt.String
	entry.RejectReason = rejectReason.String
	entry.ResponseText = responseText.String
	entry.UserNote = userNote.String
	entry.HostResolvedAt = hostResolvedAt.String
	if deliverySeq.Valid {
		entry.DeliverySeq = uint64(deliverySeq.Int64)
	}
	entry.RequestMessages = decodeMessagesJSON(messagesJSON.String)
	return entry, nil
}

// decodeMessagesJSON unpacks the stored request_messages JSON. A malformed or
// empty value yields nil rather than an error — a missing transcript must not
// make the whole entry unreadable.
func decodeMessagesJSON(raw string) []ChatMessage {
	if raw == "" {
		return nil
	}
	var msgs []ChatMessage
	if err := json.Unmarshal([]byte(raw), &msgs); err != nil {
		return nil
	}
	return msgs
}

// SetSentReviewStatus is the Phase 1 manual override: the user marks an entry
// approved or rejected after the host told them the outcome out of band. Such
// entries are stamped status_source = "manual" so the UI can show they were
// not system-confirmed.
//
// A host-confirmed ("queried") entry is never overwritten — once Phase 2 lands,
// an authoritative status from the host wins over a manual guess.
func (a *App) SetSentReviewStatus(reviewID, status, reason string) error {
	if reviewID == "" {
		return fmt.Errorf("review id is required")
	}
	if status != reviewStatusApproved && status != reviewStatusRejected {
		return fmt.Errorf("status must be %q or %q", reviewStatusApproved, reviewStatusRejected)
	}
	identity := a.currentIdentity()
	if identity == "" {
		return fmt.Errorf("not authenticated")
	}

	db, err := openSentReviewsDB()
	if err != nil {
		return err
	}
	defer db.Close()

	// reject_reason is recorded only for rejections; approvals clear it.
	var rejectReason any
	if status == reviewStatusRejected {
		rejectReason = reason
	}
	resolvedAt := time.Now().UTC().Format(manualreview.ISOMicroLayout)

	res, err := db.Exec(
		`UPDATE sent_reviews
		 SET status = ?, status_source = ?, resolved_at = ?, reject_reason = ?
		 WHERE review_id = ? AND identity = ? AND status_source != ?`,
		status, statusSourceManual, resolvedAt, rejectReason,
		reviewID, identity, statusSourceQueried,
	)
	if err != nil {
		return fmt.Errorf("failed to update review: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to confirm review update: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("review %q not found or already confirmed by the host", reviewID)
	}
	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf("SetSentReviewStatus: %s -> %s (manual)", reviewID, status))
	}
	return nil
}

// DeleteSentReview removes a single entry from the caller's ledger.
//
// This is a hard delete — the row is gone from sent-reviews.db with no
// tombstone. A subsequent host-delivered resolution for the same review_id
// (the host's manual_review_routing still has it, and JetStream retention
// holds the envelope) will land via ApplyHostResolution's synth-INSERT path
// and re-create a "queried" row. That's an intentional trade: tombstoning
// would complicate every sent_reviews query for a rare race; if the user
// really wants the row gone they can delete it again after the resolution
// arrives.
//
// Identity-scoped so a delete from one user's session never touches another
// user's row on a shared desktop install.
func (a *App) DeleteSentReview(reviewID string) error {
	if reviewID == "" {
		return fmt.Errorf("review id is required")
	}
	identity := a.currentIdentity()
	if identity == "" {
		return fmt.Errorf("not authenticated")
	}

	db, err := openSentReviewsDB()
	if err != nil {
		return err
	}
	defer db.Close()

	res, err := db.Exec(
		"DELETE FROM sent_reviews WHERE review_id = ? AND identity = ?",
		reviewID, identity,
	)
	if err != nil {
		return fmt.Errorf("failed to delete review: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to confirm delete: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("review %q not found", reviewID)
	}
	if a.ctx != nil {
		runtime.LogDebug(a.ctx, fmt.Sprintf("DeleteSentReview: %s", reviewID))
	}
	return nil
}

// SetSentReviewNote stores (or clears, with an empty string) the optional free
// text the requester attached to a ledger entry.
func (a *App) SetSentReviewNote(reviewID, note string) error {
	if reviewID == "" {
		return fmt.Errorf("review id is required")
	}
	identity := a.currentIdentity()
	if identity == "" {
		return fmt.Errorf("not authenticated")
	}

	db, err := openSentReviewsDB()
	if err != nil {
		return err
	}
	defer db.Close()

	res, err := db.Exec(
		"UPDATE sent_reviews SET user_note = ? WHERE review_id = ? AND identity = ?",
		note, reviewID, identity,
	)
	if err != nil {
		return fmt.Errorf("failed to save note: %w", err)
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to confirm note: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("review %q not found", reviewID)
	}
	return nil
}
