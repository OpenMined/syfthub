package cmd

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"mime"
	"os"
	"path/filepath"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

// uploadAgentAttachment reads a file from disk and uploads it as a
// user.attachment WebSocket frame. PR-4 supports the inline tier only.
func uploadAgentAttachment(ctx context.Context, session *syfthub.AgentSessionClient, path string) error {
	st, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("stat: %w", err)
	}
	if st.IsDir() {
		return fmt.Errorf("attachments must be files, not directories")
	}

	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("open: %w", err)
	}
	defer f.Close()

	name := filepath.Base(path)
	mimeType := mime.TypeByExtension(filepath.Ext(path))
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}

	fileID, err := session.SendAttachment(ctx, f, syfthub.AttachmentOpts{
		Name: name,
		MIME: mimeType,
	})
	if err != nil {
		return err
	}
	fmt.Printf("📎 attached %s (%d bytes) → %s\n", name, st.Size(), fileID)
	return nil
}

// saveAgentAttachment decodes an inbound attachment and saves it under
// --save-attachments-to (or the current directory if unset).
//
// Handles both transports:
//   - inline: decode in-event base64 and verify SHA
//   - object_store: stream via DownloadAttachment on the active session
func saveAgentAttachment(session *syfthub.AgentSessionClient, e *syfthub.AttachmentEvent) error {
	dir := agentSaveAttachmentsTo
	if dir == "" {
		var err error
		dir, err = os.Getwd()
		if err != nil {
			return fmt.Errorf("getwd: %w", err)
		}
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("mkdir: %w", err)
	}

	name := e.Name
	if name == "" {
		name = e.FileID
	}
	name = filepath.Base(name)
	if name == "." || name == ".." || name == string(filepath.Separator) {
		name = e.FileID
	}
	dest := filepath.Join(dir, name)

	var body []byte
	switch e.Transport {
	case "inline":
		var err error
		body, err = e.Bytes()
		if err != nil {
			return err
		}
	case "object_store":
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		var buf bytes.Buffer
		if err := session.DownloadAttachment(ctx, e.FileID, &buf); err != nil {
			return fmt.Errorf("download: %w", err)
		}
		body = buf.Bytes()
	default:
		return fmt.Errorf("unknown attachment transport %q", e.Transport)
	}

	sum := sha256.Sum256(body)
	if e.PlaintextSHA256 != "" && hex.EncodeToString(sum[:]) != e.PlaintextSHA256 {
		return fmt.Errorf("sha256 mismatch on %s", e.FileID)
	}
	if err := os.WriteFile(dest, body, 0o600); err != nil {
		return fmt.Errorf("write: %w", err)
	}
	fmt.Printf("\n📎 saved attachment %s (%d bytes) → %s\n", e.FileID, e.SizeBytes, dest)
	return nil
}
