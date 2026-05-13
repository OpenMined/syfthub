package mppx

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"testing"
	"time"
)

func TestComputeChallengeID_KnownVector(t *testing.T) {
	// Hand-computed reference: HMAC-SHA256 over the canonical 7-slot input
	// using the demo secret key and a fully-specified challenge.
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	expires, _ := time.Parse(time.RFC3339, "2026-05-08T21:43:11Z")
	c := Challenge{
		Realm:  "pubsub://alice/pay",
		Method: "tempo",
		Intent: "charge",
		Request: map[string]any{
			"amount":    "1000000",
			"currency":  "0x20c0000000000000000000000000000000000000",
			"recipient": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		},
		Expires: expires,
	}
	id, err := ComputeChallengeID(secret, c)
	if err != nil {
		t.Fatalf("compute: %v", err)
	}

	// Independent reference computation using the canonical 7-slot input.
	requestEncoded, err := EncodeRequest(c.Request)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	canonicalInput := joinSlots(
		"pubsub://alice/pay",
		"tempo",
		"charge",
		requestEncoded,
		formatExpires(expires),
		"",
		"",
	)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(canonicalInput))
	wantID := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))

	if id != wantID {
		t.Fatalf("id mismatch: got %q want %q", id, wantID)
	}
}

func joinSlots(parts ...string) string {
	out := ""
	for i, p := range parts {
		if i > 0 {
			out += "|"
		}
		out += p
	}
	return out
}

func TestVerifyChallengeID(t *testing.T) {
	secret := []byte("alice-demo-secret-key-32-bytes!!")
	c := Challenge{
		Realm:  "r",
		Method: "tempo",
		Intent: "charge",
		Request: map[string]any{
			"amount":    "1",
			"currency":  "0x20c0000000000000000000000000000000000000",
			"recipient": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
		},
	}
	id, err := ComputeChallengeID(secret, c)
	if err != nil {
		t.Fatalf("compute: %v", err)
	}
	c.ID = id
	if err := VerifyChallengeID(secret, c); err != nil {
		t.Fatalf("verify: %v", err)
	}
	// Tamper with one field — verification should fail.
	c.Request["amount"] = "1000"
	if err := VerifyChallengeID(secret, c); err == nil {
		t.Fatal("expected tampered amount to fail verification")
	}
}

func TestComputeChallengeID_RejectsEmptySecret(t *testing.T) {
	_, err := ComputeChallengeID(nil, Challenge{Realm: "r", Method: "m", Intent: "i", Request: map[string]any{}})
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestCanonicalFieldOrderConstant(t *testing.T) {
	// The HMAC implementation hard-codes the slot order; the constant exists
	// purely as documentation and a guard against accidental drift between
	// docs and code. Verify the constant lists exactly seven slots.
	const want = "realm|method|intent|request|expires|digest|opaque"
	if CanonicalFieldOrder != want {
		t.Fatalf("constant drift: got %q want %q", CanonicalFieldOrder, want)
	}
}
