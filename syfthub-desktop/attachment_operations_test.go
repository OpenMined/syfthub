package main

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"
)

func TestSha256ShortIsDeterministic(t *testing.T) {
	body := []byte("hello world")
	sum := sha256.Sum256(body)
	short := sha256Short(sum[:])
	if len(short) != 16 { // 8 bytes hex-encoded
		t.Fatalf("expected 16 hex chars, got %d", len(short))
	}
	// Recompute to confirm determinism.
	if short != sha256Short(sum[:]) {
		t.Fatal("sha256Short not deterministic")
	}
	// Confirm the prefix matches sha256(body) exactly.
	if short != hex.EncodeToString(sum[:8]) {
		t.Fatal("sha256Short does not match first 8 bytes of full digest")
	}
}

func TestAttachToActiveSessionWithoutSessionReturnsError(t *testing.T) {
	app := NewApp()
	// agentSessionID is empty by default — no active session.
	tmp, err := os.CreateTemp("", "syft-att-test-*.bin")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(tmp.Name())
	_, _ = tmp.Write([]byte("hello"))
	tmp.Close()

	_, err = app.AttachToActiveSession(tmp.Name())
	if err == nil {
		t.Fatal("expected error for inactive session")
	}
}

func TestDownloadAttachmentWithoutSessionReturnsError(t *testing.T) {
	app := NewApp()
	dir := t.TempDir()
	err := app.DownloadActiveSessionAttachment("att-x", filepath.Join(dir, "out.bin"))
	if err == nil {
		t.Fatal("expected error for inactive session")
	}
}

func TestUniqueDestPathReturnsOriginalWhenNoCollision(t *testing.T) {
	dir := t.TempDir()
	got := uniqueDestPath(dir, "foo.txt")
	want := filepath.Join(dir, "foo.txt")
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestUniqueDestPathAppendsCounterOnCollision(t *testing.T) {
	dir := t.TempDir()
	// Pre-create two collisions so the helper has to step past them.
	for _, name := range []string{"foo.txt", "foo (1).txt"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("x"), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	got := uniqueDestPath(dir, "foo.txt")
	want := filepath.Join(dir, "foo (2).txt")
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestUniqueDestPathHandlesNoExtension(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "Makefile"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	got := uniqueDestPath(dir, "Makefile")
	want := filepath.Join(dir, "Makefile (1)")
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestMaterializeAgentInlineAttachmentWritesFile(t *testing.T) {
	dir := t.TempDir()
	body := []byte("hello agent")
	sum := sha256.Sum256(body)
	data := map[string]any{
		"transport":        "inline",
		"file_id":          "att-abc",
		"name":             "Makefile.pt",
		"size_bytes":       float64(len(body)),
		"plaintext_sha256": hex.EncodeToString(sum[:]),
		"inline_data_b64":  base64Encode(body),
	}
	if err := materializeAgentInlineAttachment(dir, data); err != nil {
		t.Fatal(err)
	}
	dest := filepath.Join(dir, "att-abc.pt")
	got, err := os.ReadFile(dest)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(body) {
		t.Fatalf("contents drift: %q vs %q", got, body)
	}
}

func TestMaterializeAgentInlineAttachmentRejectsSizeMismatch(t *testing.T) {
	dir := t.TempDir()
	body := []byte("hello")
	data := map[string]any{
		"transport":       "inline",
		"file_id":         "att-x",
		"name":            "x.bin",
		"size_bytes":      float64(999),
		"inline_data_b64": base64Encode(body),
	}
	if err := materializeAgentInlineAttachment(dir, data); err == nil {
		t.Fatal("expected size mismatch error")
	}
}

func TestMaterializeAgentInlineAttachmentNoOpWhenNotInline(t *testing.T) {
	dir := t.TempDir()
	data := map[string]any{
		"transport": "object_store",
		"file_id":   "att-os",
		"name":      "x.bin",
	}
	if err := materializeAgentInlineAttachment(dir, data); err != nil {
		t.Fatalf("expected no-op, got %v", err)
	}
	// Nothing should have been written.
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 0 {
		t.Fatalf("expected empty dir, got %d entries", len(entries))
	}
}

// base64Encode is a tiny helper for the test fixtures above.
func base64Encode(b []byte) string {
	return base64.StdEncoding.EncodeToString(b)
}
