package manualreview

import (
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"testing"
)

func mustGenKey(t *testing.T) *ecdh.PrivateKey {
	t.Helper()
	k, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	return k
}

func pubB64(k *ecdh.PrivateKey) string {
	return base64.RawURLEncoding.EncodeToString(k.PublicKey().Bytes())
}

// Host encrypts → caller decrypts. The whole point of the package.
func TestCipher_CrossPartyRoundTrip(t *testing.T) {
	host := mustGenKey(t)
	caller := mustGenKey(t)
	const reviewID = "ab12cd34ef56"

	hostSide, err := NewResolutionCipher(host, pubB64(caller), reviewID)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}
	callerSide, err := NewResolutionCipher(caller, pubB64(host), reviewID)
	if err != nil {
		t.Fatalf("caller cipher: %v", err)
	}

	plaintext := []byte(`{"status":"approved","response_text":"the real held answer"}`)
	nonce, ct, err := hostSide.Seal(plaintext, reviewID)
	if err != nil {
		t.Fatalf("seal: %v", err)
	}

	got, err := callerSide.Open(nonce, ct, reviewID)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if string(got) != string(plaintext) {
		t.Errorf("decrypted = %q, want %q", got, plaintext)
	}
}

// A ciphertext for one review_id must NOT decrypt under another review_id —
// review_id is both the HKDF salt (so keys differ) AND the GCM AAD (so even
// if keys somehow matched, the tag would fail).
func TestCipher_ReviewIDBoundToCiphertext(t *testing.T) {
	host := mustGenKey(t)
	caller := mustGenKey(t)

	c1, _ := NewResolutionCipher(host, pubB64(caller), "rev-one")
	c2, _ := NewResolutionCipher(caller, pubB64(host), "rev-two")

	nonce, ct, err := c1.Seal([]byte("payload"), "rev-one")
	if err != nil {
		t.Fatalf("seal: %v", err)
	}

	if _, err := c2.Open(nonce, ct, "rev-two"); err == nil {
		t.Fatal("expected decryption failure for a different review_id")
	}
}

// Tampering with the ciphertext flips the AEAD tag — Open must reject.
func TestCipher_TamperingDetected(t *testing.T) {
	host := mustGenKey(t)
	caller := mustGenKey(t)
	const reviewID = "ab12cd34ef56"

	hostSide, _ := NewResolutionCipher(host, pubB64(caller), reviewID)
	callerSide, _ := NewResolutionCipher(caller, pubB64(host), reviewID)

	nonce, ct, _ := hostSide.Seal([]byte("payload"), reviewID)
	tampered, err := base64.RawURLEncoding.DecodeString(ct)
	if err != nil {
		t.Fatalf("decode ct: %v", err)
	}
	tampered[0] ^= 0x01
	tamperedB64 := base64.RawURLEncoding.EncodeToString(tampered)

	if _, err := callerSide.Open(nonce, tamperedB64, reviewID); err == nil {
		t.Fatal("expected decryption failure on tampered ciphertext")
	}
}

func TestCipher_RejectsBadInputs(t *testing.T) {
	host := mustGenKey(t)
	caller := mustGenKey(t)

	if _, err := NewResolutionCipher(nil, pubB64(caller), "rid"); err == nil {
		t.Error("expected error for nil identity key")
	}
	if _, err := NewResolutionCipher(host, pubB64(caller), ""); err == nil {
		t.Error("expected error for empty review id")
	}
	if _, err := NewResolutionCipher(host, "not-base64!!!", "rid"); err == nil {
		t.Error("expected error for invalid pubkey")
	}
}
