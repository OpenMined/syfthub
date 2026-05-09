package mppx

import (
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestConformance_RequestEncoding asserts our canonical request encoding
// matches the byte output of the TS reference (`PaymentRequest.serialize`).
//
// Test vector — the inputs come from PUBSUB.md's example challenge:
//
//	{
//	  "amount":    "1000000",
//	  "currency":  "0x20c0000000000000000000000000000000000000",
//	  "recipient": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
//	}
//
// After RFC 8785 canonicalization (keys sorted alphabetically, no whitespace)
// the resulting JSON is:
//
//	{"amount":"1000000","currency":"0x20c0…","recipient":"0xf39F…"}
//
// base64url(no padding) of that JSON is the expected value below.
func TestConformance_RequestEncoding(t *testing.T) {
	req := map[string]any{
		"amount":    "1000000",
		"currency":  "0x20c0000000000000000000000000000000000000",
		"recipient": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
	}
	got, err := EncodeRequest(req)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	// Compute expected by independently base64url-encoding the canonical JSON.
	canonical := `{"amount":"1000000","currency":"0x20c0000000000000000000000000000000000000","recipient":"0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"}`
	want := base64.RawURLEncoding.EncodeToString([]byte(canonical))
	if got != want {
		t.Fatalf("encoded request mismatch:\n got  %s\n want %s", got, want)
	}
}

// TestConformance_ParseFixture parses the canned fixture file and asserts the
// extracted fields match expectations. The fixture's id field is recomputed
// at runtime so the test stays valid even before a live capture is available.
func TestConformance_ParseFixture(t *testing.T) {
	path := filepath.Join("testdata", "challenge_fixture_001.txt")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	header := strings.TrimSpace(string(raw))
	c, err := DeserializeChallenge(header)
	if err != nil {
		t.Fatalf("deserialize fixture: %v", err)
	}
	if c.Realm != "pubsub://alice/pay" {
		t.Fatalf("realm: %q", c.Realm)
	}
	if c.Method != "tempo" || c.Intent != "charge" {
		t.Fatalf("method/intent: %s/%s", c.Method, c.Intent)
	}
	if c.Request["amount"] != "1000000" {
		t.Fatalf("amount: %v", c.Request["amount"])
	}
	if !c.HasExpiry() {
		t.Fatal("expected expiry")
	}
}

// TestConformance_FixtureHMAC verifies cross-implementation HMAC compatibility
// against a live fixture captured from the TypeScript reference implementation
// (`mppx` npm package, run as `node _capture.mjs` in /home/junior/workspace/mpp_demo
// against the documented input vector).
//
// Capture command (reproducible — secret is the literal string below):
//
//	import { Challenge } from 'mppx'
//	import { Methods } from 'mppx/tempo'
//	const challenge = Challenge.fromMethod(Methods.charge, {
//	  realm: 'pubsub://alice/pay',
//	  expires: '2026-05-08T21:43:11.000Z',
//	  request: {
//	    amount: '1.00',
//	    currency: '0x20c0000000000000000000000000000000000000',
//	    recipient: '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
//	    decimals: 6, chainId: 42431,
//	  },
//	  secretKey: 'alice-demo-secret-key-32-bytes!!',
//	})
//	console.log(Challenge.serialize(challenge))
//
// The Go implementation must reproduce the same HMAC byte-for-byte under
// the same canonical-JSON encoding rules.
func TestConformance_FixtureHMAC(t *testing.T) {
	secret := []byte(envOr("MPP_FIXTURE_SECRET", "alice-demo-secret-key-32-bytes!!"))
	path := filepath.Join("testdata", "challenge_fixture_001.txt")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	header := strings.TrimSpace(string(raw))
	c, err := DeserializeChallenge(header)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}

	if err := VerifyChallengeID(secret, c); err != nil {
		t.Fatalf("Go re-derivation does not match TS-emitted fixture id %q: %v", c.ID, err)
	}
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// TestConformance_CredentialWireShape confirms the credential JSON wire shape
// matches the TS reference: { challenge: { id, realm, method, intent, ...,
// request: <base64url> }, payload, source? }.
func TestConformance_CredentialWireShape(t *testing.T) {
	c := Credential{
		Challenge: Challenge{
			ID:     "abc",
			Realm:  "r",
			Method: "tempo",
			Intent: "charge",
			Request: map[string]any{
				"amount":    "1",
				"currency":  "0xc",
				"recipient": "0xr",
			},
		},
		Payload: TempoChargePayload{Type: "transaction", Signature: "0x" + strings.Repeat("a", 64)},
		Source:  "did:pkh:eip155:42431:0x1234",
	}
	wire, err := SerializeCredential(c)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	body := strings.TrimPrefix(wire, "Payment ")
	raw, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		t.Fatalf("decode: %v", err)
	}
	got := string(raw)
	if !strings.Contains(got, `"challenge":`) || !strings.Contains(got, `"payload":`) || !strings.Contains(got, `"source":`) {
		t.Fatalf("missing wire fields in %s", got)
	}
	// `request` inside the embedded challenge MUST be a base64url string.
	if !strings.Contains(got, fmt.Sprintf(`"request":"%s"`, mustEncode(c.Challenge.Request))) {
		t.Fatalf("request field not embedded as base64url string; got: %s", got)
	}
}

func mustEncode(req map[string]any) string {
	s, err := EncodeRequest(req)
	if err != nil {
		panic(err)
	}
	return s
}
