package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAttachToActiveSessionWithoutSessionReturnsError(t *testing.T) {
	app := NewApp()
	// agentSession is nil by default — no active session.
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

func TestSaveAgentAttachmentWithoutSessionReturnsError(t *testing.T) {
	app := NewApp()
	_, err := app.SaveAgentAttachment("att-x", "out.bin")
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

func TestLimitedBufferRespectsCap(t *testing.T) {
	b := &limitedBuffer{max: 3}
	n, err := b.Write([]byte("hello"))
	if err != nil || n != 5 {
		t.Fatalf("Write should consume all input: n=%d err=%v", n, err)
	}
	if string(b.bytes) != "hel" {
		t.Fatalf("expected truncation to first 3 bytes, got %q", string(b.bytes))
	}
	// Subsequent writes after cap is hit are discarded but still consumed.
	n2, err := b.Write([]byte("more"))
	if err != nil || n2 != 4 {
		t.Fatalf("post-cap Write should still consume: n=%d err=%v", n2, err)
	}
	if string(b.bytes) != "hel" {
		t.Fatalf("buffer should not grow past cap: %q", string(b.bytes))
	}
}

func TestLimitedBufferUnlimited(t *testing.T) {
	b := &limitedBuffer{}
	for _, chunk := range []string{"hello ", "agent ", "world"} {
		if _, err := b.Write([]byte(chunk)); err != nil {
			t.Fatal(err)
		}
	}
	if string(b.bytes) != "hello agent world" {
		t.Fatalf("unexpected buffer: %q", string(b.bytes))
	}
}
