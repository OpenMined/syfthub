package manualreview

// KAT (Known-Answer-Test) vectors for ResolutionCipher.
//
// Purpose: pin the wire format produced by Seal()/accepted by Open() against
// known-fixed inputs so any future refactor (e.g., moving primitives into the
// internal/cryptocore package) can be proven byte-identical.
//
// Inputs:
//   host_priv_seed   = 32 bytes of 0x11
//   caller_priv_seed = 32 bytes of 0x22
//   review_id        = "ab12cd34ef56"
//   nonce            = 12 bytes of 0x33
//   plaintext        = `{"status":"approved","response_text":"x"}`
//
// The expected ciphertext was captured by running the (then-current) primitives
// once with the fixed nonce. Any change to AES key derivation (HKDF salt/info),
// AEAD construction, or AAD binding will fail this test.

import (
	"bytes"
	"crypto/ecdh"
	"encoding/base64"
	"encoding/hex"
	"testing"
)

// Fixed test inputs.
var (
	katHostPrivSeed   = bytes.Repeat([]byte{0x11}, 32)
	katCallerPrivSeed = bytes.Repeat([]byte{0x22}, 32)
	katReviewID       = "ab12cd34ef56"
	katNonce          = bytes.Repeat([]byte{0x33}, 12)
	katPlaintext      = []byte(`{"status":"approved","response_text":"x"}`)
)

// Expected wire bytes (pinned). Empty initially; filled in via the capture
// phase below. Values are base64url-no-padding to mirror Seal's output.
const (
	katExpectedNonceB64      = "MzMzMzMzMzMzMzMz"
	katExpectedCiphertextB64 = "tucVxlaimAeJs18moq7dL_9q9j0uHuHAMOpK0oiXcZ4z1qFOZB6OSUftquShi_oBX6PZHrOH25nE"
)

func mustKey(t *testing.T, seed []byte) *ecdh.PrivateKey {
	t.Helper()
	k, err := ecdh.X25519().NewPrivateKey(seed)
	if err != nil {
		t.Fatalf("NewPrivateKey: %v", err)
	}
	return k
}

// TestKAT_ResolutionCipher_SealOpen pins the production wire format.
//
// The first time this test is run on UNREFACTORED code, the katExpected*
// constants above should be the empty string — the test prints the values it
// produced via t.Logf, the developer pastes them in, and from then on the
// test asserts byte-equality.
func TestKAT_ResolutionCipher_SealOpen(t *testing.T) {
	host := mustKey(t, katHostPrivSeed)
	caller := mustKey(t, katCallerPrivSeed)
	callerPubB64 := base64.RawURLEncoding.EncodeToString(caller.PublicKey().Bytes())
	hostPubB64 := base64.RawURLEncoding.EncodeToString(host.PublicKey().Bytes())

	// Build the host cipher and directly call the underlying AEAD with the
	// fixed nonce to produce deterministic ciphertext. We don't go through
	// Seal() because Seal generates a random nonce; the goal is to prove the
	// AEAD/HKDF derivation is byte-identical to the pinned values.
	hostCipher, err := NewResolutionCipher(host, callerPubB64, katReviewID)
	if err != nil {
		t.Fatalf("host cipher: %v", err)
	}
	ct := hostCipher.aead.Seal(nil, katNonce, katPlaintext, []byte(katReviewID))

	gotNonceB64 := base64.RawURLEncoding.EncodeToString(katNonce)
	gotCtB64 := base64.RawURLEncoding.EncodeToString(ct)

	// Capture phase: if the expected constants are empty, log what we
	// produced so the developer can paste them in.
	if katExpectedNonceB64 == "" || katExpectedCiphertextB64 == "" {
		t.Logf("KAT capture:\n  nonce_b64      = %q\n  ciphertext_b64 = %q\n  ciphertext_hex = %s",
			gotNonceB64, gotCtB64, hex.EncodeToString(ct))
		t.Fatal("KAT constants empty — paste the logged values into katExpectedNonceB64 and katExpectedCiphertextB64")
	}

	if gotNonceB64 != katExpectedNonceB64 {
		t.Errorf("nonce_b64 mismatch:\n  got  = %q\n  want = %q", gotNonceB64, katExpectedNonceB64)
	}
	if gotCtB64 != katExpectedCiphertextB64 {
		t.Errorf("ciphertext_b64 mismatch:\n  got  = %q\n  want = %q", gotCtB64, katExpectedCiphertextB64)
	}

	// Verify the production Open path accepts the pinned ciphertext.
	callerCipher, err := NewResolutionCipher(caller, hostPubB64, katReviewID)
	if err != nil {
		t.Fatalf("caller cipher: %v", err)
	}
	got, err := callerCipher.Open(katExpectedNonceB64, katExpectedCiphertextB64, katReviewID)
	if err != nil {
		t.Fatalf("Open against pinned ciphertext: %v", err)
	}
	if !bytes.Equal(got, katPlaintext) {
		t.Errorf("decrypted = %q, want %q", got, katPlaintext)
	}
}
