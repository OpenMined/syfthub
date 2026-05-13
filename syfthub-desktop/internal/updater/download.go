package updater

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"hash"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

// DownloadStage describes the progress of an in-flight or completed
// artifact download.
type DownloadStage string

const (
	DownloadIdle        DownloadStage = "idle"
	DownloadActive      DownloadStage = "downloading"
	DownloadReady       DownloadStage = "ready"
	DownloadFailed      DownloadStage = "failed"
)

// DownloadState is the structured snapshot sent to the frontend on the
// "update:download" event.
type DownloadState struct {
	Stage      DownloadStage `json:"stage"`
	Version    string        `json:"version,omitempty"`
	BytesDone  int64         `json:"bytes_done,omitempty"`
	BytesTotal int64         `json:"bytes_total,omitempty"`
	LocalPath  string        `json:"local_path,omitempty"`
	Error      string        `json:"error,omitempty"`
}

// DownloadEmitter publishes download-progress events. Decoupled from the
// manifest-state Emitter so callers can route them differently.
type DownloadEmitter interface {
	EmitDownload(state DownloadState)
}

// progressFraction returns the maximum allowed size on the wire,
// capped at size_bytes * sizeOverhead. Some servers send a slightly
// padded body; 5% slack avoids spurious aborts.
const sizeOverhead = 1.05

// progressEmitInterval throttles progress events to avoid flooding the
// frontend with tiny updates.
const progressEmitInterval = 250 * time.Millisecond

var (
	ErrDownloadInProgress = errors.New("a download is already in progress")
	ErrChecksumMismatch   = errors.New("download SHA-256 does not match the manifest")
	ErrSizeExceeded       = errors.New("download body exceeded the expected size")
)

// Downloader manages a single concurrent download of an update artifact.
// It uses a cache directory rooted at the caller-supplied path —
// typically os.UserCacheDir()/syfthub-desktop/updates.
type Downloader struct {
	cacheRoot string
	client    *http.Client
	emitter   DownloadEmitter
	logger    Logger

	mu         sync.Mutex
	inFlight   atomic.Bool
	cancelFunc context.CancelFunc
}

// NewDownloader constructs a Downloader. If client is nil, a Client
// with a 30-minute timeout is used (large artifacts on slow links).
func NewDownloader(cacheRoot string, client *http.Client, emitter DownloadEmitter, logger Logger) *Downloader {
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Minute}
	}
	if logger == nil {
		logger = nopLogger{}
	}
	return &Downloader{
		cacheRoot: cacheRoot,
		client:    client,
		emitter:   emitter,
		logger:    logger,
	}
}

// versionDir returns the cache subdirectory for a given version.
func (d *Downloader) versionDir(version string) string {
	return filepath.Join(d.cacheRoot, version)
}

// artifactPath returns the final (completed) artifact path for a manifest URL.
func (d *Downloader) artifactPath(version, downloadURL string) string {
	return filepath.Join(d.versionDir(version), path.Base(downloadURL))
}

// LookupExisting returns the path of an already-downloaded artifact that
// matches the given version + sha256, or ("", false) if no such artifact
// is cached. This is the function the App calls at startup to surface
// "Update already downloaded" UI without re-fetching.
func (d *Downloader) LookupExisting(version, downloadURL, expectedSHA256 string) (string, bool) {
	if version == "" || downloadURL == "" || expectedSHA256 == "" {
		return "", false
	}
	p := d.artifactPath(version, downloadURL)
	info, err := os.Stat(p)
	if err != nil || info.IsDir() {
		return "", false
	}
	// Verify hash before claiming this is a valid download.
	hash, err := hashFile(p)
	if err != nil {
		return "", false
	}
	if hash != expectedSHA256 {
		// Corrupt or stale artifact — remove so the next download starts clean.
		_ = os.Remove(p)
		return "", false
	}
	return p, true
}

// CleanupOldVersions deletes cache subdirectories whose name doesn't
// match keepVersion. Best-effort — errors are logged and ignored.
func (d *Downloader) CleanupOldVersions(keepVersion string) {
	entries, err := os.ReadDir(d.cacheRoot)
	if err != nil {
		// Missing dir is fine — nothing to clean.
		return
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		if e.Name() == keepVersion {
			continue
		}
		full := filepath.Join(d.cacheRoot, e.Name())
		if err := os.RemoveAll(full); err != nil {
			d.logger.Warn("downloader: cleanup failed for " + full + ": " + err.Error())
		}
	}
}

// Cancel cancels the currently-running download, if any.
func (d *Downloader) Cancel() {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.cancelFunc != nil {
		d.cancelFunc()
	}
}

