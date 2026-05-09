package mppx

import (
	"strings"
	"testing"
	"time"
)

func sampleChallenge(t *testing.T) Challenge {
	t.Helper()
	expires, err := time.Parse(time.RFC3339, "2026-05-08T21:43:11Z")
	if err != nil {
		t.Fatalf("parse expires: %v", err)
	}
	return Challenge{
		ID:     "vEUhvKuj0123456789abcdefghijklmnopqrstuvwxyz",
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
}

func TestSerializeDeserializeChallengeRoundTrip(t *testing.T) {
	c := sampleChallenge(t)
	wire, err := SerializeChallenge(c)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	if !strings.HasPrefix(wire, "Payment ") {
		t.Fatalf("missing scheme: %q", wire)
	}
	if !strings.Contains(wire, `realm="pubsub://alice/pay"`) {
		t.Fatalf("missing realm: %q", wire)
	}
	got, err := DeserializeChallenge(wire)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}
	if got.ID != c.ID || got.Realm != c.Realm || got.Method != c.Method || got.Intent != c.Intent {
		t.Fatalf("roundtrip mismatch: got %+v want %+v", got, c)
	}
	if got.Expires.UTC() != c.Expires.UTC() {
		t.Fatalf("expires mismatch: got %v want %v", got.Expires, c.Expires)
	}
	for k, v := range c.Request {
		if got.Request[k] != v {
			t.Fatalf("request[%q] mismatch: got %v want %v", k, got.Request[k], v)
		}
	}
}

func TestSerializeChallengeFieldOrder(t *testing.T) {
	c := sampleChallenge(t)
	wire, err := SerializeChallenge(c)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	want := []string{`id="`, `realm="`, `method="`, `intent="`, `request="`, `expires="`}
	idx := -1
	for _, key := range want {
		i := strings.Index(wire, key)
		if i < 0 {
			t.Fatalf("missing %q in %q", key, wire)
		}
		if i < idx {
			t.Fatalf("field %q out of order in %q", key, wire)
		}
		idx = i
	}
}

func TestDeserializeChallengeRejectsMissingScheme(t *testing.T) {
	_, err := DeserializeChallenge(`Bearer abc`)
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestDeserializeChallengeAcceptsExtraWhitespace(t *testing.T) {
	wire := `Payment id="abc",  realm="r",method="tempo", intent="charge", request="e30"`
	c, err := DeserializeChallenge(wire)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if c.ID != "abc" || c.Realm != "r" {
		t.Fatalf("parsed wrong: %+v", c)
	}
}

func TestDeserializeChallengeRejectsDuplicateParam(t *testing.T) {
	wire := `Payment id="a", id="b", realm="r", method="m", intent="i", request="e30"`
	if _, err := DeserializeChallenge(wire); err == nil {
		t.Fatal("expected duplicate-key error")
	}
}

func TestDeserializeChallengeRejectsUnterminatedQuote(t *testing.T) {
	wire := `Payment id="abc, realm="r"`
	if _, err := DeserializeChallenge(wire); err == nil {
		t.Fatal("expected unterminated-quoted-string error")
	}
}

func TestChallengeIsExpired(t *testing.T) {
	c := Challenge{Expires: time.Now().Add(-1 * time.Minute)}
	if !c.IsExpired(time.Now()) {
		t.Fatal("expected expired")
	}
	c.Expires = time.Now().Add(1 * time.Minute)
	if c.IsExpired(time.Now()) {
		t.Fatal("expected not expired")
	}
}
