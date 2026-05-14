// Package main: chat attachment bindings.
//
// Attachments flow through the active AgentSessionClient: inline (≤64 KiB) over
// the hub WebSocket, larger payloads over the aggregator's HTTP side-channel.
// Tier selection is handled by the SDK; this file caches inbound bytes for
// preview/save and forwards outbound uploads.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"mime"
	"os"
	"os/exec"
	"path/filepath"
	gosysruntime "runtime"
	"strings"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// AttachmentSummary is returned to the frontend after staging an attachment
// for the active agent session. There is no LocalPath — the bytes live on the
// host's side of the tunnel, not on the client.
type AttachmentSummary struct {
	FileID    string `json:"file_id"`
	Name      string `json:"name"`
	MIME      string `json:"mime"`
	SizeBytes int64  `json:"size_bytes"`
	SHA256    string `json:"sha256"`
}

// agentAttachment caches an inbound attachment for the active session. For
// inline-tier attachments the SDK delivered the bytes in the event; we decode
// once when the event arrives so save/preview is a buffer copy. For
// object-store-tier attachments we keep the metadata and lazily call
// AgentSessionClient.DownloadAttachment on demand.
type agentAttachment struct {
	Meta  syfthub.AttachmentEvent
	Bytes []byte // populated only for inline transport
}

// cacheAgentAttachment stores an inbound attachment under the active session's
// cache. No-op when the session has rotated since the event was emitted.
func (a *App) cacheAgentAttachment(sessionID string, ev *syfthub.AttachmentEvent) error {
	entry := &agentAttachment{Meta: *ev}

	if ev.Transport == "inline" {
		raw, err := ev.Bytes()
		if err != nil {
			return fmt.Errorf("decode inline bytes: %w", err)
		}
		if ev.SizeBytes > 0 && int64(len(raw)) != ev.SizeBytes {
			return fmt.Errorf("size mismatch: declared %d, actual %d", ev.SizeBytes, len(raw))
		}
		if ev.PlaintextSHA256 != "" {
			sum := sha256.Sum256(raw)
			if hex.EncodeToString(sum[:]) != ev.PlaintextSHA256 {
				return fmt.Errorf("sha256 mismatch on file %s", ev.FileID)
			}
		}
		entry.Bytes = raw
	}

	a.agentMu.Lock()
	defer a.agentMu.Unlock()
	if a.agentSession == nil || a.agentSession.SessionID != sessionID || a.agentAttachments == nil {
		return nil // session rotated; drop silently
	}
	a.agentAttachments[ev.FileID] = entry
	return nil
}

// activeAttachment returns the live AgentSessionClient and a cached attachment
// entry under one mutex acquisition. Either return can be nil — callers check
// individually so they can produce specific error messages.
func (a *App) activeAttachment(fileID string) (*syfthub.AgentSessionClient, *agentAttachment) {
	a.agentMu.Lock()
	defer a.agentMu.Unlock()
	if a.agentAttachments == nil {
		return a.agentSession, nil
	}
	return a.agentSession, a.agentAttachments[fileID]
}

// attachmentOpTimeout bounds a single attachment transfer (save/download/inline).
// Generous enough for slow networks streaming object-store payloads.
const attachmentOpTimeout = 2 * time.Minute

// attachmentContext returns a context with attachmentOpTimeout derived from a.ctx.
func (a *App) attachmentContext() (context.Context, context.CancelFunc) {
	return context.WithTimeout(a.ctx, attachmentOpTimeout)
}

// attachmentDownloadDir returns ~/Downloads, creating it if missing.
func attachmentDownloadDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("user home: %w", err)
	}
	dir := filepath.Join(home, "Downloads")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", fmt.Errorf("mkdir %s: %w", dir, err)
	}
	return dir, nil
}

