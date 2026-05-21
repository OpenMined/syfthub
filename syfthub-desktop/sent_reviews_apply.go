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
	"database/sql"
	"fmt"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

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
func (a *App) ApplyHostResolution(
	identity string,
	env manualreview.ResolvedEnvelope,
	payload manualreview.ResolvedPayload,
	deliverySeq uint64,
) (bool, error) {
	if identity == "" {
		return false, fmt.Errorf("identity is required")
	}
	if env.ReviewID == "" || env.ReviewID != payload.ReviewID {
		return false, fmt.Errorf("review_id mismatch or missing (env=%q payload=%q)", env.ReviewID, payload.ReviewID)
	}
	if payload.Status != manualreview.StatusApproved && payload.Status != manualreview.StatusRejected {
		return false, fmt.Errorf("unexpected resolution status %q", payload.Status)
	}

	db, err := openSentReviewsDB()
	if err != nil {
		return false, err
	}
	defer db.Close()

	// Try UPDATE-first with the seq guard. This is the common path: the user
	// captured the hold on this device (the row exists) and the host is
	// delivering the first resolution (delivery_seq is NULL).
	//
	// status_source is force-set to "queried" because host-confirmed state
	// wins over any local "manual" override — the user has been told the
	// authoritative outcome. SentReviewsView already shows a toast in that
	// case (see provenanceCaption).
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
	if affected == 1 {
		return true, nil
	}

	// UPDATE matched 0 rows. Two reasons:
	//   (a) the row exists but its delivery_seq >= deliverySeq (idempotent
	//       no-op — older or duplicate redelivery);
	//   (b) the row does not exist (fresh-device delivery — synthesize it).
	// Distinguish with a cheap existence check so we don't INSERT over a row
	// that's intentionally at a newer seq.
	var stored sql.NullInt64
	err = db.QueryRow(
		`SELECT delivery_seq FROM sent_reviews WHERE review_id = ? AND identity = ?`,
		env.ReviewID, identity,
	).Scan(&stored)
	switch {
	case err == nil:
		// Row exists; the seq guard rejected us. Idempotent — no-op.
		return false, nil
	case err == sql.ErrNoRows:
		// Fall through to INSERT.
	default:
		return false, fmt.Errorf("apply resolution probe: %w", err)
	}

	// Fresh-device INSERT. We mark status_source="queried" since the row's
	// entire existence on this device was created by a host resolution; there
	// was no captured hold to base it on. submitted_at falls back to the
	// host's resolved_at because we have no other timestamp.
	//
	// INSERT OR IGNORE: review_id is the PK without identity, so a row under
	// another identity with the same review_id (extremely unlikely with uuid4
	// review_ids, and the listener is identity-scoped) must not overwrite the
	// other tenant's row.
	endpointPath := joinEndpointPath(env.EndpointOwner, env.EndpointSlug)
	res, err = db.Exec(
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
	inserted, _ := res.RowsAffected()
	return inserted == 1, nil
}
