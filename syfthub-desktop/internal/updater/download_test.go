package updater

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type emitCollector struct {
	mu     atomicEmitMu
	events []DownloadState
}

// atomicEmitMu is a tiny lock-free guard for the collector — we don't
// need a real mutex because Append in tests is serialized.
type atomicEmitMu struct{}

func (c *emitCollector) EmitDownload(s DownloadState) {
	c.events = append(c.events, s)
}

func sha256Hex(b []byte) string {
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

func TestDownloadHappyPath(t *testing.T) {
	body := []byte(strings.Repeat("abc", 1000))
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", strconv.Itoa(len(body)))
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	dir := t.TempDir()
	ec := &emitCollector{}
	d := NewDownloader(dir, srv.Client(), ec, nopLogger{})

	url := srv.URL + "/syfthub-desktop-linux-amd64"
	p, err := d.Download(context.Background(), "0.2.0", url, sha256Hex(body), int64(len(body)))
	if err != nil {
		t.Fatalf("Download: %v", err)
	}
	if _, err := os.Stat(p); err != nil {
		t.Fatalf("artifact missing: %v", err)
	}
	if !strings.HasSuffix(p, "syfthub-desktop-linux-amd64") {
		t.Errorf("unexpected path: %s", p)
	}
	if got := lastStage(ec); got != DownloadReady {
		t.Errorf("last stage = %v, want ready", got)
	}
}

func TestDownloadHashMismatch(t *testing.T) {
	body := []byte("real body")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	dir := t.TempDir()
	ec := &emitCollector{}
	d := NewDownloader(dir, srv.Client(), ec, nopLogger{})

	wrongHash := sha256Hex([]byte("different body"))
	_, err := d.Download(context.Background(), "0.2.0", srv.URL+"/file", wrongHash, int64(len(body)))
	if !errors.Is(err, ErrChecksumMismatch) {
		t.Fatalf("want ErrChecksumMismatch, got %v", err)
	}
	if got := lastStage(ec); got != DownloadFailed {
		t.Errorf("last stage = %v, want failed", got)
	}
	// Partial should be cleaned up.
	files, _ := os.ReadDir(filepath.Join(dir, "0.2.0"))
	if len(files) != 0 {
		t.Errorf("expected no files after hash mismatch, got %d", len(files))
	}
}

func TestDownloadSizeExceeded(t *testing.T) {
	// Claim 10 bytes; serve 100. Exceeds 10 * 1.05 = 10.5, so error.
	body := []byte(strings.Repeat("x", 100))
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	dir := t.TempDir()
	ec := &emitCollector{}
	d := NewDownloader(dir, srv.Client(), ec, nopLogger{})

	_, err := d.Download(context.Background(), "0.2.0", srv.URL+"/file", sha256Hex(body), 10)
	if !errors.Is(err, ErrSizeExceeded) {
		t.Fatalf("want ErrSizeExceeded, got %v", err)
	}
}

func TestDownloadConcurrentRefused(t *testing.T) {
	gate := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-gate
		_, _ = w.Write([]byte("hi"))
	}))
	defer srv.Close()
	defer close(gate)

	dir := t.TempDir()
	d := NewDownloader(dir, srv.Client(), nil, nopLogger{})

	var firstErr atomic.Value
	var ran atomic.Bool
	go func() {
		_, err := d.Download(context.Background(), "0.2.0", srv.URL, sha256Hex([]byte("hi")), 2)
		if err != nil {
			firstErr.Store(err.Error())
		}
		ran.Store(true)
	}()

	// Give the goroutine a moment to enter Download and claim inFlight.
	time.Sleep(20 * time.Millisecond)

	_, err := d.Download(context.Background(), "0.2.0", srv.URL, sha256Hex([]byte("hi")), 2)
	if !errors.Is(err, ErrDownloadInProgress) {
		t.Errorf("concurrent call: want ErrDownloadInProgress, got %v", err)
	}
}

