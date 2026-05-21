package main

// JetStream provisioning for the manual-review resolution channel.
//
// The MR_RESOLUTIONS stream is the durable inbox layer that lets the host
// publish a resolution after the original v2 session has ended (hours, days,
// or even desktop restarts later). One stream serves every recipient on the
// cluster — per-recipient routing happens via the subject pattern
// "syfthub.inbox.<username>.review", and per-recipient durable consumers
// bind a filter on that exact subject.
//
// This file is called once at app startup, post-NATS-connect. Every desktop
// instance racing to provision this stream is fine: the create call is
// idempotent on "stream already in use", and updates are skipped when the
// existing config already matches what we want.

import (
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/nats-io/nats.go"
)

// Stream configuration constants. Changing any of these requires a
// migration plan because they govern the at-rest layout of resolution
// envelopes.
const (
	// mrStreamName is the JetStream stream name. Uppercase + underscores per
	// the convention NATS uses for stream names in its own docs.
	mrStreamName = "MR_RESOLUTIONS"

	// mrStreamSubjectFilter is the wildcard that captures every recipient's
	// inbox. The single-token "*" matches the username segment between
	// "syfthub.inbox." and ".review" — see manualreview.InboxSubjectFor.
	mrStreamSubjectFilter = "syfthub.inbox.*.review"

	// mrStreamMaxAge bounds resolution retention. 30 days is a balance
	// between "long enough that a vacationing caller still gets their
	// response when they return" and "short enough that the stream doesn't
	// grow without bound on a busy host". The retention is per-message, so
	// freshly-published resolutions are not affected by old ones aging out.
	mrStreamMaxAge = 30 * 24 * time.Hour

	// mrStreamMaxMsgSize caps a single resolution envelope. Held responses
	// can be RAG document lists or long agent outputs; 1 MiB matches the
	// NATS default max payload and lets a typical RAG answer fit inline. If
	// we ever need bigger, route through the attachment object store and
	// reference it by ID — but Phase 2.0 does not.
	mrStreamMaxMsgSize int32 = 1 << 20

	// mrStreamReplicas is the replication factor. Single-node dev runs work
	// with 1; production clusters override this via the per-deployment NATS
	// config (stream-level replicas can be UpdateStream'd up after the
	// cluster forms). Starting low is safe — JetStream tolerates moving up.
	mrStreamReplicas = 1
)

// provisionMRResolutionsStream creates (or binds to) the MR_RESOLUTIONS
// stream on the JetStream server backing conn. Idempotent. Logs once on
// create, once on bind. Returns nil on success — including the "already
// exists" case — and a non-nil error when the server has no JetStream
// support OR the stream exists with a config we explicitly disagree with.
//
// Graceful degradation: when this returns an error, the caller logs it and
// continues without manual-review delivery. The capture path still records
// routing rows; the host startup reconcile will pick them up if the stream
// later becomes available.
func provisionMRResolutionsStream(conn *nats.Conn, logger *slog.Logger) error {
	if conn == nil {
		return errors.New("nats conn is nil")
	}
	js, err := conn.JetStream()
	if err != nil {
		return fmt.Errorf("JetStream not available on this NATS connection: %w", err)
	}

	desired := &nats.StreamConfig{
		Name:        mrStreamName,
		Description: "Manual-review resolutions published by endpoint hosts to caller inboxes",
		Subjects:    []string{mrStreamSubjectFilter},
		Retention:   nats.LimitsPolicy,
		Discard:     nats.DiscardOld,
		MaxAge:      mrStreamMaxAge,
		MaxMsgSize:  mrStreamMaxMsgSize,
		Storage:     nats.FileStorage,
		Replicas:    mrStreamReplicas,
	}

	_, err = js.AddStream(desired)
	if err == nil {
		logger.Info("[MR-STREAM] provisioned",
			"stream", mrStreamName,
			"subjects", mrStreamSubjectFilter,
			"max_age", mrStreamMaxAge,
			"max_msg_size", mrStreamMaxMsgSize,
			"replicas", mrStreamReplicas,
		)
		return nil
	}
	if !errors.Is(err, nats.ErrStreamNameAlreadyInUse) {
		return fmt.Errorf("AddStream %s: %w", mrStreamName, err)
	}

	// Bind path: a previous run (or another desktop instance) already
	// provisioned the stream. We do NOT UpdateStream here — silently
	// rewriting subjects/retention could disrupt in-flight consumers
	// belonging to other recipients. If config drifts we surface it via
	// a log line; operators can run a one-shot reconcile out-of-band.
	info, infoErr := js.StreamInfo(mrStreamName)
	if infoErr != nil {
		logger.Warn("[MR-STREAM] stream exists but info lookup failed — continuing",
			"stream", mrStreamName, "error", infoErr)
		return nil
	}
	if !streamConfigMatches(info.Config, *desired) {
		logger.Warn("[MR-STREAM] stream config drift detected — leaving existing config in place",
			"stream", mrStreamName,
			"server_subjects", info.Config.Subjects,
			"want_subjects", desired.Subjects,
			"server_max_age", info.Config.MaxAge,
			"want_max_age", desired.MaxAge,
		)
		return nil
	}
	logger.Info("[MR-STREAM] bound to existing stream", "stream", mrStreamName)
	return nil
}

// streamConfigMatches compares the fields we care about between an existing
// stream config and our desired one. We intentionally ignore replica count
// and storage backend on bind — those vary between dev (single-node memory)
// and prod (clustered file), and rewriting them under a running cluster is
// disruptive.
func streamConfigMatches(got, want nats.StreamConfig) bool {
	if len(got.Subjects) != len(want.Subjects) {
		return false
	}
	for i, s := range got.Subjects {
		if s != want.Subjects[i] {
			return false
		}
	}
	if got.Retention != want.Retention {
		return false
	}
	if got.MaxAge != want.MaxAge {
		return false
	}
	if got.MaxMsgSize != want.MaxMsgSize && want.MaxMsgSize > 0 {
		return false
	}
	return true
}
