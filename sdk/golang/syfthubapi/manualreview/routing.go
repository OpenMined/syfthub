package manualreview

// Routing is the per-review record that lets the host deliver a resolution
// back to the original caller long after the v2 agent session has ended.
//
// One row is written by AgentExecutor at the moment a pending manual_review
// notice is surfaced (capture point), and read+updated by the host when the
// owner resolves the review (delivery point). The row lives in the same
// SQLite file as the policy's manual_reviews table — see syfthub-desktop
// for the on-disk schema.
type Routing struct {
	ReviewID         string // 12-hex; joins manual_reviews(review_id)
	CallerUsername   string
	CallerPubkeyB64  string // X25519 identity pubkey, base64url
	InboxSubject     string // syfthub.inbox.<caller>.review
	SessionID        string // the v2 session in which the hold occurred
	PeerChannel      string // best-effort live-injection hint
	CapturedAt       string // ISO-8601 UTC microseconds
	DeliveredAt      string // empty until first successful publish
	DeliveryAttempts int
	LastAttemptAt    string
	LastError        string
}

// RoutingRecorder is the durable store of Routing rows. The concrete
// implementation lives outside the SDK so consumers can choose their SQLite
// driver (the SDK itself takes no database/sql dependency) — see
// syfthub-desktop/review_routing.go for the modernc.org/sqlite version.
//
// All methods MUST be safe for concurrent use. The capture point
// (AgentExecutor) and the delivery point (the desktop App) may both call
// concurrently for the same review_id; Record is idempotent on review_id and
// the update methods are last-writer-wins on the timestamp/attempt columns.
type RoutingRecorder interface {
	// Record captures a new routing row. Idempotent on ReviewID — a second
	// call with the same ReviewID is a no-op so a re-emitted pending notice
	// does not overwrite the original capture context.
	Record(r Routing) error

	// Load returns the row for a review_id, or (nil, nil) when no row exists
	// (Phase 1 legacy holds, or auto-approved rows that were never held).
	Load(reviewID string) (*Routing, error)

	// MarkDelivered records a successful publish. Idempotent — re-marking an
	// already-delivered row is fine; the second timestamp is ignored.
	MarkDelivered(reviewID, deliveredAt string) error

	// RecordAttempt bumps delivery_attempts, updates last_attempt_at, and
	// stores the most recent error message. Called on transient publish
	// failures; the row stays undelivered until a later success.
	RecordAttempt(reviewID, attemptedAt, errMsg string) error

	// ListUndelivered returns all rows for which a resolution has been
	// computed (manual_reviews.status != "pending") but no successful
	// publish has been recorded yet. Used by the host startup reconcile.
	ListUndelivered() ([]Routing, error)

	// Close releases the underlying handle.
	Close() error
}

// RoutingRecorderFactory builds a RoutingRecorder for one endpoint, given the
// full path of the SQLite store file the policy writes to (i.e. the same path
// ManualReviewPolicy uses for manual_reviews).
//
// The file-mode provider calls this once per file-based agent endpoint that
// has policies configured. A nil factory disables routing capture — the
// AgentExecutor still surfaces pending notices, but the resolution can only
// be delivered via the legacy "user marks manually" path.
type RoutingRecorderFactory func(storeDBPath string) (RoutingRecorder, error)
