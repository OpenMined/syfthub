package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// AttachmentSummary is the payload returned to the frontend after staging an
// attachment for the active local agent session.
type AttachmentSummary struct {
	FileID    string `json:"file_id"`
	Name      string `json:"name"`
	MIME      string `json:"mime"`
	SizeBytes int64  `json:"size_bytes"`
	SHA256    string `json:"sha256"`
	// LocalPath is the on-disk path inside the session's AttachmentDir.
	// The agent runner reads from here.
	LocalPath string `json:"local_path"`
}

// materializeAgentInlineAttachment decodes the inline base64 bytes from an
// agent.attachment event and writes them to attachmentsDir using the
// filename pattern {file_id}{ext} so DownloadActiveSessionAttachment and
// AttachmentInlineBytes (both of which glob by file_id prefix) can find
// the file later. data is the decoded JSON payload of the event.
//
// No-op if attachmentsDir is empty (attachments disabled), if the transport
// isn't inline, or if the inline_data_b64 field is missing.
func materializeAgentInlineAttachment(attachmentsDir string, data map[string]any) error {
	if attachmentsDir == "" {
		return nil
	}
	transport, _ := data["transport"].(string)
	if transport != "inline" {
		return nil
	}
	fileID, _ := data["file_id"].(string)
	if fileID == "" {
		return fmt.Errorf("missing file_id")
	}
	inlineB64, _ := data["inline_data_b64"].(string)
	if inlineB64 == "" {
		return nil // metadata-only event, nothing to write
	}
	raw, err := base64.StdEncoding.DecodeString(inlineB64)
	if err != nil {
		return fmt.Errorf("decode inline_data_b64: %w", err)
	}

	// Verify declared size + SHA when present — the same checks the inbound
	// materializer enforces. Bad bytes never reach disk.
	if sizeF, ok := data["size_bytes"].(float64); ok {
		if int64(len(raw)) != int64(sizeF) {
			return fmt.Errorf("size mismatch: declared %d, actual %d", int64(sizeF), len(raw))
		}
	}
	if expected, _ := data["plaintext_sha256"].(string); expected != "" {
		sum := sha256.Sum256(raw)
		if hex.EncodeToString(sum[:]) != expected {
			return fmt.Errorf("sha256 mismatch")
		}
	}

	name, _ := data["name"].(string)
	ext := filepath.Ext(name)
	dest := filepath.Join(attachmentsDir, fileID+ext)
	return os.WriteFile(dest, raw, 0o600)
}

// attachmentDownloadDir returns ~/Downloads, creating it if missing. The
// default destination for agent-emitted attachment saves — chosen because
// it's the universal "I'll find this later" location on every desktop OS.
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
// extension if a file with that exact name already exists. Idempotent
// across many concurrent saves; bounded at 999 to avoid pathological loops.
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
	// Pathological case — fall back to timestamp-suffixed name. Unlikely.
	return filepath.Join(destDir, fmt.Sprintf("%s-%d%s", stem, os.Getpid(), ext))
}

// SaveAgentAttachment copies an agent-emitted attachment from the per-session
// AttachmentDir into the user's ~/Downloads folder under the original
// filename (with " (n)" suffix on collision). Returns the absolute path of
// the saved file so the frontend can surface it in the chip.
//
// Replaces the previous "open folder picker → write" two-click flow.
func (a *App) SaveAgentAttachment(fileID, suggestedName string) (string, error) {
	if fileID == "" {
		return "", fmt.Errorf("file_id required")
	}
	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentMu.Unlock()
	if sessionID == "" {
		return "", fmt.Errorf("no active agent session")
	}
	api, err := a.requireAPI()
	if err != nil {
		return "", err
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return "", fmt.Errorf("agent session manager not initialized")
	}
	sess, ok := sm.GetSession(sessionID)
	if !ok {
		return "", fmt.Errorf("session %s not found", sessionID)
	}
	if sess.AttachmentDir == "" {
		return "", fmt.Errorf("session has no attachment dir")
	}

	matches, err := filepath.Glob(filepath.Join(sess.AttachmentDir, fileID+"*"))
	if err != nil {
		return "", fmt.Errorf("glob: %w", err)
	}
	if len(matches) == 0 {
		return "", fmt.Errorf("attachment %s not found in session (was it materialized?)", fileID)
	}
	src := matches[0]
	in, err := os.Open(src)
	if err != nil {
		return "", fmt.Errorf("open src: %w", err)
	}
	defer in.Close()

	downloads, err := attachmentDownloadDir()
	if err != nil {
		return "", err
	}
	name := strings.TrimSpace(suggestedName)
	if name == "" {
		name = filepath.Base(src)
	}
	// Path-traversal guard: only the basename ever lands in Downloads.
	name = filepath.Base(name)
	if name == "." || name == ".." || name == string(filepath.Separator) {
		name = fileID + filepath.Ext(src)
	}
	dest := uniqueDestPath(downloads, name)

	out, err := os.OpenFile(dest, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		return "", fmt.Errorf("open dest: %w", err)
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		_ = os.Remove(dest)
		return "", fmt.Errorf("copy: %w", err)
	}
	return dest, nil
}