// uniqueDestPath returns destDir/baseName, appending " (n)" before the
// extension if a file with that exact name already exists. Bounded at 999 to
// avoid pathological loops.
func uniqueDestPath(destDir, baseName string) string {
	candidate := filepath.Join(destDir, baseName)
	if _, err := os.Stat(candidate); os.IsNotExist(err) {
		return candidate
	}
	ext := filepath.Ext(baseName)
	stem := strings.TrimSuffix(baseName, ext)
	for i := 1; i < 1000; i++ {
		candidate = filepath.Join(destDir, fmt.Sprintf("%s (%d)%s", stem, i, ext))
		if _, err := os.Stat(candidate); os.IsNotExist(err) {
			return candidate
		}
	}
	return filepath.Join(destDir, fmt.Sprintf("%s-%d%s", stem, os.Getpid(), ext))
}

// resolveAttachment returns (sc, entry) for fileID, or an error if no session
// is active or the attachment is unknown. Callers use this before touching
// any disk or context so error responses don't depend on Wails state.
func (a *App) resolveAttachment(fileID string) (*syfthub.AgentSessionClient, *agentAttachment, error) {
	sc, entry := a.activeAttachment(fileID)
	if sc == nil {
		return nil, nil, fmt.Errorf("no active agent session")
	}
	if entry == nil {
		return nil, nil, fmt.Errorf("attachment %s not found in current session", fileID)
	}
	return sc, entry, nil
}

// writeAttachment writes a resolved attachment's bytes into w. Inline reads
// from cache; object-store streams via the SDK's HTTP side-channel.
func (a *App) writeAttachment(ctx context.Context, sc *syfthub.AgentSessionClient, entry *agentAttachment, w io.Writer) error {
	if entry.Bytes != nil {
		_, err := w.Write(entry.Bytes)
		return err
	}
	if entry.Meta.Transport != "object_store" {
		return fmt.Errorf("attachment %s has unknown transport %q", entry.Meta.FileID, entry.Meta.Transport)
	}
	return sc.DownloadAttachment(ctx, entry.Meta.FileID, w)
}

// SaveAgentAttachment writes an agent-emitted attachment into ~/Downloads
// under its original filename (with " (n)" suffix on collision). Inline-tier
// bytes are served from the in-memory cache; object-store-tier bytes are
// streamed via the SDK's HTTP relay.
func (a *App) SaveAgentAttachment(fileID, suggestedName string) (string, error) {
	if fileID == "" {
		return "", fmt.Errorf("file_id required")
	}
	sc, entry, err := a.resolveAttachment(fileID)
	if err != nil {
		return "", err
	}

	downloads, err := attachmentDownloadDir()
	if err != nil {
		return "", err
	}

	// Path-traversal guard: only the basename ever lands in Downloads.
	name := filepath.Base(strings.TrimSpace(suggestedName))
	if name == "" || name == "." || name == ".." || name == string(filepath.Separator) {
		name = fileID
	}
	dest := uniqueDestPath(downloads, name)

	out, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		return "", fmt.Errorf("open dest: %w", err)
	}
	defer out.Close()

	ctx, cancel := a.attachmentContext()
	defer cancel()
	if err := a.writeAttachment(ctx, sc, entry, out); err != nil {
		_ = os.Remove(dest)
		return "", err
	}
	return dest, nil
}

// OpenInDefaultApp launches the OS's default handler for the file at path.
func (a *App) OpenInDefaultApp(path string) error {
	if path == "" {
		return fmt.Errorf("path is required")
	}
	if _, err := os.Stat(path); err != nil {
		return fmt.Errorf("file not found: %w", err)
	}
	var cmd *exec.Cmd
	switch gosysruntime.GOOS {
	case "darwin":
		cmd = exec.Command("open", path)
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", path)
	default:
		cmd = exec.Command("xdg-open", path)
	}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("launch failed: %w", err)
	}
	go func() { _ = cmd.Wait() }()
	return nil
}

// BrowseForAttachment opens a native file picker and returns the absolute path
// (or empty string on cancel).
func (a *App) BrowseForAttachment() string {
	path, err := runtime.OpenFileDialog(a.ctx, runtime.OpenDialogOptions{
		Title: "Attach file to agent",
	})
	if err != nil {
		runtime.LogWarning(a.ctx, fmt.Sprintf("Attachment file dialog error: %v", err))
		return ""
	}
	return path
}

