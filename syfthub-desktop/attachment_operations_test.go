package main

import (
	"crypto/sha256"
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
