package transport

// KAT (Known-Answer-Test) vectors for the v2 identity-keyed agent session
// crypto (SessionCipher) and the v1 ephemeral tunnel crypto (decrypt
// direction).
//
// Purpose: pin the wire format produced by SessionCipher.EncryptRequest /
// EncryptResponse and the decryption format consumed by DecryptTunnelRequest,
// so any future refactor (e.g., moving primitives into internal/cryptocore)
// can be proven byte-identical to current main.
//
// Inputs:
//   host_priv_seed   = 32 bytes of 0x11
//   caller_priv_seed = 32 bytes of 0x22
//   session_id       = "sess-fixed-1234"
//   correlation      = "corr-fixed-77"
//   nonce            = 12 bytes of 0x33
//   plaintext_req    = `{"status":"approved","response_text":"x"}` (req direction)
//   plaintext_resp   = `{"status":"approved","response_text":"x"}` (resp direction)
//
// For v1 tunnel: the request side uses an ephemeral keypair generated on every
// call, so we KAT the DECRYPT direction with a pre-recorded ciphertext built
// against fixed ephemeral seeds.

import (
	"bytes"
	"crypto/ecdh"
	"encoding/base64"
	"encoding/hex"
	"testing"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/internal/cryptocore"
)

// Fixed test inputs.
var (
	katHostPrivSeed    = bytes.Repeat([]byte{0x11}, 32)
	katCallerPrivSeed  = bytes.Repeat([]byte{0x22}, 32)
	katEphemeralSeed   = bytes.Repeat([]byte{0x44}, 32) // used for v1 tunnel KAT
	katSpacePrivSeed   = bytes.Repeat([]byte{0x55}, 32) // space long-term key, v1 tunnel
	katSessionID       = "sess-fixed-1234"
	katCorrelation     = "corr-fixed-77"
	katNonce           = bytes.Repeat([]byte{0x33}, 12)
	katPlaintext       = []byte(`{"status":"approved","response_text":"x"}`)
	katTunnelPlaintext = []byte(`{"messages":"find documents","limit":5}`)
)

// Expected pinned wire bytes for v2 session cipher (request + response).
const (
	// v2 request direction: client encrypts → host decrypts.
	katExpectedReqNonceB64 = "MzMzMzMzMzMzMzMz"
	katExpectedReqCtB64    = "KyIayk9SdwagmsBGdTdIkwlFrjphMMBPmSpfVcpelSHMyYJhixfy54oUxqjtY7IL84mPHyyPmEGQ"

	// v2 response direction: host encrypts → client decrypts.
	katExpectedRespNonceB64 = "MzMzMzMzMzMzMzMz"
	katExpectedRespCtB64    = "LXGxn94zl9blMZ6FI3Fe1k4WcOrKU2mdZjZ3EtR354-VhFYWYdXa0OdNF35OapfOR1KjQZSPg9Xr"

	// v1 tunnel request (decrypt direction).
	// Built against ephemeral seed 0x44 and space priv seed 0x55, correlation
	// "corr-fixed-77", nonce all-0x33, plaintext katTunnelPlaintext.
	katExpectedV1TunnelCtB64 = "xyeLFwWRy_dWGEeuej5m_ZlvAZotRJ5W0TN-ZIC6huIKVy0AK316vAG87X_Y12tvhCHSYlQKiw"
)

func katKey(t *testing.T, seed []byte) *ecdh.PrivateKey {
	t.Helper()
	k, err := ecdh.X25519().NewPrivateKey(seed)
	if err != nil {
		t.Fatalf("NewPrivateKey: %v", err)
	}
	return k
}

// TestKAT_SessionCipher_Request pins the v2 client→host wire bytes.
func TestKAT_SessionCipher_Request(t *testing.T) {
	client := katKey(t, katCallerPrivSeed)
	host := katKey(t, katHostPrivSeed)
	hostPubB64 := base64.RawURLEncoding.EncodeToString(host.PublicKey().Bytes())
	clientPubB64 := base64.RawURLEncoding.EncodeToString(client.PublicKey().Bytes())

	clientCipher, err := NewSessionCipher(client, hostPubB64, katSessionID)
	if err != nil {
		t.Fatalf("client cipher: %v", err)
	}
	ct := clientCipher.reqAEAD.Seal(nil, katNonce, katPlaintext, []byte(katCorrelation))
	gotNonceB64 := base64.RawURLEncoding.EncodeToString(katNonce)
	gotCtB64 := base64.RawURLEncoding.EncodeToString(ct)

	if katExpectedReqNonceB64 == "" || katExpectedReqCtB64 == "" {
		t.Logf("KAT capture (v2 req):\n  nonce_b64      = %q\n  ciphertext_b64 = %q\n  ciphertext_hex = %s",
			gotNonceB64, gotCtB64, hex.EncodeToString(ct))
		t.Fatal("KAT req constants empty — paste the logged values")
	}
	if gotNonceB64 != katExpectedReqNonceB64 {
		t.Errorf("req nonce mismatch:\n  got  = %q\n  want = %q", gotNonceB64, katExpectedReqNonceB64)
	}
	if gotCtB64 != katExpectedReqCtB64 {
		t.Errorf("req ciphertext mismatch:\n  got  = %q\n  want = %q", gotCtB64, katExpectedReqCtB64)
	}

	// Production decrypt must accept the pinned ciphertext.
	hostCipher, err := NewSessionCipher(host, clientPubB64, katSessionID)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}
	got, err := hostCipher.DecryptRequest(katExpectedReqNonceB64, katExpectedReqCtB64, katCorrelation)
	if err != nil {
		t.Fatalf("DecryptRequest against pinned ciphertext: %v", err)
	}
	if !bytes.Equal(got, katPlaintext) {
		t.Errorf("decrypted req = %q, want %q", got, katPlaintext)
	}
}

