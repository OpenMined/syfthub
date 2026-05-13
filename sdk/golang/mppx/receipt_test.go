package mppx

import (
	"strings"
	"testing"
	"time"
)

func TestSerializeDeserializeReceiptRoundTrip(t *testing.T) {
	ts, _ := time.Parse(time.RFC3339, "2026-05-08T21:37:28Z")
	r := Receipt{
		Method:    "tempo",
		Reference: "0x5607a5a32f3115f517ea2738752af7bca86560bc4fe85e62dbafd8f9d316dfcd",
		Status:    "success",
		Timestamp: ts,
	}
	wire, err := SerializeReceipt(r)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	if strings.ContainsAny(wire, "+/=") {
		t.Fatalf("receipt must use unpadded url-safe base64: %q", wire)
	}
	got, err := DeserializeReceipt(wire)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}
	if got.Reference != r.Reference || got.Method != r.Method || got.Status != r.Status {
		t.Fatalf("mismatch: %+v vs %+v", got, r)
	}
	if !got.Timestamp.Equal(r.Timestamp) {
		t.Fatalf("timestamp mismatch: %v vs %v", got.Timestamp, r.Timestamp)
	}
}

func TestReceiptStatusMustBeSuccess(t *testing.T) {
	r := Receipt{
		Method:    "tempo",
		Reference: "0x" + strings.Repeat("a", 64),
		Status:    "failed",
		Timestamp: time.Now(),
	}
	if _, err := SerializeReceipt(r); err == nil {
		t.Fatal("expected error for non-success status")
	}
}

func TestReceiptOptionalExternalID(t *testing.T) {
	ts, _ := time.Parse(time.RFC3339, "2026-05-08T21:37:28Z")
	r := Receipt{
		Method:     "tempo",
		Reference:  "0x" + strings.Repeat("b", 64),
		ExternalID: "order-42",
		Status:     "success",
		Timestamp:  ts,
	}
	wire, err := SerializeReceipt(r)
	if err != nil {
		t.Fatalf("serialize: %v", err)
	}
	got, err := DeserializeReceipt(wire)
	if err != nil {
		t.Fatalf("deserialize: %v", err)
	}
	if got.ExternalID != "order-42" {
		t.Fatalf("externalId lost: %q", got.ExternalID)
	}
}
