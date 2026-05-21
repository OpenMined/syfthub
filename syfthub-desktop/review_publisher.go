package main

// Host-side publisher for manual-review resolutions.
//
// When the endpoint owner approves or rejects a held request via the
// Requests tab, the desktop's resolveManualReview path (manual_review_operations.go)
// performs the local UPDATE on manual_reviews and then hands off to this
// publisher to deliver the outcome over the wire. The publisher derives a
// per-resolution cipher (HKDF over the identity-pair ECDH salted with
// review_id), encrypts the ResolvedPayload, wraps it in a ResolvedEnvelope,
// and publishes via JetStream so the recipient gets the message even when
// they are offline at resolve time.
//
// Delivery is at-least-once at the wire layer (JetStream persistence + ACK
// semantics). Idempotency on the caller side is provided by delivery_seq —
// see sent_reviews_apply.go.

import (
	"context"
	"crypto/ecdh"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/nats-io/nats.go"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// publishTimeout caps how long a JetStream publish may block. Long enough to
// absorb a slow round-trip to a remote cluster; short enough that a wedged
// publish doesn't hold the Wails goroutine that triggered the resolve.
const publishTimeout = 10 * time.Second

// ReviewPublisher delivers ResolvedEnvelope messages to caller inboxes over
// JetStream. One per app (the keypair and JetStream context are shared by
// every endpoint's resolutions).
type ReviewPublisher struct {
	js         nats.JetStreamContext
	privateKey *ecdh.PrivateKey
	hostPubB64 string // host's X25519 identity pubkey, base64url; carried in every envelope
	logger     *slog.Logger
}

// NewReviewPublisher constructs the publisher from an established NATS
// connection, the host's identity key, and the host's username (used for
// envelope provenance, not for cipher derivation). Returns an error when
// JetStream is not available on the underlying connection; callers degrade
// gracefully by logging and skipping manual-review delivery.
func NewReviewPublisher(conn *nats.Conn, identityKey *ecdh.PrivateKey, logger *slog.Logger) (*ReviewPublisher, error) {
	if conn == nil {
		return nil, errors.New("nats conn is nil")
	}
	if identityKey == nil {
		return nil, errors.New("identity key is nil")
	}
	js, err := conn.JetStream()
	if err != nil {
		return nil, fmt.Errorf("JetStream not available: %w", err)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &ReviewPublisher{
		js:         js,
		privateKey: identityKey,
		hostPubB64: base64.RawURLEncoding.EncodeToString(identityKey.PublicKey().Bytes()),
		logger:     logger,
	}, nil
}

// PublishWithMeta encrypts payload to routing.CallerPubkeyB64 under a key
// derived from routing.ReviewID, wraps it in a ResolvedEnvelope with the
// plaintext meta fields a fresh-device caller needs to render the row before
// decryption, and publishes to the caller's inbox subject. Returns the
// JetStream sequence on success.
//
// On wire-level failure the routing recorder tracks retry state via
// RecordAttempt; this method just returns the error so the caller can decide.
func (p *ReviewPublisher) PublishWithMeta(
	ctx context.Context,
	routing manualreview.Routing,
	payload manualreview.ResolvedPayload,
	endpointOwner, endpointSlug, endpointName, policyName string,
) (uint64, error) {
	if routing.ReviewID == "" || routing.CallerPubkeyB64 == "" || routing.InboxSubject == "" {
		return 0, errors.New("routing is incomplete")
	}
	if payload.ReviewID != routing.ReviewID {
		return 0, fmt.Errorf("payload review_id %q != routing review_id %q", payload.ReviewID, routing.ReviewID)
	}
	cipher, err := manualreview.NewResolutionCipher(p.privateKey, routing.CallerPubkeyB64, routing.ReviewID)
	if err != nil {
		return 0, fmt.Errorf("derive resolution cipher: %w", err)
	}
	plaintext, err := json.Marshal(payload)
	if err != nil {
		return 0, fmt.Errorf("marshal payload: %w", err)
	}
	nonceB64, ctB64, err := cipher.Seal(plaintext, routing.ReviewID)
	if err != nil {
		return 0, fmt.Errorf("seal payload: %w", err)
	}
	wire, err := json.Marshal(manualreview.ResolvedEnvelope{
		Protocol:         manualreview.ProtocolVersion,
		Type:             manualreview.MsgTypeResolved,
		ReviewID:         routing.ReviewID,
		SessionID:        routing.SessionID,
		EndpointOwner:    endpointOwner,
		EndpointSlug:     endpointSlug,
		EndpointName:     endpointName,
		PolicyName:       policyName,
		SenderPublicKey:  p.hostPubB64,
		Nonce:            nonceB64,
		EncryptedPayload: ctB64,
	})
	if err != nil {
		return 0, fmt.Errorf("marshal envelope: %w", err)
	}

	pubCtx, cancel := context.WithTimeout(ctx, publishTimeout)
	defer cancel()
	ack, err := p.js.PublishMsg(&nats.Msg{
		Subject: routing.InboxSubject,
		Header:  nats.Header{nats.MsgIdHdr: []string{routing.ReviewID}},
		Data:    wire,
	}, nats.Context(pubCtx))
	if err != nil {
		return 0, fmt.Errorf("publish to %s: %w", routing.InboxSubject, err)
	}
	p.logger.Info("[MR-PUBLISH] delivered resolution",
		"review_id", routing.ReviewID,
		"inbox", routing.InboxSubject,
		"endpoint", endpointSlug,
		"seq", ack.Sequence,
		"duplicate", ack.Duplicate,
	)
	return ack.Sequence, nil
}
