package transport

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/base64"
	"io"
	"log/slog"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// TestObjectStoreUploaderBindsToSessionAttachmentKey simulates the
// agentNATSBridge.handleSessionStart key-extraction + uploader-binding
// branch without spinning up a real NATS server.
//
// The handshake invariant: the aggregator generates a 32-byte
// session_attachment_key and transmits it (base64) in the encrypted
// session_start payload. The HOST decodes it, constructs an
// AttachmentEncryptor over that key, and produces wrapped per-file keys
// that the aggregator (with the same session key) can unwrap.
func TestObjectStoreUploaderBindsToSessionAttachmentKey(t *testing.T) {
	rawKey := make([]byte, 32)
	if _, err := rand.Read(rawKey); err != nil {
		t.Fatal(err)
	}
	keyB64 := base64.StdEncoding.EncodeToString(rawKey)

	payload := syfthubapi.AgentSessionStartPayload{
		SessionID:            "sess-handshake",
		EndpointSlug:         "ep",
		Capabilities:         []string{syfthubapi.AttachmentCapability},
		SessionAttachmentKey: keyB64,
	}
	if !payload.HasCapability(syfthubapi.AttachmentCapability) {
		t.Fatal("expected attachments capability")
	}

	decoded, err := base64.StdEncoding.DecodeString(payload.SessionAttachmentKey)
	if err != nil || len(decoded) != 32 {
		t.Fatalf("decode session_attachment_key: %v len=%d", err, len(decoded))
	}

	store := NewMemoryAttachmentObjectStore()
	uploader, err := NewObjectStoreUploader(context.Background(), decoded, store, payload.SessionID)
	if err != nil {
		t.Fatalf("NewObjectStoreUploader: %v", err)
	}

	// Aggregator-side decryption uses the SAME key derived locally — the
	// AttachmentEncryptor wraps under HKDF-derived sub-keys, so we verify
	// round-trip identity here.
	aggrEnc, err := NewAttachmentEncryptor(decoded)
	if err != nil {
		t.Fatal(err)
	}

	// Use the uploader to wrap a per-file key, then have the aggregator-
	// side encryptor unwrap it. Cross-side keying succeeds.
	body := []byte("handshake body")
	info, err := uploader.Upload(context.Background(), "att-handshake", "x.txt", "text/plain", -1, bytes.NewReader(body))
	if err != nil {
		t.Fatalf("Upload: %v", err)
	}

	wrappedCT, err := base64.StdEncoding.DecodeString(info.WrappedKey.Ciphertext)
	if err != nil {
		t.Fatal(err)
	}
	wrappedNonce, err := base64.StdEncoding.DecodeString(info.WrappedKey.Nonce)
	if err != nil {
		t.Fatal(err)
	}

	if _, err := aggrEnc.UnwrapFileKey(info.FileID, wrappedCT, wrappedNonce); err != nil {
		t.Fatalf("aggregator failed to unwrap with the same session key: %v", err)
	}
}

// attachmentAckHandler is an AgentSessionHandler that registers a real
// AgentSession with attachments enabled so the host-side agentNATSBridge can
// look it up via GetSession and route an inbound user attachment to it.
type attachmentAckHandler struct {
	mu       sync.Mutex
	sessions map[string]*syfthubapi.AgentSession
}

func newAttachmentAckHandler() *attachmentAckHandler {
	return &attachmentAckHandler{sessions: make(map[string]*syfthubapi.AgentSession)}
}

func (h *attachmentAckHandler) StartSession(payload syfthubapi.AgentSessionStartPayload, user *syfthubapi.UserContext) (*syfthubapi.AgentSession, error) {
	dir, err := os.MkdirTemp("", "syft-attach-ack-*")
	if err != nil {
		return nil, err
	}
	sess := syfthubapi.NewAgentSession(context.Background(), syfthubapi.AgentSessionParams{
		ID:            payload.SessionID,
		Prompt:        payload.Prompt,
		EndpointSlug:  payload.EndpointSlug,
		User:          user,
		Capabilities:  payload.Capabilities,
		AttachmentDir: dir,
	})
	// The handler drains the attachment channel and otherwise blocks until
	// the test cancels the session — this keeps the session alive long
	// enough for the bridge to deliver an attachment and emit the ack.
	sess.RunHandler(func(ctx context.Context, s *syfthubapi.AgentSession) error {
		ch := s.AttachmentCh()
		for {
			select {
			case <-ctx.Done():
				return nil
			case <-ch:
				// drain — we only care that the host got far enough to deliver
			}
		}
	})
	h.mu.Lock()
	h.sessions[sess.ID] = sess
	h.mu.Unlock()
	return sess, nil
}

