package main

// Caller-side application of a host-delivered manual-review resolution.
//
// The ReviewInboxListener decodes one ResolvedEnvelope at a time from the
// durable JetStream inbox and calls ApplyHostResolution to merge its content
// into the local sent_reviews ledger. ApplyHostResolution owns three
// responsibilities the listener should not have to know about:
//
//   - Idempotency: replays and re-deliveries (NAK + redeliver, two devices on
//     the same inbox subject) must NOT regress already-applied state. The
//     delivery_seq column carries the JetStream stream sequence; an inbound
//     seq <= stored seq is a no-op.
//
//   - Resurrection on a fresh device: a desktop install that never captured
//     the original hold (RecordSentReview was never called there) still gets
//     the resolution. We INSERT a synthetic row from the envelope metadata so
//     the user has something to look at in SentReviewsView.
//
//   - Provenance: the row's status_source becomes "queried" — distinct from
//     "captured" (pending hold) and "manual" (user override). The
//     SentReviewsView already renders the three sources differently; we just
//     keep the labels in step.

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// dbExecutor is the subset of *sql.DB / *sql.Tx the helpers need. Accepting
// the interface lets applyHostResolutionTx run against either a raw DB handle
// (legacy callers / direct tests) or a transaction (the production path that
// wraps the three-step orchestration in BEGIN IMMEDIATE).
type dbExecutor interface {
	Exec(query string, args ...any) (sql.Result, error)
	QueryRow(query string, args ...any) *sql.Row
}

// HostResolutionOutcome classifies the effect on the local ledger. Callers
// that only need "did anything change?" should keep using ApplyHostResolution
// which collapses these into a bool via Applied(). The detailed form exists
// so the listener (and tests) can distinguish "no-op because we already had
// newer state" from "no-op because of a foreign-identity PK collision".
type HostResolutionOutcome int

const (
	// OutcomeUnknown is the zero value. Helpers must never return it on a
	// successful path; it indicates a bug in the orchestrator if observed.
	OutcomeUnknown HostResolutionOutcome = iota
	// OutcomeApplied: the existing row was updated with a newer seq.
	OutcomeApplied
	// OutcomeStaleIgnored: a row exists but its stored seq >= the incoming
	// delivery seq. Idempotent no-op (replay, duplicate redelivery).
	OutcomeStaleIgnored
	// OutcomeSynthesized: no row existed under this identity; a synthetic
	// row was inserted from the envelope metadata (fresh-device delivery).
	OutcomeSynthesized
	// OutcomeForeignCollision: INSERT OR IGNORE skipped because the
	// review_id is already owned by a different identity. The listener is
	// identity-scoped by design so this path is not normally reachable;
	// silent skip is the conservative choice.
	OutcomeForeignCollision
)

// Applied reports whether the local ledger actually changed. It collapses the
// outcome down to the historical (bool, error) contract — callers that only
// want UI-noise gating can read this and ignore the specific outcome.
func (o HostResolutionOutcome) Applied() bool {
	return o == OutcomeApplied || o == OutcomeSynthesized
}