// AttachToActiveSession reads the file at hostPath and sends it to the agent
// via the hub WebSocket (inline) or aggregator HTTP relay (object-store),
// whichever the size dictates. Returns the assigned file_id and metadata so
// the frontend can render a staged-attachment chip and reference the file in
// follow-up messages with the attachment://{file_id} URI.
func (a *App) AttachToActiveSession(hostPath string) (*AttachmentSummary, error) {
	a.agentMu.Lock()
	sc := a.agentSession
	a.agentMu.Unlock()
	if sc == nil {
		return nil, fmt.Errorf("no active agent session")
	}

	st, err := os.Stat(hostPath)
	if err != nil {
		return nil, fmt.Errorf("stat: %w", err)
	}
	if st.IsDir() {
		return nil, fmt.Errorf("attachments must be files, not directories")
	}

	body, err := os.ReadFile(hostPath)
	if err != nil {
		return nil, fmt.Errorf("read: %w", err)
	}

	name := filepath.Base(hostPath)
	mimeType := mime.TypeByExtension(filepath.Ext(hostPath))
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}

	ctx, cancel := a.attachmentContext()
	defer cancel()
	fileID, err := sc.SendAttachmentBytes(ctx, body, syfthub.AttachmentOpts{
		Name: name,
		MIME: mimeType,
	})
	if err != nil {
		return nil, fmt.Errorf("send attachment: %w", err)
	}

	sum := sha256.Sum256(body)
	return &AttachmentSummary{
		FileID:    fileID,
		Name:      name,
		MIME:      mimeType,
		SizeBytes: int64(len(body)),
		SHA256:    hex.EncodeToString(sum[:]),
	}, nil
}

// DownloadActiveSessionAttachment writes fileID's bytes to destPath. Used
// when the user picks "Save to…" with a custom path.
func (a *App) DownloadActiveSessionAttachment(fileID, destPath string) error {
	sc, entry, err := a.resolveAttachment(fileID)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(destPath), 0o700); err != nil {
		return fmt.Errorf("mkdir: %w", err)
	}
	out, err := os.OpenFile(destPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("open dest: %w", err)
	}
	defer out.Close()

	ctx, cancel := a.attachmentContext()
	defer cancel()
	return a.writeAttachment(ctx, sc, entry, out)
}

// AttachmentInlineBytes returns the plaintext bytes for an attachment so the
// frontend can render image previews / inline content in the chat timeline.
// For inline-tier attachments this is a cache read; for object-store-tier it
// streams the bytes through SDK's HTTP relay into memory. maxBytes caps the
// returned slice; 0 means no limit.
func (a *App) AttachmentInlineBytes(fileID string, maxBytes int64) ([]byte, error) {
	sc, entry, err := a.resolveAttachment(fileID)
	if err != nil {
		return nil, err
	}
	if entry.Bytes != nil {
		if maxBytes > 0 && int64(len(entry.Bytes)) > maxBytes {
			return entry.Bytes[:maxBytes], nil
		}
		return entry.Bytes, nil
	}

	// Object-store tier: stream into a capped buffer.
	ctx, cancel := a.attachmentContext()
	defer cancel()
	buf := newLimitedBuffer(maxBytes)
	if err := sc.DownloadAttachment(ctx, fileID, buf); err != nil {
		return nil, fmt.Errorf("download attachment: %w", err)
	}
	return buf.bytes, nil
}

// limitedBuffer is an io.Writer that stores up to max bytes (0 = unlimited).
// Used by AttachmentInlineBytes to bound previews of large object-store
// attachments without buffering the entire payload in memory.
type limitedBuffer struct {
	bytes []byte
	max   int64
}

func newLimitedBuffer(max int64) *limitedBuffer {
	b := &limitedBuffer{max: max}
	if max > 0 {
		b.bytes = make([]byte, 0, max)
	}
	return b
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	n := len(p)
	if b.max > 0 {
		remaining := b.max - int64(len(b.bytes))
		if remaining <= 0 {
			return n, nil // discard but report consumed so the SDK keeps streaming
		}
		if int64(n) > remaining {
			b.bytes = append(b.bytes, p[:remaining]...)
			return n, nil
		}
	}
	b.bytes = append(b.bytes, p...)
	return n, nil
}
