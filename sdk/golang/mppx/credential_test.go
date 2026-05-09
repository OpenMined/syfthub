package mppx

import (
	"testing"
	"time"
)

func TestSerializeDeserializeCredentialRoundTrip(t *testing.T) {
	expires, _ := time.Parse(time.RFC3339, "2026-05-08T21:43:11Z")
	c := Credential{
		Challenge: Challenge{
			ID:     "vEUhvKujExampleHmacBase64Url",
			Realm:  "pubsub://alice/pay",
			Method: "tempo",
			Intent: "charge",
			Request: map[string]any{
				"amount":    "1000000",
				"currency":  "0x20c0000000000000000000000000000000000000",
				"recipient": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
			},
			Expires: expires,
		},
		Payload: TempoChargePayload{
			Type:      CredentialTypeTransaction,
			Signature: "0x5607a5a32f3115f517ea2738752af7bca86560bc4fe85e62dbafd8f9d316dfcd",
		},
		Source: "did:pkh:eip155:42431:0xC40DcC1234567890abcDef1234567890ABcdEF12",
	}

	wire, err := SerializeCredential(c)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	if len(wire) < len("Payment ") || wire[:8] != "Payment " {
		t.Fatalf("missing scheme: %q", wire)
	}

	got, err := DeserializeCredential(wire)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}
	if got.Challenge.ID != c.Challenge.ID {
		t.Fatalf("id mismatch: %q vs %q", got.Challenge.ID, c.Challenge.ID)
	}
	if got.Source != c.Source {
		t.Fatalf("source mismatch")
	}
	if got.Challenge.Expires.UTC() != c.Challenge.Expires.UTC() {
		t.Fatalf("expires mismatch")
	}
	for k, v := range c.Challenge.Request {
		if got.Challenge.Request[k] != v {
			t.Fatalf("request[%q] mismatch", k)
		}
	}

	payload, err := decodeTempoPayload(got.Payload)
	if err != nil {
		t.Fatalf("decode payload: %v", err)
	}
	if payload.Signature != "0x5607a5a32f3115f517ea2738752af7bca86560bc4fe85e62dbafd8f9d316dfcd" {
		t.Fatalf("payload signature mismatch: %q", payload.Signature)
	}
}

func TestDeserializeCredentialRejectsBadScheme(t *testing.T) {
	if _, err := DeserializeCredential("Bearer abc"); err == nil {
		t.Fatal("expected error")
	}
}

func TestDeserializeCredentialRejectsBadBase64(t *testing.T) {
	if _, err := DeserializeCredential("Payment !!!not-base64!!!"); err == nil {
		t.Fatal("expected error")
	}
}
