package syfthubapi

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAttachmentInfoRoundTripInline(t *testing.T) {
	info := AttachmentInfo{
		FileID:          "att-abc",
		Name:            "hello.txt",
		MIME:            "text/plain",
		SizeBytes:       11,
		PlaintextSHA256: "deadbeef",
		Transport:       AttachmentTransportInline,
		InlineDataB64:   "aGVsbG8gd29ybGQ=",
	}
	b, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !strings.Contains(string(b), `"transport":"inline"`) {
		t.Fatalf("expected transport=inline in %s", string(b))
	}
	out, err := AttachmentInfoFromRaw(json.RawMessage(b))
	if err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out.FileID != info.FileID || out.InlineDataB64 != info.InlineDataB64 {
		t.Fatalf("round-trip mismatch: %+v vs %+v", out, info)
	}
	if out.Transport != AttachmentTransportInline {
		t.Fatalf("transport mismatch: %q", out.Transport)
	}
}

func TestAttachmentInfoRoundTripObjectStore(t *testing.T) {
	info := AttachmentInfo{
		FileID:          "att-xyz",
		Name:            "doc.pdf",
		MIME:            "application/pdf",
		SizeBytes:       2_000_000,
		PlaintextSHA256: "feedface",
		Transport:       AttachmentTransportObjectStore,
		ObjectBucket:    "syft-att-sess-1",
		ObjectKey:       "att-xyz",
		ChunkSize:       65536,
		WrappedKey: &WrappedKey{
			Algorithm:  "AES-256-GCM",
			Ciphertext: "AAAAAA==",
			Nonce:      "BBBBBBBBBBBBBBBBBB==",
			Info:       AttachmentHKDFInfoV1,
		},
	}
	b, err := json.Marshal(info)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	out, err := AttachmentInfoFromRaw(json.RawMessage(b))
	if err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out.WrappedKey == nil || out.WrappedKey.Info != AttachmentHKDFInfoV1 {
		t.Fatalf("wrapped key not preserved: %+v", out.WrappedKey)
	}
	if out.ChunkSize != 65536 {
		t.Fatalf("chunk size lost: %d", out.ChunkSize)
	}
}

func TestSessionStartPayloadHasCapability(t *testing.T) {
	p := AgentSessionStartPayload{Capabilities: []string{"attachments", "future"}}
	if !p.HasCapability(AttachmentCapability) {
		t.Fatal("expected attachments capability to match")
	}
	if p.HasCapability("nope") {
		t.Fatal("expected nope to NOT match")
	}
	empty := AgentSessionStartPayload{}
	if empty.HasCapability(AttachmentCapability) {
		t.Fatal("expected empty capabilities to NOT match")
	}
}

func TestInlineMaxBytesMatchesProtocol(t *testing.T) {
	// The protocol spec hard-codes 64 KiB as the inline ceiling. Detect drift.
	if InlineMaxBytes != 64*1024 {
		t.Fatalf("InlineMaxBytes drifted from spec: %d", InlineMaxBytes)
	}
}

func TestAttachmentEventTypesAreNamespaced(t *testing.T) {
	// The event types must use dotted namespacing matching the message event style.
	if EventTypeUserAttachment != "user.attachment" {
		t.Fatalf("user attachment event type drift: %q", EventTypeUserAttachment)
	}
	if EventTypeAgentAttachment != "agent.attachment" {
		t.Fatalf("agent attachment event type drift: %q", EventTypeAgentAttachment)
	}
}
