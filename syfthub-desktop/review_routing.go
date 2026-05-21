package main

// SQLite-backed implementation of manualreview.RoutingRecorder.
//
// Lives on the desktop side (not in the SDK) so the SDK takes no database/sql
// dependency. The store file is the same SQLite database the Python
// ManualReviewPolicy uses for its manual_reviews table — see
// reviewStoreDBPath in manual_review_operations.go. Both tables coexist in
// one file with WAL + busy_timeout=5000.

import (
	"database/sql"
	"fmt"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"

	_ "modernc.org/sqlite" // pure-Go SQLite driver, registered as "sqlite"
)

// routingCreateTable + routingCreateIndex are idempotent — the table is
// created lazily on first Record. Same convention ManualReviewPolicy uses.
const (
	routingCreateTable = `
CREATE TABLE IF NOT EXISTS manual_review_routing (
    review_id           TEXT PRIMARY KEY,
    caller_username     TEXT NOT NULL,
    caller_pubkey_b64   TEXT NOT NULL,
    inbox_subject       TEXT NOT NULL,
    session_id          TEXT,
    peer_channel        TEXT,
    captured_at         TEXT NOT NULL,
    delivered_at        TEXT,
    delivery_attempts   INTEGER NOT NULL DEFAULT 0,
    last_attempt_at     TEXT,
    last_error          TEXT
)`
	// Partial index: only undelivered rows; the host startup reconcile scans
	// this set so the index targets exactly that query.
	routingCreateIndex = `
CREATE INDEX IF NOT EXISTS idx_routing_undelivered
ON manual_review_routing (caller_username)
WHERE delivered_at IS NULL`
)

// sqliteRoutingRecorder is the modernc.org/sqlite-backed RoutingRecorder.
// One instance per endpoint store.db file. Methods are safe for concurrent
// use; database/sql + WAL handles the cross-goroutine locking.
type sqliteRoutingRecorder struct {
	mu     sync.Mutex // serializes Close vs in-flight queries
	closed bool
	db     *sql.DB
	path   string
}

// openRoutingRecorder opens (creating if absent) the routing table inside
// the endpoint's policy store database. WAL + busy_timeout let this writer
// coexist with the policy-runner subprocess that also touches the file.
func openRoutingRecorder(storeDBPath string) (manualreview.RoutingRecorder, error) {
	dsn := "file:" + storeDBPath + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open routing db %q: %w", storeDBPath, err)
	}
	if _, err := db.Exec(routingCreateTable); err != nil {
		db.Close()
		return nil, fmt.Errorf("create routing table: %w", err)
	}
	if _, err := db.Exec(routingCreateIndex); err != nil {
		db.Close()
		return nil, fmt.Errorf("create routing index: %w", err)
	}
	return &sqliteRoutingRecorder{db: db, path: storeDBPath}, nil
}

// newRoutingRecorderFactory adapts openRoutingRecorder to the SDK's factory
// signature.
func newRoutingRecorderFactory() manualreview.RoutingRecorderFactory {
	return openRoutingRecorder
}

func (r *sqliteRoutingRecorder) Record(row manualreview.Routing) error {
	// INSERT OR IGNORE: idempotent on review_id. A re-emitted pending notice
	// (e.g. the agent re-runs the same turn) must not overwrite the original
	// capture context — the first capture is authoritative.
	_, err := r.db.Exec(
		`INSERT OR IGNORE INTO manual_review_routing
		    (review_id, caller_username, caller_pubkey_b64, inbox_subject,
		     session_id, peer_channel, captured_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?)`,
		row.ReviewID, row.CallerUsername, row.CallerPubkeyB64, row.InboxSubject,
		nullIfEmpty(row.SessionID), nullIfEmpty(row.PeerChannel), row.CapturedAt,
	)
	if err != nil {
		return fmt.Errorf("record routing %s: %w", row.ReviewID, err)
	}
	return nil
}

