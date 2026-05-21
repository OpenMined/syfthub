package main

// Caller-side durable consumer for manual-review resolution envelopes.
//
// See review_publisher.go for the host-side counterpart. The listener:
//
//   1. Binds a durable JetStream consumer to syfthub.inbox.<username>.review
//      using the per-device durable name "mr-<username>-<deviceID>". A
//      durable name lets the same physical desktop survive restarts without
//      stealing messages from a future second device on the same account.
//
//   2. For each envelope, derives the resolution cipher (with the caller's
//      identity key + envelope.SenderPublicKey + envelope.ReviewID),
//      decrypts the payload, and hands it to App.ApplyHostResolution.
//
//   3. Emits a Wails event ("manual-review:resolved") so SentReviewsView
//      refetches and the user sees the resolution land in real time.
//
//   4. ACKs the JetStream message on success; Naks (with a delay) on
//      transient errors; Terms on permanent decode/decrypt failures so the
//      consumer doesn't loop forever.
//
// The listener owns a goroutine; Start blocks until Stop is called or the
// underlying NATS connection drops.

import (
	"context"
	"crypto/ecdh"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// reviewInboxFetchBatch is the number of messages requested per Fetch call.
// Small enough to keep latency low; large enough that a bursty backfill (a
// caller comes online after a vacation, 30 days of resolutions waiting)
// drains quickly.
const reviewInboxFetchBatch = 16

// reviewInboxFetchWait caps how long Fetch blocks before returning empty.
// JetStream will return early when at least one message is available, so
// the cap is the worst-case idle wakeup rate. Long enough to be cheap; short
// enough that Stop unblocks promptly.
const reviewInboxFetchWait = 30 * time.Second

// reviewInboxNakBackoff is how long to delay before a transient-error redeliver.
// Long enough that we don't hot-loop on a wedged DB; short enough that recovery
// after a real transient (lock contention with the policy runner) is prompt.
const reviewInboxNakBackoff = 5 * time.Second

// ReviewInboxListener is a one-per-app long-running consumer of the
// resolution inbox for the currently-logged-in user. nil-safe: a zero-value
// listener never started can be safely Stop()'d.
type ReviewInboxListener struct {
	apply       func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload, seq uint64) (bool, error)
	notify      func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload)
	identity    string
	deviceID    string
	identityKey *ecdh.PrivateKey
	js          nats.JetStreamContext
	logger      *slog.Logger

	mu     sync.Mutex
	cancel context.CancelFunc
	done   chan struct{}
}

