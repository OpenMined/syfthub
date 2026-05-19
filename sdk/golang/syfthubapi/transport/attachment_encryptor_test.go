package transport

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"testing"
)

func TestAttachmentEncryptorRequiresValidKey(t *testing.T) {
	if _, err := NewAttachmentEncryptor(make([]byte, 16)); err == nil {
		t.Fatal("expected error for short key")
	}
	if _, err := NewAttachmentEncryptor(make([]byte, 32)); err != nil {
		t.Fatalf("expected ok for 32-byte key: %v", err)
	}
}

func TestDeriveFileKEKIsDeterministicAndPerFile(t *testing.T) {
	sessionKey := make([]byte, 32)
	if _, err := rand.Read(sessionKey); err != nil {
		t.Fatal(err)
	}
	enc, err := NewAttachmentEncryptor(sessionKey)
	if err != nil {
		t.Fatal(err)
	}
	a1, _ := enc.DeriveFileKEK("att-foo")
	a2, _ := enc.DeriveFileKEK("att-foo")
	b1, _ := enc.DeriveFileKEK("att-bar")
	if !bytes.Equal(a1, a2) {
		t.Fatal("KEK derivation not deterministic")
	}
	if bytes.Equal(a1, b1) {
		t.Fatal("KEKs collided across file_ids")
	}
	if len(a1) != 32 {
		t.Fatalf("expected 32-byte KEK, got %d", len(a1))
	}
}

func TestWrapUnwrapFileKey(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	ct, nonce, err := enc.WrapFileKey("att-1", fileKey)
	if err != nil {
		t.Fatal(err)
	}
	out, err := enc.UnwrapFileKey("att-1", ct, nonce)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(out, fileKey) {
		t.Fatal("unwrap did not recover original key")
	}
	// Wrong file_id should fail (AAD mismatch).
	if _, err := enc.UnwrapFileKey("att-2", ct, nonce); err == nil {
		t.Fatal("expected AAD mismatch error")
	}
}

func TestEncryptStreamDecryptStreamRoundTripSmall(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()
	plaintext := []byte("hello world — small payload, single chunk")

	var ct bytes.Buffer
	size, sha, err := enc.EncryptStream(fileKey, baseNonce, "att-x", bytes.NewReader(plaintext), &ct)
	if err != nil {
		t.Fatal(err)
	}
	if size != int64(len(plaintext)) {
		t.Fatalf("size mismatch: %d vs %d", size, len(plaintext))
	}
	want := sha256.Sum256(plaintext)
	if sha != hex.EncodeToString(want[:]) {
		t.Fatalf("sha mismatch: %s", sha)
	}

	var pt bytes.Buffer
	rsize, rsha, err := enc.DecryptStream(fileKey, baseNonce, "att-x", int64(len(plaintext)), &ct, &pt)
	if err != nil {
		t.Fatal(err)
	}
	if rsize != int64(len(plaintext)) || rsha != sha {
		t.Fatalf("round-trip mismatch: %d/%s vs %d/%s", rsize, rsha, len(plaintext), sha)
	}
	if !bytes.Equal(pt.Bytes(), plaintext) {
		t.Fatal("plaintext drift")
	}
}

func TestEncryptStreamMultipleChunks(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()

	// Build a 200 KiB plaintext — 3 full chunks + 1 partial (64+64+64+8).
	plaintext := make([]byte, 200*1024)
	rand.Read(plaintext)

	var ct bytes.Buffer
	if _, _, err := enc.EncryptStream(fileKey, baseNonce, "att-multi", bytes.NewReader(plaintext), &ct); err != nil {
		t.Fatal(err)
	}

	// Each full chunk produces ChunkSize + TagSize ciphertext bytes; final
	// chunk produces remainingBytes + TagSize. Total = N*(chunk + tag) + final + tag.
	expected := 3*(AttachmentChunkSize+AttachmentTagSize) + (200*1024 - 3*AttachmentChunkSize + AttachmentTagSize)
	if ct.Len() != expected {
		t.Fatalf("ciphertext length mismatch: got %d, want %d", ct.Len(), expected)
	}

	var pt bytes.Buffer
	if _, _, err := enc.DecryptStream(fileKey, baseNonce, "att-multi", int64(len(plaintext)), &ct, &pt); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(pt.Bytes(), plaintext) {
		t.Fatal("plaintext drift after multi-chunk round-trip")
	}
}

func TestEncryptStreamExactlyOneChunk(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()

	// 64 KiB exact — boundary case for the chunked GCM loop.
	plaintext := make([]byte, AttachmentChunkSize)
	rand.Read(plaintext)

	var ct bytes.Buffer
	if _, _, err := enc.EncryptStream(fileKey, baseNonce, "att-exact", bytes.NewReader(plaintext), &ct); err != nil {
		t.Fatal(err)
	}
	if ct.Len() != AttachmentChunkSize+AttachmentTagSize {
		t.Fatalf("expected single-chunk ciphertext, got %d bytes", ct.Len())
	}
	var pt bytes.Buffer
	if _, _, err := enc.DecryptStream(fileKey, baseNonce, "att-exact", int64(len(plaintext)), &ct, &pt); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(pt.Bytes(), plaintext) {
		t.Fatal("plaintext drift after exact-chunk round-trip")
	}
}

