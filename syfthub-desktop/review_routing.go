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
	"errors"
	"fmt"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"

	_ "modernc.org/sqlite" // pure-Go SQLite driver, registered as "sqlite"
)

// ErrShuttingDown is returned by sentReviewsDB / routingDB after closeAllDBs
// has run. It lets late goroutines (e.g. a publishResolution fire-and-forget
// kicked off just before shutdown) see a definite signal rather than racing a
// half-closed pool.
var ErrShuttingDown = errors.New("manual-review db caches are closed")

// sqliteHandle is one entry in the App.routingDBs cache. The once + err pair
// follows the standard "open lazily under a mutex-protected map, then run the
// expensive Open exactly once" pattern: callers grab the *sqliteHandle inside
// dbMu, drop the lock, then call once.Do — so two concurrent first-callers
// for the same path can't race on the Open.
type sqliteHandle struct {
	db   *sql.DB
	once sync.Once
	err  error
	path string
}

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
//
// ownsDB controls whether Close() releases the underlying *sql.DB. The
// App-cached path (newRoutingRecorderFromDB) wraps a pool the App owns and
// sets ownsDB=false so the SDK calling Close() on reload / shutdown does
// not invalidate the App's cache. The legacy openRoutingRecorder path keeps
// ownsDB=true for backward-compatible standalone usage (tests).
type sqliteRoutingRecorder struct {
	mu      sync.Mutex // serializes Close vs in-flight queries
	closed  bool
	db      *sql.DB
	path    string
	ownsDB  bool
}

// openRoutingDB opens (creating if absent) the routing tables inside the
// endpoint's policy store database. WAL + busy_timeout let this writer
// coexist with the policy-runner subprocess that also touches the file.
//
// This is the bottom half of the original openRoutingRecorder: it does the
// raw sql.Open + DDL but returns the *sql.DB rather than wrapping it. Used
// by the App cache so a single pool is shared across recorder instances.
func openRoutingDB(storeDBPath string) (*sql.DB, error) {
	dsn := "file:" + storeDBPath + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open routing db %q: %w", storeDBPath, err)
	}
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(2)
	if _, err := db.Exec(routingCreateTable); err != nil {
		db.Close()
		return nil, fmt.Errorf("create routing table: %w", err)
	}
	if _, err := db.Exec(routingCreateIndex); err != nil {
		db.Close()
		return nil, fmt.Errorf("create routing index: %w", err)
	}
	return db, nil
}

// newRoutingRecorderFromDB wraps a cached *sql.DB in a RoutingRecorder whose
// Close is a no-op. The pool's lifetime is owned by App.closeAllDBs, not by
// the SDK's per-endpoint Close calls.
func newRoutingRecorderFromDB(db *sql.DB, path string) *sqliteRoutingRecorder {
	return &sqliteRoutingRecorder{db: db, path: path, ownsDB: false}
}

// openRoutingRecorder is the legacy standalone constructor: opens its own
// *sql.DB and owns its lifetime. Kept for tests (review_routing_test.go) that
// exercise the recorder directly without an App. Production code goes through
// App.routingRecorder which uses the cached pool.
func openRoutingRecorder(storeDBPath string) (manualreview.RoutingRecorder, error) {
	db, err := openRoutingDB(storeDBPath)
	if err != nil {
		return nil, err
	}
	return &sqliteRoutingRecorder{db: db, path: storeDBPath, ownsDB: true}, nil
}

// routingDB returns the App-cached *sql.DB for the given absolute store path,
// opening it lazily on first use. Safe for concurrent callers across paths
// (dbMu protects the map; the per-handle once protects the open).
func (a *App) routingDB(path string) (*sql.DB, error) {
	a.dbMu.Lock()
	if a.routingDBsClosed {
		a.dbMu.Unlock()
		return nil, ErrShuttingDown
	}
	if a.routingDBs == nil {
		// Tests that construct &App{} directly skip NewApp. Lazy-init here
		// so the cache works regardless of how the App was built.
		a.routingDBs = make(map[string]*sqliteHandle)
	}
	h, ok := a.routingDBs[path]
	if !ok {
		h = &sqliteHandle{path: path}
		a.routingDBs[path] = h
	}
	a.dbMu.Unlock()

	h.once.Do(func() {
		h.db, h.err = openRoutingDB(path)
	})
	if h.err != nil {
		return nil, h.err
	}
	return h.db, nil
}