func (r *sqliteRoutingRecorder) Load(reviewID string) (*manualreview.Routing, error) {
	var (
		row         manualreview.Routing
		sessionID   sql.NullString
		peerChannel sql.NullString
		deliveredAt sql.NullString
		lastAttempt sql.NullString
		lastError   sql.NullString
	)
	err := r.db.QueryRow(
		`SELECT review_id, caller_username, caller_pubkey_b64, inbox_subject,
		        session_id, peer_channel, captured_at, delivered_at,
		        delivery_attempts, last_attempt_at, last_error
		   FROM manual_review_routing
		  WHERE review_id = ?`,
		reviewID,
	).Scan(
		&row.ReviewID, &row.CallerUsername, &row.CallerPubkeyB64, &row.InboxSubject,
		&sessionID, &peerChannel, &row.CapturedAt, &deliveredAt,
		&row.DeliveryAttempts, &lastAttempt, &lastError,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("load routing %s: %w", reviewID, err)
	}
	row.SessionID = sessionID.String
	row.PeerChannel = peerChannel.String
	row.DeliveredAt = deliveredAt.String
	row.LastAttemptAt = lastAttempt.String
	row.LastError = lastError.String
	return &row, nil
}

func (r *sqliteRoutingRecorder) MarkDelivered(reviewID, deliveredAt string) error {
	// COALESCE keeps the first delivery timestamp if MarkDelivered is called
	// twice for the same review (e.g. a retry that races a previous success).
	res, err := r.db.Exec(
		`UPDATE manual_review_routing
		    SET delivered_at = COALESCE(delivered_at, ?),
		        last_error   = NULL
		  WHERE review_id = ?`,
		deliveredAt, reviewID,
	)
	if err != nil {
		return fmt.Errorf("mark delivered %s: %w", reviewID, err)
	}
	n, _ := res.RowsAffected()
	if n == 0 {
		return fmt.Errorf("routing row %s not found", reviewID)
	}
	return nil
}

func (r *sqliteRoutingRecorder) RecordAttempt(reviewID, attemptedAt, errMsg string) error {
	_, err := r.db.Exec(
		`UPDATE manual_review_routing
		    SET delivery_attempts = delivery_attempts + 1,
		        last_attempt_at   = ?,
		        last_error        = ?
		  WHERE review_id = ?`,
		attemptedAt, errMsg, reviewID,
	)
	if err != nil {
		return fmt.Errorf("record attempt %s: %w", reviewID, err)
	}
	return nil
}

func (r *sqliteRoutingRecorder) ListUndelivered() ([]manualreview.Routing, error) {
	rows, err := r.db.Query(
		`SELECT review_id, caller_username, caller_pubkey_b64, inbox_subject,
		        session_id, peer_channel, captured_at, delivered_at,
		        delivery_attempts, last_attempt_at, last_error
		   FROM manual_review_routing
		  WHERE delivered_at IS NULL
		  ORDER BY captured_at ASC`,
	)
	if err != nil {
		return nil, fmt.Errorf("list undelivered: %w", err)
	}
	defer rows.Close()

	var out []manualreview.Routing
	for rows.Next() {
		var (
			row         manualreview.Routing
			sessionID   sql.NullString
			peerChannel sql.NullString
			deliveredAt sql.NullString
			lastAttempt sql.NullString
			lastError   sql.NullString
		)
		if err := rows.Scan(
			&row.ReviewID, &row.CallerUsername, &row.CallerPubkeyB64, &row.InboxSubject,
			&sessionID, &peerChannel, &row.CapturedAt, &deliveredAt,
			&row.DeliveryAttempts, &lastAttempt, &lastError,
		); err != nil {
			return nil, fmt.Errorf("scan undelivered: %w", err)
		}
		row.SessionID = sessionID.String
		row.PeerChannel = peerChannel.String
		row.DeliveredAt = deliveredAt.String
		row.LastAttemptAt = lastAttempt.String
		row.LastError = lastError.String
		out = append(out, row)
	}
	return out, rows.Err()
}

func (r *sqliteRoutingRecorder) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closed {
		return nil
	}
	r.closed = true
	return r.db.Close()
}

// nullIfEmpty turns "" into NULL on the SQL side so an absent value stays
// distinguishable from an explicit empty one. Used by manual-review tables
// where NULL ("haven't observed") and "" ("observed empty") have different
// meaning.
func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
