package transport

import (
	"encoding/base64"
	"encoding/json"
	"io"
	"log/slog"
	"sync"
	"testing"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// TestDialMintsSessionAttachmentKey asserts the client-side AgentDialer mints
// a 32-byte session_attachment_key whenever AttachmentCapability is requested
// without an explicit key, retains it on the AgentClientSession, and ships
// the base64-encoded form inside the encrypted session_start payload that
// reaches the host's space subject.
func TestDialMintsSessionAttachmentKey(t *testing.T) {
	srv := runEmbeddedNATS(t)
	defer srv.Shutdown()
	natsURL := srv.ClientURL()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	const hostUser = "hostbob"
	hostCreds := &syfthubapi.NATSCredentials{URL: natsURL, Subject: spaceSubjectPrefix + hostUser}

	hostConn, err := NewNATSConn(hostCreds, "key-test-host", logger)
	if err != nil {
		t.Fatalf("host NATSConn: %v", err)
	}
	defer hostConn.Close()

	hostT, err := NewNATSTransport(hostConn, &Config{
		SpaceURL:        "tunneling:" + hostUser,
		NATSCredentials: hostCreds,
		Logger:          logger,
	})
	if err != nil {
		t.Fatalf("NewNATSTransport: %v", err)
	}

	// Passive observer on the host's space subject — captures the envelope
	// without running the full bridge handler.
	var (
		mu       sync.Mutex
		captured []byte
		gotOnce  sync.Once
		gotCh    = make(chan struct{})
	)
	if _, err := hostT.conn.Subscribe(spaceSubjectPrefix+hostUser, func(m *nats.Msg) {
		mu.Lock()
		captured = append([]byte(nil), m.Data...)
		mu.Unlock()
		gotOnce.Do(func() { close(gotCh) })
	}); err != nil {
		t.Fatalf("subscribe space: %v", err)
	}
	time.Sleep(150 * time.Millisecond)

	clientKey, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("client keypair: %v", err)
	}
	clientConn, err := NewNATSConn(&syfthubapi.NATSCredentials{URL: natsURL}, "key-test-client", logger)
	if err != nil {
		t.Fatalf("client NATSConn: %v", err)
	}
	defer clientConn.Close()

	dialer, err := NewAgentDialer(clientConn, clientKey, logger)
	if err != nil {
		t.Fatalf("NewAgentDialer: %v", err)
	}
	// Wire an attachment store so requesting AttachmentCapability does not
	// fail at dial time. The host's NATSTransport doubles as the client-side
	// object-store source for this in-process test.
	dialer.WithAttachmentStore(hostT)

	ctx := t.Context()
	sess, err := dialer.Dial(ctx, DialParams{
		TargetUsername:   hostUser,
		HostPublicKeyB64: hostT.PublicKeyB64(),
		PeerChannel:      "key-test-channel",
		SatelliteToken:   "fake",
		Prompt:           "hi",
		EndpointSlug:     "agent1",
		Capabilities:     []string{syfthubapi.AttachmentCapability},
	})
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	defer sess.Close()

	// 1) Client-side: the session retained a 32-byte key.
	if got := len(sess.sessionAESKey); got != 32 {
		t.Fatalf("sess.sessionAESKey length = %d, want 32", got)
	}

	// 2) Wire: the start envelope must carry the same 32-byte key (base64).
	select {
	case <-gotCh:
	case <-time.After(2 * time.Second):
		t.Fatal("did not capture session_start envelope on host space subject")
	}
	mu.Lock()
	raw := captured
	mu.Unlock()

	var env syfthubapi.AgentEnvelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatalf("decode envelope: %v", err)
	}
	if env.Type != syfthubapi.MsgTypeAgentSessionStart {
		t.Fatalf("unexpected envelope type %q", env.Type)
	}

	// Decrypt with host's identity key + the client's sender pub from the envelope.
	cipher, err := NewSessionCipher(hostT.privateKey, env.SenderPublicKey, env.SessionID)
	if err != nil {
		t.Fatalf("NewSessionCipher (host side): %v", err)
	}
	pt, err := cipher.DecryptRequest(env.Nonce, env.EncryptedPayload, env.CorrelationID)
	if err != nil {
		t.Fatalf("decrypt session_start payload: %v", err)
	}
	var startPayload syfthubapi.AgentSessionStartPayload
	if err := json.Unmarshal(pt, &startPayload); err != nil {
		t.Fatalf("unmarshal session_start payload: %v", err)
	}
	if startPayload.SessionAttachmentKey == "" {
		t.Fatalf("dialer did not set SessionAttachmentKey on wire; payload=%+v", startPayload)
	}
	wireKey, err := base64.StdEncoding.DecodeString(startPayload.SessionAttachmentKey)
	if err != nil {
		t.Fatalf("decode wire session_attachment_key: %v", err)
	}
	if len(wireKey) != 32 {
		t.Fatalf("wire session_attachment_key length = %d, want 32", len(wireKey))
	}
	if string(wireKey) != string(sess.sessionAESKey) {
		t.Fatalf("wire key does not match in-memory session key")
	}
}