// tryUpdateExistingReview runs the seq-guarded UPDATE against the existing
// row. Returns updated=true when exactly one row was modified. updated=false
// covers both "no row existed" and "row exists but seq guard rejected" —
// the orchestrator disambiguates with probeReviewExists.
//
// status_source is force-set to "queried" because host-confirmed state wins
// over any local "manual" override; the user has been told the authoritative
// outcome and SentReviewsView surfaces a toast in that case.
func tryUpdateExistingReview(
	db dbExecutor,
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (updated bool, err error) {
	res, err := db.Exec(
		`UPDATE sent_reviews
		    SET status            = ?,
		        status_source     = 'queried',
		        resolved_at       = COALESCE(resolved_at, ?),
		        host_resolved_at  = ?,
		        response_text     = ?,
		        reject_reason     = ?,
		        delivery_seq      = ?
		  WHERE review_id = ?
		    AND identity  = ?
		    AND (delivery_seq IS NULL OR delivery_seq < ?)`,
		payload.Status,
		time.Now().UTC().Format(manualreview.ISOMicroLayout),
		payload.ResolvedAt,
		nullIfEmpty(payload.ResponseText),
		nullIfEmpty(payload.RejectReason),
		int64(deliverySeq),
		env.ReviewID,
		identity,
		int64(deliverySeq),
	)
	if err != nil {
		return false, fmt.Errorf("apply resolution update: %w", err)
	}
	affected, _ := res.RowsAffected()
	return affected == 1, nil
}

// probeReviewExists checks whether a row exists under (review_id, identity).
// Used after tryUpdateExistingReview's UPDATE matched 0 rows to distinguish
// "stored seq guarded us out" from "no such row" — only the latter justifies
// an INSERT.
func probeReviewExists(db dbExecutor, identity, reviewID string) (exists bool, err error) {
	var stored sql.NullInt64
	err = db.QueryRow(
		`SELECT delivery_seq FROM sent_reviews WHERE review_id = ? AND identity = ?`,
		reviewID, identity,
	).Scan(&stored)
	switch {
	case err == nil:
		return true, nil
	case err == sql.ErrNoRows:
		return false, nil
	default:
		return false, fmt.Errorf("apply resolution probe: %w", err)
	}
}

// synthesizeReviewRow performs the fresh-device INSERT. Returns inserted=true
// when one row landed and inserted=false when INSERT OR IGNORE was skipped
// (review_id PK collision under a different identity).
//
// INSERT OR IGNORE is intentional: review_id is the PK without identity, so
// a row under another identity with the same review_id must not overwrite the
// other tenant's row. status_source is "queried" because the row's entire
// existence on this device was created by a host resolution.
func synthesizeReviewRow(
	db dbExecutor,
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (inserted bool, err error) {
	endpointPath := joinEndpointPath(env.EndpointOwner, env.EndpointSlug)
	res, err := db.Exec(
		`INSERT OR IGNORE INTO sent_reviews
		   (review_id, identity, endpoint_path, endpoint_owner, endpoint_slug,
		    endpoint_name, endpoint_type, policy_name, request_messages,
		    placeholder, submitted_at, status, status_source, resolved_at,
		    host_resolved_at, response_text, reject_reason, delivery_seq)
		 VALUES (?, ?, ?, ?, ?, ?, 'agent', ?, ?, NULL, ?, ?, 'queried', ?, ?, ?, ?, ?)`,
		env.ReviewID, identity, endpointPath, env.EndpointOwner, env.EndpointSlug,
		env.EndpointName, env.PolicyName, "[]",
		payload.ResolvedAt, payload.Status,
		payload.ResolvedAt,
		payload.ResolvedAt, nullIfEmpty(payload.ResponseText), nullIfEmpty(payload.RejectReason),
		int64(deliverySeq),
	)
	if err != nil {
		return false, fmt.Errorf("insert synthesized resolution row: %w", err)
	}
	affected, _ := res.RowsAffected()
	return affected == 1, nil
}

// applyHostResolutionTx orchestrates the three helpers in the canonical order:
//
//  1. UPDATE-first (common case: row exists, first delivery).
//  2. EXISTS probe (UPDATE matched 0 rows — was it the seq guard or no row?).
//  3. INSERT OR IGNORE (no row — synthesize from envelope).
//
// Run inside a transaction so a concurrent RecordSentReview can't race between
// the UPDATE-miss in step 1 and the INSERT in step 3.
func applyHostResolutionTx(
	db dbExecutor,
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (HostResolutionOutcome, error) {
	updated, err := tryUpdateExistingReview(db, identity, env, payload, deliverySeq)
	if err != nil {
		return OutcomeUnknown, err
	}
	if updated {
		return OutcomeApplied, nil
	}

	exists, err := probeReviewExists(db, identity, env.ReviewID)
	if err != nil {
		return OutcomeUnknown, err
	}
	if exists {
		return OutcomeStaleIgnored, nil
	}

	inserted, err := synthesizeReviewRow(db, identity, env, payload, deliverySeq)
	if err != nil {
		return OutcomeUnknown, err
	}
	if inserted {
		return OutcomeSynthesized, nil
	}
	return OutcomeForeignCollision, nil
}

// ApplyHostResolution merges a host-delivered resolution into the local
// sent_reviews ledger.
//
// Returns (applied, err) where applied is true only when the local state
// actually changed — i.e. the listener should emit the Wails event and ACK
// the JetStream message based on err==nil regardless of applied, but should
// suppress UI noise when applied==false.
//
// identity is the username under which to scope the row. The listener gets it
// from the currently-logged-in user; passing it in explicitly (rather than
// reading a.currentIdentity()) makes the method testable without a full app.
//
// This method preserves the historical (bool, error) shape for backward
// compatibility. New callers wanting the typed outcome should use
// ApplyHostResolutionDetailed instead.
func (a *App) ApplyHostResolution(
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (bool, error) {
	outcome, err := a.ApplyHostResolutionDetailed(identity, env, payload, deliverySeq)
	if err != nil {
		return false, err
	}
	return outcome.Applied(), nil
}

// ApplyHostResolutionDetailed merges a host-delivered resolution and returns
// the typed outcome distinguishing applied, stale-ignored, synthesized, and
// foreign-collision cases.
//
// The three helpers run inside a BEGIN IMMEDIATE transaction so that a
// concurrent RecordSentReview cannot race between the UPDATE-miss in
// tryUpdateExistingReview and the INSERT in synthesizeReviewRow.
func (a *App) ApplyHostResolutionDetailed(
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (HostResolutionOutcome, error) {
	if identity == "" {
		return OutcomeUnknown, fmt.Errorf("identity is required")
	}
	if env.ReviewID == "" || env.ReviewID != payload.ReviewID {
		return OutcomeUnknown, fmt.Errorf("review_id mismatch or missing (env=%q payload=%q)", env.ReviewID, payload.ReviewID)
	}
	if payload.Status != manualreview.StatusApproved && payload.Status != manualreview.StatusRejected {
		return OutcomeUnknown, fmt.Errorf("unexpected resolution status %q", payload.Status)
	}

	db, err := a.sentReviewsDB()
	if err != nil {
		return OutcomeUnknown, err
	}

	// db.Conn pins a single connection from the pool so BEGIN IMMEDIATE,
	// the helpers, and COMMIT all run on the same SQLite connection — tx
	// state in SQLite is per-connection. Plain db.Exec("BEGIN IMMEDIATE")
	// would be free to land each statement on a different pooled conn.
	ctx := context.Background()
	conn, err := db.Conn(ctx)
	if err != nil {
		return OutcomeUnknown, fmt.Errorf("acquire conn: %w", err)
	}
	defer conn.Close()

	exec := &connExecutor{ctx: ctx, conn: conn}
	if _, err := conn.ExecContext(ctx, "BEGIN IMMEDIATE"); err != nil {
		return OutcomeUnknown, fmt.Errorf("begin tx: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_, _ = conn.ExecContext(ctx, "ROLLBACK")
		}
	}()

	outcome, err := applyHostResolutionTx(exec, identity, env, payload, deliverySeq)
	if err != nil {
		return OutcomeUnknown, err
	}

	if _, err := conn.ExecContext(ctx, "COMMIT"); err != nil {
		return OutcomeUnknown, fmt.Errorf("commit tx: %w", err)
	}
	committed = true
	return outcome, nil
}

// connExecutor adapts *sql.Conn to the dbExecutor interface so the helpers,
// which use the non-context Exec/QueryRow shape, can run against a pinned
// connection. The context is supplied at construction.
type connExecutor struct {
	ctx  context.Context
	conn *sql.Conn
}

func (c *connExecutor) Exec(query string, args ...any) (sql.Result, error) {
	return c.conn.ExecContext(c.ctx, query, args...)
}

func (c *connExecutor) QueryRow(query string, args ...any) *sql.Row {
	return c.conn.QueryRowContext(c.ctx, query, args...)
}
