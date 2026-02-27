package transport

import (
	"crypto/ecdh"
	"encoding/json"
	"strings"
	"testing"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

// encryptRequestForTest simulates what the Python aggregator does to encrypt a
// tunnel request: generate an ephemeral keypair, ECDH with the space's long-term
// key, HKDF-SHA256 (request info), AES-256-GCM.
//
// Returns (encInfo, encPayloadB64, ephemeralPrivateKey).
// Callers retain the ephemeral private key to decrypt the response.
func encryptRequestForTest(t *testing.T, spacePublicKeyBytes []byte, payloadJSON, correlationID string) (*syfthubapi.EncryptionInfo, string, *ecdh.PrivateKey) {
	t.Helper()

	ephemeral, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("GenerateX25519Keypair: %v", err)
	}

	aesKey, err := deriveKey(ephemeral, spacePublicKeyBytes, hkdfRequestInfo)
	if err != nil {
		t.Fatalf("deriveKey: %v", err)
	}

	nonce, ciphertext, err := encryptPayload([]byte(payloadJSON), aesKey, []byte(correlationID))
	if err != nil {
		t.Fatalf("encryptPayload: %v", err)
	}

	encInfo := &syfthubapi.EncryptionInfo{
		Algorithm:          "X25519-ECDH-AES-256-GCM",
		EphemeralPublicKey: b64urlEncode(ephemeral.PublicKey().Bytes()),
		Nonce:              b64urlEncode(nonce),
	}
	return encInfo, b64urlEncode(ciphertext), ephemeral
}

// decryptResponseForTest simulates what the Python aggregator does to decrypt a
// tunnel response: ECDH(requestEphemeralPriv, responseEphemeralPub) + HKDF
// (response info) + AES-256-GCM.
func decryptResponseForTest(t *testing.T, encPayloadB64 string, encInfo *syfthubapi.EncryptionInfo, requestEphemeralPriv *ecdh.PrivateKey, correlationID string) string {
	t.Helper()

	respEphemeralPubBytes, err := b64urlDecode(encInfo.EphemeralPublicKey)
	if err != nil {
		t.Fatalf("b64urlDecode ephemeral_public_key: %v", err)
	}

	aesKey, err := deriveKey(requestEphemeralPriv, respEphemeralPubBytes, hkdfResponseInfo)
	if err != nil {
		t.Fatalf("deriveKey(response): %v", err)
	}

	nonce, err := b64urlDecode(encInfo.Nonce)
	if err != nil {
		t.Fatalf("b64urlDecode nonce: %v", err)
	}

	ciphertext, err := b64urlDecode(encPayloadB64)
	if err != nil {
		t.Fatalf("b64urlDecode ciphertext: %v", err)
	}

	plaintext, err := decryptPayload(ciphertext, aesKey, nonce, []byte(correlationID))
	if err != nil {
		t.Fatalf("decryptPayload: %v", err)
	}
	return string(plaintext)
}

// natsCfg returns a minimal valid Config for NATS transport tests.
func natsCfg() *Config {
	return &Config{
		SpaceURL: "tunneling:testuser",
		NATSCredentials: &syfthubapi.NATSCredentials{
			URL:     "wss://nats.example.com/nats",
			Token:   "test-token-12345678901234567890",
			Subject: "syfthub.spaces.testuser",
		},
	}
}

// ---------------------------------------------------------------------------
// GenerateX25519Keypair
// ---------------------------------------------------------------------------

func TestGenerateX25519Keypair(t *testing.T) {
	t.Run("generates valid 32-byte public key", func(t *testing.T) {
		key, err := GenerateX25519Keypair()
		if err != nil {
			t.Fatalf("GenerateX25519Keypair() error: %v", err)
		}
		if key == nil {
			t.Fatal("key is nil")
		}
		if len(key.PublicKey().Bytes()) != 32 {
			t.Fatalf("public key length = %d, want 32", len(key.PublicKey().Bytes()))
		}
	})

	t.Run("each call produces a unique key", func(t *testing.T) {
		k1, _ := GenerateX25519Keypair()
		k2, _ := GenerateX25519Keypair()
		if string(k1.PublicKey().Bytes()) == string(k2.PublicKey().Bytes()) {
			t.Fatal("two GenerateX25519Keypair() calls returned the same public key")
		}
	})
}