// TestDialDoesNotMintKeyWithoutAttachmentCapability — when the caller doesn't
// request the capability, the dialer should NOT mint a key (keeps sessions
// keyless when attachments aren't needed). Validated by inspecting the
// AgentClientSession's internal state.
func TestDialDoesNotMintKeyWithoutAttachmentCapability(t *testing.T) {
	srv := runEmbeddedNATS(t)
	defer srv.Shutdown()
	natsURL := srv.ClientURL()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	const hostUser = "hostcarol"
	hostCreds := &syfthubapi.NATSCredentials{URL: natsURL, Subject: spaceSubjectPrefix + hostUser}
	hostConn, err := NewNATSConn(hostCreds, "key-test-host2", logger)
	if err != nil {
		t.Fatalf("host NATSConn: %v", err)
	}
	defer hostConn.Close()
	hostT, err := NewNATSTransport(hostConn, &Config{
		SpaceURL:        "tunneling:" + hostUser,
		NATSCredentials: hostCreds,
		Logger:          logger,
	})
	if err != nil {
		t.Fatalf("NewNATSTransport: %v", err)
	}

	clientKey, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("client keypair: %v", err)
	}
	clientConn, err := NewNATSConn(&syfthubapi.NATSCredentials{URL: natsURL}, "key-test-client2", logger)
	if err != nil {
		t.Fatalf("client NATSConn: %v", err)
	}
	defer clientConn.Close()

	dialer, err := NewAgentDialer(clientConn, clientKey, logger)
	if err != nil {
		t.Fatalf("NewAgentDialer: %v", err)
	}
	sess, err := dialer.Dial(t.Context(), DialParams{
		TargetUsername:   hostUser,
		HostPublicKeyB64: hostT.PublicKeyB64(),
		PeerChannel:      "key-test-channel2",
		SatelliteToken:   "fake",
		Prompt:           "hi",
		EndpointSlug:     "agent1",
		// no Capabilities
	})
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	defer sess.Close()

	if sess.sessionAESKey != nil {
		t.Fatalf("expected nil sessionAESKey when AttachmentCapability not requested, got %d bytes", len(sess.sessionAESKey))
	}
}

// TestDialRequiresAttachmentStoreWhenCapabilityRequested asserts the dialer
// refuses to advertise AttachmentCapability when WithAttachmentStore was not
// called. Without this fail-closed check, the host accepts the session,
// allocates per-session attachment state, and the first object-store transfer
// blows up mid-stream with an opaque "dialer not configured" error after the
// chip has already been shown to the user as in-flight.
func TestDialRequiresAttachmentStoreWhenCapabilityRequested(t *testing.T) {
	srv := runEmbeddedNATS(t)
	defer srv.Shutdown()
	natsURL := srv.ClientURL()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	clientKey, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("client keypair: %v", err)
	}
	clientConn, err := NewNATSConn(&syfthubapi.NATSCredentials{URL: natsURL}, "key-test-client3", logger)
	if err != nil {
		t.Fatalf("client NATSConn: %v", err)
	}
	defer clientConn.Close()

	dialer, err := NewAgentDialer(clientConn, clientKey, logger)
	if err != nil {
		t.Fatalf("NewAgentDialer: %v", err)
	}
	// Deliberately do NOT call WithAttachmentStore.

	_, err = dialer.Dial(t.Context(), DialParams{
		TargetUsername:   "any",
		HostPublicKeyB64: base64.StdEncoding.EncodeToString(make([]byte, 32)),
		PeerChannel:      "ch",
		SatelliteToken:   "fake",
		Prompt:           "hi",
		EndpointSlug:     "agent1",
		Capabilities:     []string{syfthubapi.AttachmentCapability},
	})
	if err == nil {
		t.Fatalf("expected Dial to fail when AttachmentCapability is requested without WithAttachmentStore")
	}
}
