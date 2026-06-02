// attachment_cancel_test.go covers the failure surfaces that callers rely on
// for clean cancel-mid-transfer semantics:
//
//   - ObjectStoreUploader.Upload must surface a reader error mid-stream so
//     SendAttachment errors out BEFORE publishing a user.attachment message.
//   - Upload must surface a store-side Put failure so the caller can react
//     (the per-session bucket is TTL'd; per-file cleanup is the caller's job).
//   - ObjectStoreDownloader.DownloadStream must propagate writer errors so
//     the desktop's SaveAgentAttachment can os.Remove the partial file.

package transport

import (
	"bytes"
	"context"
	"crypto/rand"
	"errors"
	"io"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// errAfterReader yields n bytes of 'A' then fails with err.
type errAfterReader struct {
	n    int64
	read int64
	err  error
}

func (r *errAfterReader) Read(p []byte) (int, error) {
	remaining := r.n - r.read
	if remaining <= 0 {
		return 0, r.err
	}
	take := min(int64(len(p)), remaining)
	for i := range int(take) {
		p[i] = 'A'
	}
	r.read += take
	return int(take), nil
}

// putFailingStore wraps an in-memory store but injects an error on Put.
// EnsureBucket / Get / DeleteBucket pass through.
type putFailingStore struct {
	inner *MemoryAttachmentObjectStore
	err   error
	puts  atomic.Int32
}

func (s *putFailingStore) EnsureBucket(ctx context.Context, bucket string, ttl time.Duration) error {
	return s.inner.EnsureBucket(ctx, bucket, ttl)
}
func (s *putFailingStore) Put(_ context.Context, _, _ string, r io.Reader) error {
	s.puts.Add(1)
	_, _ = io.Copy(io.Discard, r) // mirror real backends that drain before reporting
	return s.err
}
func (s *putFailingStore) Get(ctx context.Context, bucket, key string, w io.Writer) error {
	return s.inner.Get(ctx, bucket, key, w)
}
func (s *putFailingStore) Delete(ctx context.Context, bucket, key string) error {
	return s.inner.Delete(ctx, bucket, key)
}
func (s *putFailingStore) DeleteBucket(ctx context.Context, bucket string) error {
	return s.inner.DeleteBucket(ctx, bucket)
}

// failWriter writes successfully up to failAt bytes, then returns err on the
// write that crosses the threshold. Tracks total bytes written for the test
// to assert the failure happened before the full payload made it through.
type failWriter struct {
	failAt  int
	written int
	err     error
}

func (w *failWriter) Write(p []byte) (int, error) {
	remaining := w.failAt - w.written
	if remaining <= 0 {
		return 0, w.err
	}
	if len(p) <= remaining {
		w.written += len(p)
		return len(p), nil
	}
	w.written = w.failAt
	return remaining, w.err
}

// TestObjectStoreUploaderReaderAbortLeavesNoObject verifies that a reader
// error past the inline boundary fails the upload at the encrypt stage —
// before the store's Put is reached. No ciphertext blob ends up in the
// session bucket, and no AttachmentInfo is produced for SendAttachment
// to publish as a user.attachment message.
func TestObjectStoreUploaderReaderAbortLeavesNoObject(t *testing.T) {
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	store := NewMemoryAttachmentObjectStore()
	const sessionID = "sess-reader-abort"
	up, err := NewObjectStoreUploader(context.Background(), key, store, sessionID)
	if err != nil {
		t.Fatal(err)
	}

	// Past one full encrypt-chunk (64 KiB) and into the second so the failure
	// triggers in the middle of a stream — not at the chunk boundary.
	r := &errAfterReader{
		n:   int64(syfthubapi.InlineMaxBytes) + 16*1024,
		err: errors.New("simulated source cancel"),
	}

	info, err := up.Upload(context.Background(), "att-aborted", "x.bin", "application/octet-stream", -1, r)
	if err == nil {
		t.Fatal("expected error from failing reader")
	}
	if !strings.Contains(err.Error(), "encrypt stream") {
		t.Errorf("expected error wrapped as 'encrypt stream', got: %v", err)
	}
	if info.FileID != "" {
		t.Errorf("expected zero AttachmentInfo on failure, got FileID=%q", info.FileID)
	}

	// No object should have landed in the bucket — Upload aborts before Put.
	var sink bytes.Buffer
	getErr := store.Get(context.Background(), bucketNameForSession(sessionID), "att-aborted", &sink)
	if getErr == nil {
		t.Errorf("expected Get to fail; bucket contained %d bytes", sink.Len())
	}
}

// TestObjectStoreUploaderPutFailureSurfaces verifies that a store-side Put
// failure (modeling a NATS disconnect / cancel during the network write) is
// surfaced to the caller as an error, with exactly one Put attempt — no
// retry loop and no AttachmentInfo produced.
func TestObjectStoreUploaderPutFailureSurfaces(t *testing.T) {
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	store := &putFailingStore{
		inner: NewMemoryAttachmentObjectStore(),
		err:   errors.New("nats: connection closed"),
	}
	up, err := NewObjectStoreUploader(context.Background(), key, store, "sess-put-fail")
	if err != nil {
		t.Fatal(err)
	}

	body := bytes.Repeat([]byte("X"), syfthubapi.InlineMaxBytes+1024)
	info, err := up.Upload(context.Background(), "att-put-fail", "x.bin", "application/octet-stream", -1, bytes.NewReader(body))
	if err == nil {
		t.Fatal("expected Upload to surface Put failure")
	}
	if !strings.Contains(err.Error(), "object-store put") {
		t.Errorf("expected error wrapped as 'object-store put', got: %v", err)
	}
	if info.FileID != "" {
		t.Errorf("expected zero AttachmentInfo on failure, got FileID=%q", info.FileID)
	}
	if got := store.puts.Load(); got != 1 {
		t.Errorf("expected exactly 1 Put attempt, got %d", got)
	}
}

// TestDownloadStreamPropagatesWriterError verifies that a writer error
// mid-decrypt is surfaced to the caller. This is the failure mode the
// desktop's SaveAgentAttachment / SaveAttachmentAs rely on to know it
// needs to os.Remove the partial destination file.
func TestDownloadStreamPropagatesWriterError(t *testing.T) {
	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		t.Fatal(err)
	}
	store := NewMemoryAttachmentObjectStore()
	up, err := NewObjectStoreUploader(context.Background(), key, store, "sess-dl-writer-fail")
	if err != nil {
		t.Fatal(err)
	}

	// Two full chunks of plaintext so failWriter has room to succeed before
	// failing — exercises the mid-stream cleanup path, not the first-write
	// path.
	body := bytes.Repeat([]byte{'Z'}, 2*AttachmentChunkSize)
	info, err := up.Upload(context.Background(), "att-dl", "x.bin", "application/octet-stream", -1, bytes.NewReader(body))
	if err != nil {
		t.Fatalf("Upload setup: %v", err)
	}

	dl, err := NewObjectStoreDownloader(context.Background(), key, store)
	if err != nil {
		t.Fatal(err)
	}

	w := &failWriter{failAt: AttachmentChunkSize / 2, err: errors.New("disk full")}
	err = dl.DownloadStream(&info, w)
	if err == nil {
		t.Fatal("expected DownloadStream to surface writer error")
	}
	if !strings.Contains(err.Error(), "disk full") {
		t.Errorf("expected wrapped 'disk full' error, got: %v", err)
	}
	if w.written > AttachmentChunkSize {
		t.Errorf("writer accepted %d bytes; expected to stop at failAt=%d", w.written, w.failAt)
	}
}