// TestKAT_SessionCipher_Response pins the v2 host→client wire bytes.
func TestKAT_SessionCipher_Response(t *testing.T) {
	client := katKey(t, katCallerPrivSeed)
	host := katKey(t, katHostPrivSeed)
	hostPubB64 := base64.RawURLEncoding.EncodeToString(host.PublicKey().Bytes())
	clientPubB64 := base64.RawURLEncoding.EncodeToString(client.PublicKey().Bytes())

	hostCipher, err := NewSessionCipher(host, clientPubB64, katSessionID)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}
	ct := hostCipher.respAEAD.Seal(nil, katNonce, katPlaintext, []byte(katCorrelation))
	gotNonceB64 := base64.RawURLEncoding.EncodeToString(katNonce)
	gotCtB64 := base64.RawURLEncoding.EncodeToString(ct)

	if katExpectedRespNonceB64 == "" || katExpectedRespCtB64 == "" {
		t.Logf("KAT capture (v2 resp):\n  nonce_b64      = %q\n  ciphertext_b64 = %q\n  ciphertext_hex = %s",
			gotNonceB64, gotCtB64, hex.EncodeToString(ct))
		t.Fatal("KAT resp constants empty — paste the logged values")
	}
	if gotNonceB64 != katExpectedRespNonceB64 {
		t.Errorf("resp nonce mismatch:\n  got  = %q\n  want = %q", gotNonceB64, katExpectedRespNonceB64)
	}
	if gotCtB64 != katExpectedRespCtB64 {
		t.Errorf("resp ciphertext mismatch:\n  got  = %q\n  want = %q", gotCtB64, katExpectedRespCtB64)
	}

	clientCipher, err := NewSessionCipher(client, hostPubB64, katSessionID)
	if err != nil {
		t.Fatalf("client cipher: %v", err)
	}
	got, err := clientCipher.DecryptResponse(katExpectedRespNonceB64, katExpectedRespCtB64, katCorrelation)
	if err != nil {
		t.Fatalf("DecryptResponse against pinned ciphertext: %v", err)
	}
	if !bytes.Equal(got, katPlaintext) {
		t.Errorf("decrypted resp = %q, want %q", got, katPlaintext)
	}
}

// TestKAT_V1Tunnel_Decrypt pins the v1 tunnel decrypt path.
//
// We build a ciphertext with fixed ephemeral key, fixed space key, fixed
// nonce, fixed plaintext, and verify DecryptTunnelRequest produces the
// expected plaintext. Then we record the ciphertext bytes so any change to
// the v1 HKDF/AEAD scheme is caught.
func TestKAT_V1Tunnel_Decrypt(t *testing.T) {
	ephemeral := katKey(t, katEphemeralSeed)
	spacePriv := katKey(t, katSpacePrivSeed)

	// Build ciphertext using the v1 primitives directly (deriveKey +
	// aead.Seal with fixed nonce). This is the exact path
	// encryptPayload/DecryptTunnelRequest exercise, just with a fixed nonce
	// for reproducibility.
	aesKey, err := deriveKey(ephemeral, spacePriv.PublicKey().Bytes(), hkdfRequestInfo)
	if err != nil {
		t.Fatalf("deriveKey: %v", err)
	}
	gcm, err := cryptocore.NewAESGCM(aesKey)
	if err != nil {
		t.Fatalf("NewAESGCM: %v", err)
	}
	ct := gcm.Seal(nil, katNonce, katTunnelPlaintext, []byte(katCorrelation))
	gotCtB64 := base64.RawURLEncoding.EncodeToString(ct)

	if katExpectedV1TunnelCtB64 == "" {
		t.Logf("KAT capture (v1 tunnel decrypt):\n  ciphertext_b64 = %q\n  ciphertext_hex = %s",
			gotCtB64, hex.EncodeToString(ct))
		t.Fatal("KAT v1 tunnel constant empty — paste the logged value")
	}
	if gotCtB64 != katExpectedV1TunnelCtB64 {
		t.Errorf("v1 tunnel ciphertext mismatch:\n  got  = %q\n  want = %q", gotCtB64, katExpectedV1TunnelCtB64)
	}

	// Now verify the production DecryptTunnelRequest accepts these bytes.
	encInfo := &syfthubapi.EncryptionInfo{
		Algorithm:          "X25519-ECDH-AES-256-GCM",
		EphemeralPublicKey: base64.RawURLEncoding.EncodeToString(ephemeral.PublicKey().Bytes()),
		Nonce:              base64.RawURLEncoding.EncodeToString(katNonce),
	}
	plaintext, err := DecryptTunnelRequest(katExpectedV1TunnelCtB64, encInfo, spacePriv, katCorrelation)
	if err != nil {
		t.Fatalf("DecryptTunnelRequest against pinned ciphertext: %v", err)
	}
	if !bytes.Equal(plaintext, katTunnelPlaintext) {
		t.Errorf("decrypted = %q, want %q", plaintext, katTunnelPlaintext)
	}
}
