package transport

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/base64"
	"testing"

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
	info, err := uploader.Upload("att-handshake", "x.txt", "text/plain", -1, bytes.NewReader(body))
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