// Download starts an artifact fetch. Returns immediately — progress is
// published via the emitter. Only one download may run at a time.
//
// On success the artifact is at the returned path. The same path is also
// emitted in the DownloadReady event.
func (d *Downloader) Download(ctx context.Context, version, downloadURL, expectedSHA256 string, expectedSize int64) (string, error) {
	if !d.inFlight.CompareAndSwap(false, true) {
		return "", ErrDownloadInProgress
	}
	defer d.inFlight.Store(false)

	dlCtx, cancel := context.WithCancel(ctx)
	d.mu.Lock()
	d.cancelFunc = cancel
	d.mu.Unlock()
	defer func() {
		d.mu.Lock()
		d.cancelFunc = nil
		d.mu.Unlock()
		cancel()
	}()

	// Fast path: artifact already present and valid.
	if p, ok := d.LookupExisting(version, downloadURL, expectedSHA256); ok {
		d.emit(DownloadState{Stage: DownloadReady, Version: version, LocalPath: p, BytesDone: expectedSize, BytesTotal: expectedSize})
		return p, nil
	}

	dir := d.versionDir(version)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		d.emitErr(version, fmt.Errorf("create cache dir: %w", err))
		return "", err
	}

	finalPath := d.artifactPath(version, downloadURL)
	partialPath := finalPath + ".partial"

	// Resume support: if a .partial exists and its size is < expectedSize,
	// reuse it. If it equals expectedSize, we'll just verify the hash and
	// rename. If it exceeds, discard.
	var startOffset int64
	if info, err := os.Stat(partialPath); err == nil && !info.IsDir() {
		if info.Size() <= expectedSize {
			startOffset = info.Size()
		} else {
			_ = os.Remove(partialPath)
		}
	}

	d.emit(DownloadState{
		Stage:      DownloadActive,
		Version:    version,
		BytesDone:  startOffset,
		BytesTotal: expectedSize,
	})

	// Hash while writing so we don't have to re-read the file from disk
	// after the download. On a resume, the existing prefix has to be
	// hashed once to seed the hasher (unavoidable second read in that
	// case).
	h := sha256.New()
	if startOffset > 0 {
		if err := seedHasherFromFile(h, partialPath, startOffset); err != nil {
			d.emitErr(version, fmt.Errorf("seed resume hash: %w", err))
			return "", err
		}
	}
	if err := d.downloadInto(dlCtx, downloadURL, partialPath, startOffset, expectedSize, version, h); err != nil {
		d.emitErr(version, err)
		return "", err
	}

	got := hex.EncodeToString(h.Sum(nil))
	if got != expectedSHA256 {
		_ = os.Remove(partialPath)
		err := ErrChecksumMismatch
		d.emitErr(version, err)
		return "", err
	}

	if err := os.Rename(partialPath, finalPath); err != nil {
		d.emitErr(version, fmt.Errorf("rename partial: %w", err))
		return "", err
	}

	d.emit(DownloadState{
		Stage:      DownloadReady,
		Version:    version,
		BytesDone:  expectedSize,
		BytesTotal: expectedSize,
		LocalPath:  finalPath,
	})
	return finalPath, nil
}

// downloadInto streams the response body into partialPath starting at
// startOffset, emitting throttled progress events and feeding every
// byte written into h so the caller gets a SHA-256 without a second
// disk pass.
func (d *Downloader) downloadInto(ctx context.Context, url, partialPath string, startOffset, expectedSize int64, version string, h hash.Hash) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", "syfthub-desktop-updater/1")
	if startOffset > 0 {
		req.Header.Set("Range", "bytes="+strconv.FormatInt(startOffset, 10)+"-")
	}

	resp, err := d.client.Do(req)
	if err != nil {
		return fmt.Errorf("http get: %w", err)
	}
	defer resp.Body.Close()

	// Some servers ignore Range and respond 200; rewrite from scratch
	// and reset the hasher seeded from the (now-discarded) prefix.
	if startOffset > 0 && resp.StatusCode == http.StatusOK {
		_ = os.Remove(partialPath)
		startOffset = 0
		h.Reset()
	}
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return fmt.Errorf("http get: status %d", resp.StatusCode)
	}

	var flag int
	if startOffset > 0 {
		flag = os.O_WRONLY | os.O_APPEND
	} else {
		flag = os.O_WRONLY | os.O_CREATE | os.O_TRUNC
	}
	f, err := os.OpenFile(partialPath, flag, 0o644)
	if err != nil {
		return fmt.Errorf("open partial: %w", err)
	}
	defer f.Close()

	maxBytes := int64(float64(expectedSize) * sizeOverhead)
	totalSoFar := startOffset
	lastEmit := time.Now()
	sink := io.MultiWriter(f, h)

	buf := make([]byte, 64*1024)
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		n, readErr := resp.Body.Read(buf)
		if n > 0 {
			if totalSoFar+int64(n) > maxBytes {
				return ErrSizeExceeded
			}
			if _, err := sink.Write(buf[:n]); err != nil {
				return fmt.Errorf("write partial: %w", err)
			}
			totalSoFar += int64(n)

			if time.Since(lastEmit) >= progressEmitInterval {
				d.emit(DownloadState{
					Stage:      DownloadActive,
					Version:    version,
					BytesDone:  totalSoFar,
					BytesTotal: expectedSize,
				})
				lastEmit = time.Now()
			}
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}

	if err := f.Sync(); err != nil {
		return fmt.Errorf("fsync partial: %w", err)
	}
	return nil
}

// seedHasherFromFile hashes the first n bytes of path into h. Used to
// resume a download with the SHA-256 state already containing the
// existing prefix's bytes.
func seedHasherFromFile(h hash.Hash, path string, n int64) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = io.CopyN(h, f, n)
	return err
}

func (d *Downloader) emit(s DownloadState) {
	if d.emitter != nil {
		d.emitter.EmitDownload(s)
	}
}

func (d *Downloader) emitErr(version string, err error) {
	d.emit(DownloadState{
		Stage:   DownloadFailed,
		Version: version,
		Error:   err.Error(),
	})
}

// hashFile returns the lowercase-hex SHA-256 of the file at path.
func hashFile(p string) (string, error) {
	f, err := os.Open(p)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
