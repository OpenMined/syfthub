// download.go wires the updater.Downloader (Phase 2) into Wails App
// bindings. Streaming SHA-256-verified artifact fetch with resume; the
// completed file is revealed in the OS file browser on demand.
package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/openmined/syfthub-desktop-gui/internal/updater"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// downloadEventName is the Wails event channel for download-progress
// updates. Separate from "update:state" so subscribers can listen
// selectively.
const downloadEventName = "update:download"

// updateCacheSubdir is the cache directory under os.UserCacheDir() that
// holds the downloaded artifacts. Cleaned of older versions on startup.
const updateCacheSubdir = "syfthub-desktop/updates"

// downloadEmitter routes DownloadState events to the Wails runtime.
type downloadEmitter struct{ ctx context.Context }

func (e downloadEmitter) EmitDownload(s updater.DownloadState) {
	runtime.EventsEmit(e.ctx, downloadEventName, s)
}

func updateCacheDir() (string, error) {
	base, err := os.UserCacheDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, updateCacheSubdir), nil
}

// initDownloader builds the App's Downloader. Called from app.startup
// after settings are loaded.
func (a *App) initDownloader(ctx context.Context) {
	cacheDir, err := updateCacheDir()
	if err != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("downloader: cannot resolve cache dir: %v", err))
		return
	}
	if mkErr := os.MkdirAll(cacheDir, 0o755); mkErr != nil {
		runtime.LogWarning(ctx, fmt.Sprintf("downloader: cannot create cache dir: %v", mkErr))
		return
	}
	dl := updater.NewDownloader(cacheDir, nil, downloadEmitter{ctx: ctx}, updaterLogger{ctx: ctx})
	a.mu.Lock()
	a.downloader = dl
	a.mu.Unlock()

	// Surface already-downloaded artifact if present for the latest version.
	// Runs after the updater state is available; safe to call repeatedly.
	go a.surfaceExistingDownload()
}

// surfaceExistingDownload checks the cache for a completed artifact that
// matches the current update state's version and SHA-256, and emits a
// DownloadReady event so the UI can offer "Reveal in file browser"
// without re-downloading.
func (a *App) surfaceExistingDownload() {
	a.mu.RLock()
	dl := a.downloader
	c := a.updater
	a.mu.RUnlock()
	if dl == nil || c == nil {
		return
	}
	s := c.State()
	if s.LatestVersion == "" || s.DownloadURL == "" || s.DownloadSHA256 == "" {
		return
	}
	if p, ok := dl.LookupExisting(s.LatestVersion, s.DownloadURL, s.DownloadSHA256); ok {
		runtime.EventsEmit(a.ctx, downloadEventName, updater.DownloadState{
			Stage:      updater.DownloadReady,
			Version:    s.LatestVersion,
			LocalPath:  p,
			BytesDone:  s.DownloadSizeBytes,
			BytesTotal: s.DownloadSizeBytes,
		})
	}
	// Best-effort cleanup of stale version directories.
	dl.CleanupOldVersions(s.LatestVersion)
}

// GetDownloadState returns an idle DownloadState. Exists so Wails
// includes updater.DownloadState in the generated TypeScript bindings —
// the live state is delivered to the frontend via the "update:download"
// event, not by polling this method.
func (a *App) GetDownloadState() updater.DownloadState {
	return updater.DownloadState{Stage: updater.DownloadIdle}
}

// DownloadUpdate begins a background download of the latest update
// artifact for the current platform. Returns immediately; progress is
// published on the "update:download" event.
//
// Returns an error if the manifest has not yet been fetched, the
// current platform is unsupported, or another download is in flight.
func (a *App) DownloadUpdate() error {
	a.mu.RLock()
	dl := a.downloader
	c := a.updater
	a.mu.RUnlock()
	if dl == nil || c == nil {
		return errors.New("updater not initialized")
	}
	s := c.State()
	if !s.PlatformSupported {
		return errors.New("no download available for this platform")
	}
	if s.LatestVersion == "" || s.DownloadURL == "" || s.DownloadSHA256 == "" {
		return errors.New("no update available — try checking for updates first")
	}

	go func() {
		ctx := context.Background()
		_, err := dl.Download(ctx, s.LatestVersion, s.DownloadURL, s.DownloadSHA256, s.DownloadSizeBytes)
		if err != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("download failed: %v", err))
		}
	}()
	return nil
}

// CancelDownload cancels an in-flight download, if any.
func (a *App) CancelDownload() {
	a.mu.RLock()
	dl := a.downloader
	a.mu.RUnlock()
	if dl != nil {
		dl.Cancel()
	}
}

// RevealDownloadedUpdate opens the file manager at the directory
// containing the downloaded artifact. localPath must be inside the
// updater cache directory — defensive check to avoid bound-parameter
// abuse opening arbitrary system paths.
func (a *App) RevealDownloadedUpdate(localPath string) error {
	cacheDir, err := updateCacheDir()
	if err != nil {
		return err
	}
	absPath, err := filepath.Abs(localPath)
	if err != nil {
		return fmt.Errorf("resolve path: %w", err)
	}
	absCache, err := filepath.Abs(cacheDir)
	if err != nil {
		return fmt.Errorf("resolve cache: %w", err)
	}
	rel, err := filepath.Rel(absCache, absPath)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return errors.New("path is outside the update cache")
	}
	return openInExplorer(filepath.Dir(absPath))
}