// BrowseForAttachment opens a native file picker (no filter — attachments
// can be any MIME) and returns the absolute path, or an empty string if
// the user cancelled. Bound to the desktop UI's paperclip button.
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

// AttachToActiveSession reads the file at hostPath, copies it into the
// active agent session's AttachmentDir, and delivers it to the session's
// attachment channel so the runner can pick it up.
//
// Returns the metadata that was queued for the runner. Returns an error
// if there is no active session or attachments are not enabled for that
// session (the endpoint must declare accepts_attachments: true).
func (a *App) AttachToActiveSession(hostPath string) (*AttachmentSummary, error) {
	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentMu.Unlock()
	if sessionID == "" {
		return nil, fmt.Errorf("no active agent session")
	}

	api, err := a.requireAPI()
	if err != nil {
		return nil, err
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return nil, fmt.Errorf("agent session manager not initialized")
	}
	sess, ok := sm.GetSession(sessionID)
	if !ok {
		return nil, fmt.Errorf("session %s not found", sessionID)
	}
	if !sess.AttachmentsEnabled() {
		return nil, fmt.Errorf("attachments not enabled for this endpoint (set accepts_attachments: true in the endpoint frontmatter)")
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

	sum := sha256.Sum256(body)
	fileID := "att-" + sha256Short(sum[:])
	destName := fileID + filepath.Ext(hostPath)
	dest := filepath.Join(sess.AttachmentDir, destName)
	if err := os.WriteFile(dest, body, 0o600); err != nil {
		return nil, fmt.Errorf("stage: %w", err)
	}

	info := syfthubapi.AttachmentInfo{
		FileID:          fileID,
		Name:            name,
		MIME:            mimeType,
		SizeBytes:       int64(len(body)),
		PlaintextSHA256: hex.EncodeToString(sum[:]),
		Transport:       syfthubapi.AttachmentTransportInline,
		LocalPath:       dest,
	}
	if !sess.DeliverAttachment(info) {
		return nil, fmt.Errorf("attachment channel full")
	}

	return &AttachmentSummary{
		FileID:    info.FileID,
		Name:      info.Name,
		MIME:      info.MIME,
		SizeBytes: info.SizeBytes,
		SHA256:    info.PlaintextSHA256,
		LocalPath: info.LocalPath,
	}, nil
}

// DownloadActiveSessionAttachment copies the file referenced by fileID out
// of the active session's AttachmentDir to destPath.
//
// Useful when the agent emits an attachment and the user wants to save it.
// fileID must correspond to a file the runner produced in this session.
func (a *App) DownloadActiveSessionAttachment(fileID, destPath string) error {
	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentMu.Unlock()
	if sessionID == "" {
		return fmt.Errorf("no active agent session")
	}
	api, err := a.requireAPI()
	if err != nil {
		return err
	}
	sm := api.AgentSessionManager()
	if sm == nil {
		return fmt.Errorf("agent session manager not initialized")
	}
	sess, ok := sm.GetSession(sessionID)
	if !ok {
		return fmt.Errorf("session %s not found", sessionID)
	}
	if sess.AttachmentDir == "" {
		return fmt.Errorf("session has no attachment dir")
	}

	// Match by file_id prefix in the session dir.
	matches, err := filepath.Glob(filepath.Join(sess.AttachmentDir, fileID+"*"))
	if err != nil {
		return fmt.Errorf("glob: %w", err)
	}
	if len(matches) == 0 {
		return fmt.Errorf("attachment %s not found in session", fileID)
	}
	src := matches[0]
	in, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("open src: %w", err)
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(destPath), 0o700); err != nil {
		return fmt.Errorf("mkdir: %w", err)
	}
	out, err := os.OpenFile(destPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("open dest: %w", err)
	}
	defer out.Close()
	if _, err := io.Copy(out, in); err != nil {
		return fmt.Errorf("copy: %w", err)
	}
	return nil
}

// AttachmentInlineBytes returns the plaintext bytes for an inline attachment
// the agent emitted. The frontend uses this to render images / preview
// content directly in the chat timeline without exposing the on-disk path.
//
// Returns at most maxBytes; the rest is truncated. Pass 0 for no limit.
func (a *App) AttachmentInlineBytes(fileID string, maxBytes int64) ([]byte, error) {
	a.agentMu.Lock()
	sessionID := a.agentSessionID
	a.agentMu.Unlock()
	if sessionID == "" {
		return nil, fmt.Errorf("no active agent session")
	}
	api, err := a.requireAPI()
	if err != nil {
		return nil, err
	}
	sm := api.AgentSessionManager()
	sess, ok := sm.GetSession(sessionID)
	if !ok {
		return nil, fmt.Errorf("session not found")
	}
	matches, err := filepath.Glob(filepath.Join(sess.AttachmentDir, fileID+"*"))
	if err != nil || len(matches) == 0 {
		return nil, fmt.Errorf("attachment %s not found", fileID)
	}
	f, err := os.Open(matches[0])
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var buf bytes.Buffer
	if maxBytes > 0 {
		_, err = io.Copy(&buf, io.LimitReader(f, maxBytes))
	} else {
		_, err = io.Copy(&buf, f)
	}
	if err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func sha256Short(b []byte) string {
	return hex.EncodeToString(b[:8])
}