// ---------------------------------------------------------------------------
// b64url helpers
// ---------------------------------------------------------------------------

func TestB64urlRoundtrip(t *testing.T) {
	data := make([]byte, 256)
	for i := range data {
		data[i] = byte(i)
	}
	encoded := b64urlEncode(data)
	decoded, err := b64urlDecode(encoded)
	if err != nil {
		t.Fatalf("b64urlDecode error: %v", err)
	}
	if string(decoded) != string(data) {
		t.Fatal("b64url roundtrip did not produce original data")
	}
}

func TestB64urlNoPadding(t *testing.T) {
	encoded := b64urlEncode([]byte("hello"))
	if strings.Contains(encoded, "=") {
		t.Fatalf("b64urlEncode produced padding: %q", encoded)
	}
}

// ---------------------------------------------------------------------------
// DecryptTunnelRequest
// ---------------------------------------------------------------------------

func TestDecryptTunnelRequestRoundtrip(t *testing.T) {
	spacePriv, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("GenerateX25519Keypair: %v", err)
	}

	payload := `{"messages":"find documents","limit":5}`
	correlationID := "test-corr-id-roundtrip"

	encInfo, encPayloadB64, _ := encryptRequestForTest(t, spacePriv.PublicKey().Bytes(), payload, correlationID)

	plaintext, err := DecryptTunnelRequest(encPayloadB64, encInfo, spacePriv, correlationID)
	if err != nil {
		t.Fatalf("DecryptTunnelRequest error: %v", err)
	}
	if string(plaintext) != payload {
		t.Fatalf("DecryptTunnelRequest = %q, want %q", plaintext, payload)
	}
}

func TestDecryptTunnelRequestWrongKey(t *testing.T) {
	spacePriv, _ := GenerateX25519Keypair()
	wrongPriv, _ := GenerateX25519Keypair()

	encInfo, encPayloadB64, _ := encryptRequestForTest(t, spacePriv.PublicKey().Bytes(), `{"messages":"secret"}`, "test-wrong-key")

	_, err := DecryptTunnelRequest(encPayloadB64, encInfo, wrongPriv, "test-wrong-key")
	if err == nil {
		t.Fatal("DecryptTunnelRequest with wrong key should have returned an error")
	}
}

func TestDecryptTunnelRequestWrongCorrelationID(t *testing.T) {
	spacePriv, _ := GenerateX25519Keypair()

	encInfo, encPayloadB64, _ := encryptRequestForTest(t, spacePriv.PublicKey().Bytes(), `{"messages":"secret"}`, "real-corr-id")

	_, err := DecryptTunnelRequest(encPayloadB64, encInfo, spacePriv, "wrong-correlation-id")
	if err == nil {
		t.Fatal("DecryptTunnelRequest with wrong correlation_id should have returned an error")
	}
}

func TestDecryptTunnelRequestNilEncryptionInfo(t *testing.T) {
	spacePriv, _ := GenerateX25519Keypair()
	_, err := DecryptTunnelRequest("somepayload", nil, spacePriv, "id")
	if err == nil {
		t.Fatal("expected error for nil encryption_info")
	}
}

// ---------------------------------------------------------------------------
// EncryptTunnelResponse
// ---------------------------------------------------------------------------

func TestEncryptTunnelResponseRoundtrip(t *testing.T) {
	requestEphemeralPriv, err := GenerateX25519Keypair()
	if err != nil {
		t.Fatalf("GenerateX25519Keypair: %v", err)
	}

	payload := `{"summary":{"message":{"content":"Here are the results"}}}`
	correlationID := "test-corr-id-response"

	encInfo, encPayloadB64, err := EncryptTunnelResponse(
		[]byte(payload),
		b64urlEncode(requestEphemeralPriv.PublicKey().Bytes()),
		correlationID,
	)
	if err != nil {
		t.Fatalf("EncryptTunnelResponse error: %v", err)
	}

	recovered := decryptResponseForTest(t, encPayloadB64, encInfo, requestEphemeralPriv, correlationID)
	if recovered != payload {
		t.Fatalf("EncryptTunnelResponse roundtrip = %q, want %q", recovered, payload)
	}
}

