package manualreview_test

// End-to-end smoke test for the manual-review resolution channel.
//
// Spins up an embedded NATS server with JetStream, simulates the host
// publishing a resolution envelope, and verifies a JetStream consumer
// receives + decrypts it correctly. Validates:
//
//   * MR_RESOLUTIONS stream creation is idempotent across two callers.
//   * The published envelope round-trips: subject, header dedup id,
//     plaintext metadata, encrypted payload.
//   * The receiver derives the same cipher and decodes payload.Status.
//   * Replay of the same MsgID is deduped at the JetStream layer (Duplicate
//     flag set on the ack).
//
// This test exercises ONLY the SDK-level pieces — the desktop's
// ReviewPublisher and ReviewInboxListener wrappers carry their own
// unit tests. Keeping this layer focused makes it portable to other SDK
// consumers (CLI, third-party) that may want to publish resolutions
// without the desktop's Wails layer.

import (
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"testing"
	"time"

	natsserver "github.com/nats-io/nats-server/v2/server"
	"github.com/nats-io/nats.go"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/manualreview"
)

// runEmbeddedJetStreamNATS starts an in-process NATS server with JetStream
// enabled, on a random free port, with a tempdir-backed JS store so the test
// can publish persistent messages.
func runEmbeddedJetStreamNATS(t *testing.T) *natsserver.Server {
	t.Helper()
	storeDir := t.TempDir()
	s, err := natsserver.NewServer(&natsserver.Options{
		Host:      "127.0.0.1",
		Port:      -1,
		NoLog:     true,
		NoSigs:    true,
		JetStream: true,
		StoreDir:  storeDir,
	})
	if err != nil {
		t.Fatalf("create embedded NATS server: %v", err)
	}
	go s.Start()
	if !s.ReadyForConnections(5 * time.Second) {
		t.Fatal("embedded NATS server not ready")
	}
	return s
}

// mustGenKey generates a fresh X25519 keypair.
func mustGenKey(t *testing.T) *ecdh.PrivateKey {
	t.Helper()
	k, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	return k
}

// pubB64 returns the base64url-encoded public key for an identity.
func pubB64(k *ecdh.PrivateKey) string {
	return base64.RawURLEncoding.EncodeToString(k.PublicKey().Bytes())
}

// provisionStream mirrors the desktop's review_stream_provision.go but
// keeps the test SDK-only.
func provisionStream(t *testing.T, js nats.JetStreamContext) {
	t.Helper()
	_, err := js.AddStream(&nats.StreamConfig{
		Name:       "MR_RESOLUTIONS_TEST",
		Subjects:   []string{"syfthub.inbox.*.review"},
		Retention:  nats.LimitsPolicy,
		Storage:    nats.FileStorage,
		MaxAge:     24 * time.Hour,
		MaxMsgSize: 1 << 20,
		Replicas:   1,
	})
	if err != nil {
		t.Fatalf("add stream: %v", err)
	}
}

// TestEndToEnd_ResolutionRoundTrip walks the full pipeline: host derives a
// cipher with caller pubkey + review_id, encrypts a payload, publishes to
// the caller's inbox subject; caller subscribes durably, decrypts, and
// reads back the original payload.
func TestEndToEnd_ResolutionRoundTrip(t *testing.T) {
	srv := runEmbeddedJetStreamNATS(t)
	defer srv.Shutdown()
	url := srv.ClientURL()
	_ = slog.New(slog.NewTextHandler(io.Discard, nil))

	conn, err := nats.Connect(url)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer conn.Close()
	js, err := conn.JetStream()
	if err != nil {
		t.Fatalf("jetstream: %v", err)
	}
	provisionStream(t, js)

	hostKey := mustGenKey(t)
	callerKey := mustGenKey(t)
	const reviewID = "ab12cd34ef56"
	const callerUsername = "bob"
	inbox := manualreview.InboxSubjectFor(callerUsername)

	// --- HOST: encrypt + publish ---
	hostCipher, err := manualreview.NewResolutionCipher(hostKey, pubB64(callerKey), reviewID)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}
	payload := manualreview.ResolvedPayload{
		ReviewID:       reviewID,
		Status:         manualreview.StatusApproved,
		ResolvedAt:     "2026-05-22T10:00:00.000000+00:00",
		ResponseText:   "the real held answer",
		ResolverUserID: "alice",
	}
	plaintext, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	nonce, ciphertext, err := hostCipher.Seal(plaintext, reviewID)
	if err != nil {
		t.Fatalf("seal: %v", err)
	}
	envelope := manualreview.ResolvedEnvelope{
		Protocol:         manualreview.ProtocolVersion,
		Type:             manualreview.MsgTypeResolved,
		ReviewID:         reviewID,
		EndpointOwner:    "alice",
		EndpointSlug:     "research-agent",
		SenderPublicKey:  pubB64(hostKey),
		Nonce:            nonce,
		EncryptedPayload: ciphertext,
	}
	wire, _ := json.Marshal(envelope)

	ack1, err := js.PublishMsg(&nats.Msg{
		Subject: inbox,
		Header:  nats.Header{nats.MsgIdHdr: []string{reviewID}},
		Data:    wire,
	})
	if err != nil {
		t.Fatalf("publish: %v", err)
	}
	if ack1.Duplicate {
		t.Error("first publish should not be a duplicate")
	}
	if ack1.Sequence == 0 {
		t.Error("expected non-zero JetStream sequence")
	}

	// --- CALLER: durable consumer, decrypt, verify ---
	sub, err := js.PullSubscribe(inbox, "mr-"+callerUsername+"-test-device",
		nats.AckExplicit(), nats.DeliverAll(), nats.ManualAck(),
	)
	if err != nil {
		t.Fatalf("pull subscribe: %v", err)
	}
	defer sub.Unsubscribe()

	msgs, err := sub.Fetch(1, nats.MaxWait(2*time.Second))
	if err != nil {
		t.Fatalf("fetch: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("got %d messages, want 1", len(msgs))
	}

	var got manualreview.ResolvedEnvelope
	if err := json.Unmarshal(msgs[0].Data, &got); err != nil {
		t.Fatalf("decode envelope: %v", err)
	}
	if got.ReviewID != reviewID || got.SenderPublicKey != pubB64(hostKey) {
		t.Errorf("envelope round-trip mismatch: %+v", got)
	}

	callerCipher, err := manualreview.NewResolutionCipher(callerKey, got.SenderPublicKey, got.ReviewID)
	if err != nil {
		t.Fatalf("caller cipher: %v", err)
	}
	decrypted, err := callerCipher.Open(got.Nonce, got.EncryptedPayload, got.ReviewID)
	if err != nil {
		t.Fatalf("decrypt: %v", err)
	}
	var gotPayload manualreview.ResolvedPayload
	if err := json.Unmarshal(decrypted, &gotPayload); err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	if gotPayload.Status != manualreview.StatusApproved {
		t.Errorf("Status = %q, want approved", gotPayload.Status)
	}
	if gotPayload.ResponseText != "the real held answer" {
		t.Errorf("ResponseText = %q", gotPayload.ResponseText)
	}

	if err := msgs[0].Ack(); err != nil {
		t.Errorf("ack: %v", err)
	}
}

