package transport

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func TestMaterializeInlineAttachmentSuccess(t *testing.T) {
	dir := t.TempDir()
	body := []byte("hello world")
	sum := sha256.Sum256(body)
	info := syfthubapi.AttachmentInfo{
		FileID:          "att-1",
		Name:            "hello.txt",
		MIME:            "text/plain",
		SizeBytes:       int64(len(body)),
		PlaintextSHA256: hex.EncodeToString(sum[:]),
		Transport:       syfthubapi.AttachmentTransportInline,
		InlineDataB64:   base64.StdEncoding.EncodeToString(body),
	}
	if err := materializeInlineAttachment(dir, &info); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if info.LocalPath == "" {
		t.Fatal("LocalPath not set")
	}
	got, err := os.ReadFile(info.LocalPath)
	if err != nil {
		t.Fatalf("read materialized file: %v", err)
	}
	if string(got) != string(body) {
		t.Fatalf("materialized bytes mismatch: %q vs %q", got, body)
	}
	// Verify the file was placed under the tempdir (and not elsewhere).
	if filepath.Dir(info.LocalPath) != dir {
		t.Fatalf("materialized file not in dir: %q", info.LocalPath)
	}
	// 0600 perms (Unix only).
	st, err := os.Stat(info.LocalPath)
	if err != nil {
		t.Fatal(err)
	}
	if mode := st.Mode().Perm(); mode != 0o600 {
		t.Fatalf("unexpected mode %o, want 600", mode)
	}
}

func TestMaterializeInlineAttachmentSizeMismatch(t *testing.T) {
	dir := t.TempDir()
	body := []byte("hello world")
	sum := sha256.Sum256(body)
	info := syfthubapi.AttachmentInfo{
		FileID:          "att-2",
		Name:            "x.bin",
		MIME:            "application/octet-stream",
		SizeBytes:       999, // wrong
		PlaintextSHA256: hex.EncodeToString(sum[:]),
		Transport:       syfthubapi.AttachmentTransportInline,
		InlineDataB64:   base64.StdEncoding.EncodeToString(body),
	}
	if err := materializeInlineAttachment(dir, &info); err == nil {
		t.Fatal("expected size mismatch error")
	}
}

func TestMaterializeInlineAttachmentSHAMismatch(t *testing.T) {
	dir := t.TempDir()
	body := []byte("hello world")
	info := syfthubapi.AttachmentInfo{
		FileID:          "att-3",
		Name:            "x.bin",
		MIME:            "application/octet-stream",
		SizeBytes:       int64(len(body)),
		PlaintextSHA256: hex.EncodeToString([]byte("not-the-real-sum-not-the-real-sum")), // wrong
		Transport:       syfthubapi.AttachmentTransportInline,
		InlineDataB64:   base64.StdEncoding.EncodeToString(body),
	}
	if err := materializeInlineAttachment(dir, &info); err == nil {
		t.Fatal("expected sha mismatch error")
	}
}

func TestMaterializeInlineAttachmentRejectsObjectStoreTransport(t *testing.T) {
	dir := t.TempDir()
	info := syfthubapi.AttachmentInfo{
		FileID:    "att-4",
		Transport: syfthubapi.AttachmentTransportObjectStore,
	}
	if err := materializeInlineAttachment(dir, &info); err == nil {
		t.Fatal("expected error for non-inline transport")
	}
}

func TestMaterializeInlineAttachmentPreservesExtension(t *testing.T) {
	dir := t.TempDir()
	body := []byte("png-bytes")
	sum := sha256.Sum256(body)
	info := syfthubapi.AttachmentInfo{
		FileID:          "att-5",
		Name:            "logo.png",
		MIME:            "image/png",
		SizeBytes:       int64(len(body)),
		PlaintextSHA256: hex.EncodeToString(sum[:]),
		Transport:       syfthubapi.AttachmentTransportInline,
		InlineDataB64:   base64.StdEncoding.EncodeToString(body),
	}
	if err := materializeInlineAttachment(dir, &info); err != nil {
		t.Fatal(err)
	}
	if filepath.Ext(info.LocalPath) != ".png" {
		t.Fatalf("extension not preserved: %q", info.LocalPath)
	}
}