func TestEncryptTunnelResponseEncryptsNull(t *testing.T) {
	requestEphemeralPriv, _ := GenerateX25519Keypair()
	correlationID := "test-corr-id-null"

	encInfo, encPayloadB64, err := EncryptTunnelResponse(
		[]byte("null"),
		b64urlEncode(requestEphemeralPriv.PublicKey().Bytes()),
		correlationID,
	)
	if err != nil {
		t.Fatalf("EncryptTunnelResponse(null) error: %v", err)
	}

	recovered := decryptResponseForTest(t, encPayloadB64, encInfo, requestEphemeralPriv, correlationID)
	if recovered != "null" {
		t.Fatalf("expected 'null', got %q", recovered)
	}
}

func TestEncryptTunnelResponseSetsAlgorithm(t *testing.T) {
	epk, _ := GenerateX25519Keypair()
	encInfo, _, err := EncryptTunnelResponse([]byte(`{}`), b64urlEncode(epk.PublicKey().Bytes()), "corr-id")
	if err != nil {
		t.Fatalf("EncryptTunnelResponse error: %v", err)
	}
	if encInfo.Algorithm != "X25519-ECDH-AES-256-GCM" {
		t.Fatalf("algorithm = %q, want X25519-ECDH-AES-256-GCM", encInfo.Algorithm)
	}
}

func TestEncryptTunnelResponseUniquePerCall(t *testing.T) {
	epk, _ := GenerateX25519Keypair()
	pubB64 := b64urlEncode(epk.PublicKey().Bytes())
	payload := []byte(`{"data":"same"}`)
	correlationID := "corr-id-unique"

	enc1, ct1, _ := EncryptTunnelResponse(payload, pubB64, correlationID)
	enc2, ct2, _ := EncryptTunnelResponse(payload, pubB64, correlationID)

	if enc1.EphemeralPublicKey == enc2.EphemeralPublicKey {
		t.Fatal("two EncryptTunnelResponse calls returned the same ephemeral public key")
	}
	if ct1 == ct2 {
		t.Fatal("two EncryptTunnelResponse calls returned the same ciphertext")
	}
}

// ---------------------------------------------------------------------------
// Domain separation
// ---------------------------------------------------------------------------

func TestDomainSeparation(t *testing.T) {
	// Deriving with hkdfRequestInfo vs hkdfResponseInfo from the same ECDH
	// shared secret must produce different 32-byte AES keys.
	priv, _ := GenerateX25519Keypair()
	peer, _ := GenerateX25519Keypair()

	reqKey, err := deriveKey(priv, peer.PublicKey().Bytes(), hkdfRequestInfo)
	if err != nil {
		t.Fatalf("deriveKey(request): %v", err)
	}
	respKey, err := deriveKey(priv, peer.PublicKey().Bytes(), hkdfResponseInfo)
	if err != nil {
		t.Fatalf("deriveKey(response): %v", err)
	}

	if string(reqKey) == string(respKey) {
		t.Fatal("request and response keys must differ (domain separation failure)")
	}
}

// ---------------------------------------------------------------------------
// NATSTransport keypair
// ---------------------------------------------------------------------------

func TestNATSTransportPublicKeyB64(t *testing.T) {
	transport, err := NewNATSTransport(natsCfg())
	if err != nil {
		t.Fatalf("NewNATSTransport error: %v", err)
	}

	pubKeyB64 := transport.PublicKeyB64()
	if pubKeyB64 == "" {
		t.Fatal("PublicKeyB64() returned empty string")
	}

	decoded, err := b64urlDecode(pubKeyB64)
	if err != nil {
		t.Fatalf("PublicKeyB64() is not valid base64url: %v", err)
	}
	if len(decoded) != 32 {
		t.Fatalf("decoded public key length = %d, want 32", len(decoded))
	}
}

func TestNATSTransportPublicKeyB64UniquePerInstance(t *testing.T) {
	t1, _ := NewNATSTransport(natsCfg())
	t2, _ := NewNATSTransport(natsCfg())

	if t1.PublicKeyB64() == t2.PublicKeyB64() {
		t.Fatal("two NATSTransport instances should have different X25519 keypairs")
	}
}

