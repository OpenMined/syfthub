package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"
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

// TestSaveAgentAttachmentRemovesDestOnDownloadError pins the partial-write
// cleanup contract: if writeAttachment errors, SaveAgentAttachment must
// os.Remove the dest file it created so callers never see a half-written
// blob under ~/Downloads.
//
// We trigger the error path without spinning up NATS by leaving the
// AgentClientSession's attachmentStore unset — DownloadAttachment fails
// inside ensureDownloader, which is the same surface a mid-stream cancel
// would propagate through. HOME is redirected so the dest lands in a
// tempdir, not the developer's real Downloads folder.
func TestSaveAgentAttachmentRemovesDestOnDownloadError(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home) // harmless on Unix; covers Windows runners

	app := NewApp()
	app.ctx = context.Background()

	// Live session shell — only SessionID matters for the test path; the
	// rest stays zero-valued so ensureDownloader returns "attachmentStore
	// nil" the moment DownloadAttachment is called.
	app.agentSession = &transport.AgentClientSession{SessionID: "sess-cleanup"}
	app.agentAttachments = map[string]*agentAttachment{
		"att-bad": {
			Meta: agenttypes.AttachmentEvent{
				FileID:       "att-bad",
				Name:         "report.bin",
				MIME:         "application/octet-stream",
				SizeBytes:    200_000,
				Transport:    "object_store",
				ObjectBucket: "syft-att-sess-cleanup",
				ObjectKey:    "att-bad",
			},
			// Bytes is nil so writeAttachment routes through the
			// object_store branch and fails inside the SDK.
		},
	}

	dest, err := app.SaveAgentAttachment("att-bad", "report.bin")
	if err == nil {
		t.Fatal("expected SaveAgentAttachment to fail when downloader is unconfigured")
	}
	if dest != "" {
		t.Errorf("expected empty dest on error, got %q", dest)
	}

	leftover := filepath.Join(home, "Downloads", "report.bin")
	if _, statErr := os.Stat(leftover); !os.IsNotExist(statErr) {
		t.Errorf("expected partial file at %s to be removed; got stat err = %v", leftover, statErr)
	}
}