// NewReviewInboxListener builds a listener bound to one (username, deviceID)
// pair. The apply callback is the local write path (App.ApplyHostResolution);
// notify is the Wails event emitter — kept separate so tests can drive
// without touching Wails.
func NewReviewInboxListener(
	conn *nats.Conn,
	identityKey *ecdh.PrivateKey,
	identity, deviceID string,
	apply func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload, seq uint64) (bool, error),
	notify func(env manualreview.ResolvedEnvelope, payload manualreview.ResolvedPayload),
	logger *slog.Logger,
) (*ReviewInboxListener, error) {
	if conn == nil {
		return nil, errors.New("nats conn is nil")
	}
	if identityKey == nil {
		return nil, errors.New("identity key is nil")
	}
	if identity == "" {
		return nil, errors.New("identity is empty")
	}
	if deviceID == "" {
		return nil, errors.New("device id is empty")
	}
	js, err := conn.JetStream()
	if err != nil {
		return nil, fmt.Errorf("JetStream not available: %w", err)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &ReviewInboxListener{
		apply:       apply,
		notify:      notify,
		identity:    identity,
		deviceID:    deviceID,
		identityKey: identityKey,
		js:          js,
		logger:      logger,
	}, nil
}

// Start spawns the consumer goroutine. Returns immediately; the goroutine
// runs until Stop is called or the underlying connection drops.
//
// Safe to call once. A second call without a Stop in between is a no-op.
func (l *ReviewInboxListener) Start(ctx context.Context) error {
	l.mu.Lock()
	if l.cancel != nil {
		l.mu.Unlock()
		return nil
	}
	loopCtx, cancel := context.WithCancel(ctx)
	l.cancel = cancel
	l.done = make(chan struct{})
	l.mu.Unlock()

	subject := manualreview.InboxSubjectFor(l.identity)
	durable := "mr-" + l.identity + "-" + l.deviceID
	sub, err := l.js.PullSubscribe(subject, durable,
		nats.AckExplicit(),
		nats.DeliverAll(),
		nats.ManualAck(),
		nats.AckWait(30*time.Second),
		nats.MaxDeliver(5),
	)
	if err != nil {
		l.mu.Lock()
		l.cancel = nil
		close(l.done)
		l.mu.Unlock()
		return fmt.Errorf("subscribe %s (durable %s): %w", subject, durable, err)
	}

	go l.run(loopCtx, sub, subject, durable)
	return nil
}

// Stop ends the consumer goroutine and waits for it to drain. Idempotent.
func (l *ReviewInboxListener) Stop() {
	l.mu.Lock()
	if l.cancel == nil {
		l.mu.Unlock()
		return
	}
	cancel := l.cancel
	done := l.done
	l.cancel = nil
	l.mu.Unlock()
	cancel()
	<-done
}

func (l *ReviewInboxListener) run(ctx context.Context, sub *nats.Subscription, subject, durable string) {
	defer close(l.done)
	defer func() {
		if err := sub.Unsubscribe(); err != nil {
			l.logger.Debug("[MR-INBOX] unsubscribe failed", "error", err)
		}
	}()
	l.logger.Info("[MR-INBOX] consumer started",
		"identity", l.identity, "device", l.deviceID,
		"subject", subject, "durable", durable)

	for {
		select {
		case <-ctx.Done():
			l.logger.Info("[MR-INBOX] consumer stopping", "identity", l.identity)
			return
		default:
		}
		msgs, err := sub.Fetch(reviewInboxFetchBatch, nats.MaxWait(reviewInboxFetchWait))
		if err != nil {
			if errors.Is(err, nats.ErrTimeout) || errors.Is(err, context.DeadlineExceeded) {
				continue
			}
			if errors.Is(err, context.Canceled) || errors.Is(err, nats.ErrConnectionClosed) {
				return
			}
			l.logger.Warn("[MR-INBOX] fetch failed; backing off", "error", err)
			select {
			case <-ctx.Done():
				return
			case <-time.After(reviewInboxNakBackoff):
			}
			continue
		}
		for _, m := range msgs {
			l.handle(m)
		}
	}
}

// handle decodes, decrypts, applies, and ACKs one envelope. Bad envelopes
// are Term'd so the consumer doesn't redeliver them forever. Transient
// failures (DB lock) are Nak'd with a short backoff.
func (l *ReviewInboxListener) handle(m *nats.Msg) {
	var env manualreview.ResolvedEnvelope
	if err := json.Unmarshal(m.Data, &env); err != nil {
		l.logger.Warn("[MR-INBOX] dropping unparseable envelope", "error", err)
		_ = m.Term()
		return
	}
	if env.Protocol != manualreview.ProtocolVersion || env.Type != manualreview.MsgTypeResolved {
		l.logger.Warn("[MR-INBOX] dropping envelope of unknown shape",
			"protocol", env.Protocol, "type", env.Type)
		_ = m.Term()
		return
	}
	if env.SenderPublicKey == "" || env.EncryptedPayload == "" || env.ReviewID == "" {
		l.logger.Warn("[MR-INBOX] dropping envelope missing required fields",
			"review_id", env.ReviewID)
		_ = m.Term()
		return
	}

	cipher, err := manualreview.NewResolutionCipher(l.identityKey, env.SenderPublicKey, env.ReviewID)
	if err != nil {
		l.logger.Warn("[MR-INBOX] dropping envelope — cipher derivation failed",
			"review_id", env.ReviewID, "error", err)
		_ = m.Term()
		return
	}
	plaintext, err := cipher.Open(env.Nonce, env.EncryptedPayload, env.ReviewID)
	if err != nil {
		// Decryption can fail when our identity key rotates between capture
		// and delivery, when the host has the wrong pubkey on file, or when
		// the message was tampered. Either way the consumer cannot recover
		// — Term so we stop redelivering it. The user can still see the
		// hold in SentReviewsView at status_source="manual"/"captured" and
		// resolve manually.
		l.logger.Warn("[MR-INBOX] dropping envelope — decrypt failed",
			"review_id", env.ReviewID, "error", err)
		_ = m.Term()
		return
	}
	var payload manualreview.ResolvedPayload
	if err := json.Unmarshal(plaintext, &payload); err != nil {
		l.logger.Warn("[MR-INBOX] dropping envelope — payload decode failed",
			"review_id", env.ReviewID, "error", err)
		_ = m.Term()
		return
	}

	meta, _ := m.Metadata()
	var seq uint64
	if meta != nil {
		seq = meta.Sequence.Stream
	}

	applied, err := l.apply(env, payload, seq)
	if err != nil {
		l.logger.Warn("[MR-INBOX] apply failed; nakking for redelivery",
			"review_id", env.ReviewID, "error", err)
		_ = m.NakWithDelay(reviewInboxNakBackoff)
		return
	}
	// Log every received envelope so a successful pipeline shows up in the
	// log just as clearly as a failure. "applied=false" means the seq guard
	// skipped a duplicate; "applied=true" means the sent_reviews row changed
	// and the Wails event was emitted.
	l.logger.Info("[MR-INBOX] resolution received",
		"review_id", env.ReviewID,
		"status", payload.Status,
		"seq", seq,
		"applied", applied,
	)
	if applied && l.notify != nil {
		l.notify(env, payload)
	}
	if err := m.Ack(); err != nil {
		l.logger.Warn("[MR-INBOX] ack failed", "review_id", env.ReviewID, "error", err)
	}
}