// ---------------------------------------------------------------------------
// Cross-language constant verification
// ---------------------------------------------------------------------------

// TestCrossLanguageConstants verifies that the Go implementation uses the exact
// same algorithm identifiers as the Python aggregator's crypto.py:
//   - HKDF_REQUEST_INFO  = b"syfthub-tunnel-request-v1"
//   - HKDF_RESPONSE_INFO = b"syfthub-tunnel-response-v1"
//   - NONCE_SIZE         = 12
//   - ALGORITHM_ID       = "X25519-ECDH-AES-256-GCM"
func TestCrossLanguageConstants(t *testing.T) {
	if string(hkdfRequestInfo) != "syfthub-tunnel-request-v1" {
		t.Errorf("hkdfRequestInfo = %q, want syfthub-tunnel-request-v1", hkdfRequestInfo)
	}
	if string(hkdfResponseInfo) != "syfthub-tunnel-response-v1" {
		t.Errorf("hkdfResponseInfo = %q, want syfthub-tunnel-response-v1", hkdfResponseInfo)
	}
	if nonceSize != 12 {
		t.Errorf("nonceSize = %d, want 12", nonceSize)
	}

	epk, _ := GenerateX25519Keypair()
	encInfo, _, err := EncryptTunnelResponse([]byte("{}"), b64urlEncode(epk.PublicKey().Bytes()), "algo-check")
	if err != nil {
		t.Fatalf("EncryptTunnelResponse: %v", err)
	}
	if encInfo.Algorithm != "X25519-ECDH-AES-256-GCM" {
		t.Errorf("algorithm = %q, want X25519-ECDH-AES-256-GCM", encInfo.Algorithm)
	}
}

// ---------------------------------------------------------------------------
// Full pipeline roundtrip
// ---------------------------------------------------------------------------

// TestFullPipelineRoundtrip verifies the complete request+response pipeline:
// (aggregator) encrypt request → (space) decrypt → (space) encrypt response → (aggregator) decrypt.
func TestFullPipelineRoundtrip(t *testing.T) {
	// Space's long-term keypair (generated in NewNATSTransport)
	spacePriv, _ := GenerateX25519Keypair()

	requestPayload := json.RawMessage(`{"messages":"what is syfthub?","limit":3}`)
	responsePayload := json.RawMessage(`{"summary":{"message":{"content":"SyftHub is a platform"}}}`)
	correlationID := "full-pipeline-test"

	// --- Request path ---
	// Aggregator encrypts request; encryptRequestForTest returns the ephemeral private key
	// that the aggregator retains to decrypt the response.
	encInfo, encPayloadB64, aggEphemeralPriv := encryptRequestForTest(
		t, spacePriv.PublicKey().Bytes(), string(requestPayload), correlationID,
	)

	// Space (Go SDK) decrypts request using its long-term private key
	decryptedPayload, err := DecryptTunnelRequest(encPayloadB64, encInfo, spacePriv, correlationID)
	if err != nil {
		t.Fatalf("Space DecryptTunnelRequest: %v", err)
	}
	if string(decryptedPayload) != string(requestPayload) {
		t.Fatalf("request decrypt mismatch: got %q, want %q", decryptedPayload, requestPayload)
	}

	// --- Response path ---
	// Space (Go SDK) encrypts response using the aggregator's ephemeral public key from encInfo.
	respEncInfo, respEncPayloadB64, err := EncryptTunnelResponse(
		responsePayload,
		encInfo.EphemeralPublicKey, // aggregator's ephemeral public key
		correlationID,
	)
	if err != nil {
		t.Fatalf("Space EncryptTunnelResponse: %v", err)
	}

	// Aggregator decrypts response using its retained ephemeral private key.
	recovered := decryptResponseForTest(t, respEncPayloadB64, respEncInfo, aggEphemeralPriv, correlationID)
	if recovered != string(responsePayload) {
		t.Fatalf("response decrypt mismatch: got %q, want %q", recovered, responsePayload)
	}
}