// routingRecorder returns a RoutingRecorder backed by the cached pool. The
// returned recorder's Close is a no-op — the underlying pool is owned by the
// App and closed only at shutdown.
func (a *App) routingRecorder(path string) (manualreview.RoutingRecorder, error) {
	db, err := a.routingDB(path)
	if err != nil {
		return nil, err
	}
	return newRoutingRecorderFromDB(db, path), nil
}

// newRoutingRecorderFactory adapts the App-scoped routingRecorder helper to
// the SDK's factory signature. The SDK will call Close() on the returned
// recorders during reload / shutdown — the no-op Close keeps the App's
// cached pool alive across those events.
func (a *App) newRoutingRecorderFactory() manualreview.RoutingRecorderFactory {
	return func(storeDBPath string) (manualreview.RoutingRecorder, error) {
		return a.routingRecorder(storeDBPath)
	}
}

// closeIdentityScopedDBs closes every entry in routingDBs and clears the map.
// MUST be called only after the listener and publisher are torn down so no
// goroutine is still mid-query against a pool. Does NOT close
// sentReviewsCache — the ledger is identity-fenced by the identity column,
// so the same pool serves successive logins safely.
func (a *App) closeIdentityScopedDBs() {
	a.dbMu.Lock()
	dbs := a.routingDBs
	a.routingDBs = make(map[string]*sqliteHandle)
	a.dbMu.Unlock()

	for _, h := range dbs {
		// once.Do ensures h.db is the result of openRoutingDB if it
		// succeeded, nil otherwise.
		if h.db != nil {
			_ = h.db.Close()
		}
	}
}

// closeAllDBs closes both caches and marks them shut. After this returns,
// every routingDB / sentReviewsDB call returns ErrShuttingDown. Idempotent.
func (a *App) closeAllDBs() {
	a.dbMu.Lock()
	if a.routingDBsClosed {
		a.dbMu.Unlock()
		return
	}
	a.routingDBsClosed = true
	dbs := a.routingDBs
	a.routingDBs = nil
	sentCache := a.sentReviewsCache
	a.sentReviewsCache = nil
	a.dbMu.Unlock()

	for _, h := range dbs {
		if h.db != nil {
			_ = h.db.Close()
		}
	}
	if sentCache != nil && sentCache.db != nil {
		_ = sentCache.db.Close()
	}
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

// routingColumns is the canonical SELECT projection used by Load and
// ListUndelivered. Kept in step with scanRoutingRow below.
const routingColumns = `review_id, caller_username, caller_pubkey_b64, inbox_subject,
	        session_id, peer_channel, captured_at, delivered_at,
	        delivery_attempts, last_attempt_at, last_error`

// rowScanner matches both *sql.Row and *sql.Rows so a single decoder can
// drive QueryRow and Query call sites without per-site NullString plumbing.
type rowScanner interface {
	Scan(dest ...any) error
}

func scanRoutingRow(s rowScanner) (manualreview.Routing, error) {
	var (
		row         manualreview.Routing
		sessionID   sql.NullString
		peerChannel sql.NullString
		deliveredAt sql.NullString
		lastAttempt sql.NullString
		lastError   sql.NullString
	)
	if err := s.Scan(
		&row.ReviewID, &row.CallerUsername, &row.CallerPubkeyB64, &row.InboxSubject,
		&sessionID, &peerChannel, &row.CapturedAt, &deliveredAt,
		&row.DeliveryAttempts, &lastAttempt, &lastError,
	); err != nil {
		return manualreview.Routing{}, err
	}
	row.SessionID = sessionID.String
	row.PeerChannel = peerChannel.String
	row.DeliveredAt = deliveredAt.String
	row.LastAttemptAt = lastAttempt.String
	row.LastError = lastError.String
	return row, nil
}

func (r *sqliteRoutingRecorder) Load(reviewID string) (*manualreview.Routing, error) {
	row, err := scanRoutingRow(r.db.QueryRow(
		`SELECT `+routingColumns+`
		   FROM manual_review_routing
		  WHERE review_id = ?`,
		reviewID,
	))
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("load routing %s: %w", reviewID, err)
	}
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
		`SELECT ` + routingColumns + `
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
		row, err := scanRoutingRow(rows)
		if err != nil {
			return nil, fmt.Errorf("scan undelivered: %w", err)
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

// Close releases the underlying *sql.DB only when this recorder owns it.
// App-cached recorders (newRoutingRecorderFromDB) share the App pool and
// must not close it from per-endpoint reload/shutdown calls — the App
// owns the pool's lifetime via closeAllDBs.
func (r *sqliteRoutingRecorder) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closed {
		return nil
	}
	r.closed = true
	if !r.ownsDB {
		return nil
	}
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
