package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
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