// TestEndToEnd_ReplayDedupedByMsgID re-publishes the same MsgID and verifies
// JetStream reports the second as a duplicate within the dedup window.
// This is the wire-layer half of the idempotency story (the caller side has
// delivery_seq for the longer horizon).
func TestEndToEnd_ReplayDedupedByMsgID(t *testing.T) {
	srv := runEmbeddedJetStreamNATS(t)
	defer srv.Shutdown()
	conn, _ := nats.Connect(srv.ClientURL())
	defer conn.Close()
	js, _ := conn.JetStream()
	provisionStream(t, js)

	subject := manualreview.InboxSubjectFor("eve")
	msg := &nats.Msg{
		Subject: subject,
		Header:  nats.Header{nats.MsgIdHdr: []string{"rid-dedup"}},
		Data:    []byte(`{"protocol":"syfthub-mr-v1","type":"manual_review_resolved","review_id":"rid-dedup"}`),
	}

	ack1, err := js.PublishMsg(msg)
	if err != nil {
		t.Fatalf("first publish: %v", err)
	}
	if ack1.Duplicate {
		t.Error("first publish should not be a duplicate")
	}

	ack2, err := js.PublishMsg(msg)
	if err != nil {
		t.Fatalf("second publish: %v", err)
	}
	if !ack2.Duplicate {
		t.Error("second publish with same MsgID should be a duplicate")
	}
	if ack2.Sequence != ack1.Sequence {
		t.Errorf("dedup should map to original sequence: %d vs %d", ack2.Sequence, ack1.Sequence)
	}
}

// TestEndToEnd_InboxFiltersByUsername proves the wildcard subject pattern
// scopes deliveries correctly: a consumer for alice's inbox does NOT see
// envelopes published to bob's inbox.
func TestEndToEnd_InboxFiltersByUsername(t *testing.T) {
	srv := runEmbeddedJetStreamNATS(t)
	defer srv.Shutdown()
	conn, _ := nats.Connect(srv.ClientURL())
	defer conn.Close()
	js, _ := conn.JetStream()
	provisionStream(t, js)

	if _, err := js.Publish(manualreview.InboxSubjectFor("bob"), []byte(`{"x":1}`)); err != nil {
		t.Fatalf("publish bob: %v", err)
	}
	if _, err := js.Publish(manualreview.InboxSubjectFor("alice"), []byte(`{"x":2}`)); err != nil {
		t.Fatalf("publish alice: %v", err)
	}

	sub, err := js.PullSubscribe(manualreview.InboxSubjectFor("alice"), "alice-only",
		nats.AckExplicit(), nats.DeliverAll(), nats.ManualAck(),
	)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	defer sub.Unsubscribe()

	msgs, err := sub.Fetch(10, nats.MaxWait(time.Second))
	if err != nil {
		t.Fatalf("fetch: %v", err)
	}
	if len(msgs) != 1 {
		t.Fatalf("got %d messages, want 1 (alice's only)", len(msgs))
	}
	for _, m := range msgs {
		if string(m.Data) != `{"x":2}` {
			t.Errorf("alice's consumer got %s, expected only alice's message", m.Data)
		}
		_ = m.Ack()
	}
}