func TestDownloadResume(t *testing.T) {
	body := []byte(strings.Repeat("a", 1000))
	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		if rng := r.Header.Get("Range"); rng != "" {
			// Honor a simple "bytes=N-" range.
			var start int64
			_, _ = strconv.Atoi(strings.TrimPrefix(strings.TrimSuffix(rng, "-"), "bytes="))
			if i := strings.IndexByte(rng[6:], '-'); i >= 0 {
				start, _ = strconv.ParseInt(rng[6:6+i], 10, 64)
			}
			w.Header().Set("Content-Range", "bytes "+strconv.FormatInt(start, 10)+"-"+strconv.Itoa(len(body)-1)+"/"+strconv.Itoa(len(body)))
			w.WriteHeader(http.StatusPartialContent)
			_, _ = w.Write(body[start:])
			return
		}
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	dir := t.TempDir()
	d := NewDownloader(dir, srv.Client(), nil, nopLogger{})

	// Pre-populate a partial with the first 400 bytes.
	versionDir := filepath.Join(dir, "0.2.0")
	if err := os.MkdirAll(versionDir, 0o755); err != nil {
		t.Fatal(err)
	}
	finalName := "syfthub-desktop-linux-amd64"
	if err := os.WriteFile(filepath.Join(versionDir, finalName+".partial"), body[:400], 0o644); err != nil {
		t.Fatal(err)
	}

	url := srv.URL + "/" + finalName
	p, err := d.Download(context.Background(), "0.2.0", url, sha256Hex(body), int64(len(body)))
	if err != nil {
		t.Fatalf("Download: %v", err)
	}
	got, _ := os.ReadFile(p)
	if string(got) != string(body) {
		t.Errorf("resumed download produced wrong body (len got=%d want=%d)", len(got), len(body))
	}
}

func TestLookupExistingValid(t *testing.T) {
	dir := t.TempDir()
	d := NewDownloader(dir, nil, nil, nopLogger{})
	versionDir := filepath.Join(dir, "0.2.0")
	if err := os.MkdirAll(versionDir, 0o755); err != nil {
		t.Fatal(err)
	}
	body := []byte("artifact")
	path := filepath.Join(versionDir, "syfthub-desktop-linux-amd64")
	if err := os.WriteFile(path, body, 0o644); err != nil {
		t.Fatal(err)
	}
	p, ok := d.LookupExisting("0.2.0", "https://example.com/syfthub-desktop-linux-amd64", sha256Hex(body))
	if !ok {
		t.Fatal("LookupExisting returned false for valid artifact")
	}
	if p != path {
		t.Errorf("path = %s, want %s", p, path)
	}
}

func TestLookupExistingHashMismatchDeletes(t *testing.T) {
	dir := t.TempDir()
	d := NewDownloader(dir, nil, nil, nopLogger{})
	versionDir := filepath.Join(dir, "0.2.0")
	_ = os.MkdirAll(versionDir, 0o755)
	path := filepath.Join(versionDir, "file")
	_ = os.WriteFile(path, []byte("corrupt"), 0o644)

	_, ok := d.LookupExisting("0.2.0", "https://example.com/file", sha256Hex([]byte("correct")))
	if ok {
		t.Fatal("LookupExisting should return false for hash mismatch")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("hash-mismatched artifact should have been deleted")
	}
}

func TestCleanupOldVersions(t *testing.T) {
	dir := t.TempDir()
	d := NewDownloader(dir, nil, nil, nopLogger{})
	_ = os.MkdirAll(filepath.Join(dir, "0.1.0"), 0o755)
	_ = os.MkdirAll(filepath.Join(dir, "0.2.0"), 0o755)
	_ = os.MkdirAll(filepath.Join(dir, "0.3.0"), 0o755)

	d.CleanupOldVersions("0.2.0")

	if _, err := os.Stat(filepath.Join(dir, "0.2.0")); err != nil {
		t.Error("kept version was deleted")
	}
	if _, err := os.Stat(filepath.Join(dir, "0.1.0")); !os.IsNotExist(err) {
		t.Error("0.1.0 should have been deleted")
	}
	if _, err := os.Stat(filepath.Join(dir, "0.3.0")); !os.IsNotExist(err) {
		t.Error("0.3.0 should have been deleted")
	}
}

func lastStage(c *emitCollector) DownloadStage {
	if len(c.events) == 0 {
		return DownloadIdle
	}
	return c.events[len(c.events)-1].Stage
}