func (h *attachmentAckHandler) RouteMessage(syfthubapi.AgentUserMessagePayload) error { return nil }
func (h *attachmentAckHandler) CancelSession(string) error                            { return nil }
func (h *attachmentAckHandler) GetSession(id string) (*syfthubapi.AgentSession, bool) {
	h.mu.Lock()
	defer h.mu.Unlock()
	s, ok := h.sessions[id]
	return s, ok
}

// TestHandleUserAttachmentEmitsAck spins up the embedded NATS server + the
// agentNATSBridge, dials a session with the attachments capability, publishes
// an inline attachment from the client, and asserts that the host emits a
// user.attachment accept-ack event carrying the original file_id and size.
func TestHandleUserAttachmentEmitsAck(t *testing.T) {
	srv := runEmbeddedNATS(t)
	defer srv.Shutdown()
	natsURL := srv.ClientURL()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))

	const hostUser = "hostack"
	hostCreds := &syfthubapi.NATSCredentials{URL: natsURL, Subject: spaceSubjectPrefix + hostUser}

	hostConn, err := NewNATSConn(hostCreds, "ack-host", logger)
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
	handler := newAttachmentAckHandler()
	hostT.SetAgentHandler(handler)
	hostT.SetTokenVerifier(func(_ context.Context, _ string) (*syfthubapi.UserContext, error) {
		return &syfthubapi.UserContext{Sub: "u1", Username: hostUser, Role: "user"}, nil
	})

	ctx := t.Context()
	go func() { _ = hostT.Start(ctx) }()
	defer func() { _ = hostT.Stop(context.Background()) }()

	// Wait for the host subscription to register on the server before the
	// client publishes anything.
	time.Sleep(200 * time.Millisecond)

	clientKey, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("client keypair: %v", err)
	}
	clientConn, err := NewNATSConn(&syfthubapi.NATSCredentials{URL: natsURL}, "ack-client", logger)
	if err != nil {
		t.Fatalf("client NATSConn: %v", err)
	}
	defer clientConn.Close()

	dialer, err := NewAgentDialer(clientConn, clientKey, logger)
	if err != nil {
		t.Fatalf("NewAgentDialer: %v", err)
	}
	// AttachmentCapability now requires a wired object store; reuse the
	// host transport's store handle for this in-process integration test.
	dialer.WithAttachmentStore(hostT)

	sess, err := dialer.Dial(ctx, DialParams{
		TargetUsername:   hostUser,
		HostPublicKeyB64: hostT.PublicKeyB64(),
		PeerChannel:      "ack-channel",
		SatelliteToken:   "fake-satellite-token",
		Prompt:           "hello host",
		EndpointSlug:     "agent-ack",
		Capabilities:     []string{syfthubapi.AttachmentCapability},
	})
	if err != nil {
		t.Fatalf("Dial: %v", err)
	}
	defer sess.Close()

	// Give the host a moment to process session_start and register the
	// session in the handler map (needed before GetSession can resolve it).
	time.Sleep(200 * time.Millisecond)

	body := []byte("ack-me-please")
	info, err := sess.SendAttachmentBytes(ctx, body, AttachmentOpts{Name: "note.txt", MIME: "text/plain"})
	if err != nil {
		t.Fatalf("SendAttachmentBytes: %v", err)
	}

	timeout := time.After(10 * time.Second)
	var ack *agenttypes.UserAttachmentEvent
collect:
	for {
		select {
		case ev, ok := <-sess.Events():
			if !ok {
				break collect
			}
			if e, ok := ev.(*agenttypes.UserAttachmentEvent); ok {
				ack = e
				break collect
			}
		case <-timeout:
			t.Fatalf("timed out waiting for user.attachment ack")
		}
	}

	if ack == nil {
		t.Fatal("did not receive user.attachment ack event")
	}
	if ack.FileID != info.FileID {
		t.Errorf("ack file_id mismatch: got %q, want %q", ack.FileID, info.FileID)
	}
	if ack.SizeBytes != int64(len(body)) {
		t.Errorf("ack size_bytes mismatch: got %d, want %d", ack.SizeBytes, len(body))
	}
}
