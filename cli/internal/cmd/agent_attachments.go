package cmd

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"mime"
	"os"
	"path/filepath"

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
	if st.Size() > syfthub.InlineAttachmentMaxBytes {
		return fmt.Errorf("file is %d bytes; inline ceiling is %d (Object Store transport ships in PR-7)", st.Size(), syfthub.InlineAttachmentMaxBytes)
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
func saveAgentAttachment(e *syfthub.AttachmentEvent) error {
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

	if e.Transport != "inline" {
		return fmt.Errorf("transport %q not supported by PR-4 CLI (Object Store ships in PR-7)", e.Transport)
	}

	body, err := e.Bytes()
	if err != nil {
		return err
	}

	sum := sha256.Sum256(body)
	if hex.EncodeToString(sum[:]) != e.PlaintextSHA256 {
		return fmt.Errorf("sha256 mismatch on %s", e.FileID)
	}

	name := e.Name
	if name == "" {
		name = e.FileID
	}
	// Sanitize: only allow the basename — refuse anything containing path
	// separators to avoid writing outside dir.
	name = filepath.Base(name)
	if name == "." || name == ".." || name == string(filepath.Separator) {
		name = e.FileID
	}

	dest := filepath.Join(dir, name)
	if err := os.WriteFile(dest, body, 0o600); err != nil {
		return fmt.Errorf("write: %w", err)
	}
	fmt.Printf("\n📎 saved attachment %s (%d bytes) → %s\n", e.FileID, e.SizeBytes, dest)
	return nil
}