func TestDecryptStreamRejectsTamperedCiphertext(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()
	plaintext := []byte("important data")
	var ct bytes.Buffer
	enc.EncryptStream(fileKey, baseNonce, "att-tamper", bytes.NewReader(plaintext), &ct)
	tampered := ct.Bytes()
	tampered[5] ^= 0xff
	var pt bytes.Buffer
	if _, _, err := enc.DecryptStream(fileKey, baseNonce, "att-tamper", int64(len(plaintext)), bytes.NewReader(tampered), &pt); err == nil {
		t.Fatal("expected decrypt to fail on tampered ciphertext")
	}
}

func TestDecryptStreamSizeMismatchRejected(t *testing.T) {
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)
	enc, _ := NewAttachmentEncryptor(sessionKey)
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()
	plaintext := []byte("data")
	var ct bytes.Buffer
	enc.EncryptStream(fileKey, baseNonce, "att", bytes.NewReader(plaintext), &ct)
	var pt bytes.Buffer
	if _, _, err := enc.DecryptStream(fileKey, baseNonce, "att", 999, &ct, &pt); err == nil {
		t.Fatal("expected size mismatch error")
	}
}

func TestMemoryObjectStoreRoundTrip(t *testing.T) {
	ctx := context.Background()
	os := NewMemoryAttachmentObjectStore()
	if err := os.EnsureBucket(ctx, "b1", 0); err != nil {
		t.Fatal(err)
	}
	body := []byte("ciphertext-blob")
	if err := os.Put(ctx, "b1", "k1", bytes.NewReader(body)); err != nil {
		t.Fatal(err)
	}
	var w bytes.Buffer
	if err := os.Get(ctx, "b1", "k1", &w); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(w.Bytes(), body) {
		t.Fatal("round-trip drift")
	}
	if err := os.DeleteBucket(ctx, "b1"); err != nil {
		t.Fatal(err)
	}
	if err := os.Get(ctx, "b1", "k1", io.Discard); err == nil {
		t.Fatal("expected error after bucket delete")
	}
}

func TestBucketNameForSession(t *testing.T) {
	if got := bucketNameForSession("sess-42"); got != "syft-att-sess-42" {
		t.Fatalf("unexpected bucket name: %s", got)
	}
}

func TestEndToEndEncryptedUploadDownload(t *testing.T) {
	ctx := context.Background()
	sessionKey := make([]byte, 32)
	rand.Read(sessionKey)

	hostEnc, _ := NewAttachmentEncryptor(sessionKey)
	aggrEnc, _ := NewAttachmentEncryptor(sessionKey) // aggregator derives the same session key

	fileID := "att-final"
	bucket := bucketNameForSession("sess-roundtrip")
	store := NewMemoryAttachmentObjectStore()
	if err := store.EnsureBucket(ctx, bucket, 0); err != nil {
		t.Fatal(err)
	}

	plaintext := make([]byte, 80*1024)
	rand.Read(plaintext)

	// HOST: generate per-file K + base nonce, wrap K under session key,
	// encrypt + stream to Object Store.
	fileKey, _ := GenerateFileKey()
	baseNonce, _ := GenerateBaseNonce()
	wrappedCT, wrappedNonce, err := hostEnc.WrapFileKey(fileID, fileKey)
	if err != nil {
		t.Fatal(err)
	}
	var ct bytes.Buffer
	if _, _, err := hostEnc.EncryptStream(fileKey, baseNonce, fileID, bytes.NewReader(plaintext), &ct); err != nil {
		t.Fatal(err)
	}
	if err := store.Put(ctx, bucket, fileID, &ct); err != nil {
		t.Fatal(err)
	}

	// AGGREGATOR: unwrap K from session key, stream ciphertext out of Object
	// Store, decrypt to plaintext.
	unwrapped, err := aggrEnc.UnwrapFileKey(fileID, wrappedCT, wrappedNonce)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(unwrapped, fileKey) {
		t.Fatal("aggregator unwrapped to a different key")
	}
	var ctOut bytes.Buffer
	if err := store.Get(ctx, bucket, fileID, &ctOut); err != nil {
		t.Fatal(err)
	}
	var pt bytes.Buffer
	if _, _, err := aggrEnc.DecryptStream(unwrapped, baseNonce, fileID, int64(len(plaintext)), &ctOut, &pt); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(pt.Bytes(), plaintext) {
		t.Fatal("aggregator-side plaintext drift")
	}
}
