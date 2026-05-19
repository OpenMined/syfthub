// agent_attachments.go adds the client-side attachment surface to an
// AgentClientSession. The direct peer-to-peer path supports the inline tier
// (≤ 64 KiB): the bytes ride, encrypted, inside an agent_user_attachment
// message. Object-store (large-file) attachments over the direct path are a
// documented follow-up — see syfthub-desktop/docs/p2p-agent-direct-nats-design.md.

package transport

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"

	"github.com/google/uuid"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// AttachmentOpts holds the per-call options for sending an attachment.
type AttachmentOpts struct {
	// Name is the display file name (defaults to "attachment.bin").
	Name string
	// MIME is the declared media type (defaults to application/octet-stream).
	MIME string
}

// SendAttachmentBytes sends data to the agent as an inline attachment and
// returns the assigned file_id. Reference it in subsequent text with the URI
// scheme attachment://{file_id}.
//
// Payloads larger than the inline limit return an error: object-store
// attachments are not yet supported on the direct P2P path.
func (s *AgentClientSession) SendAttachmentBytes(_ context.Context, data []byte, opts AttachmentOpts) (string, error) {
	if len(data) > syfthubapi.InlineMaxBytes {
		return "", fmt.Errorf(
			"attachment is %d bytes; the direct peer-to-peer path supports only inline attachments up to %d bytes",
			len(data), syfthubapi.InlineMaxBytes)
	}
	name := opts.Name
	if name == "" {
		name = "attachment.bin"
	}
	mimeType := opts.MIME
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}
	fileID := "att-" + uuid.NewString()
	sum := sha256.Sum256(data)
	info := syfthubapi.AttachmentInfo{
		FileID:          fileID,
		Name:            name,
		MIME:            mimeType,
		SizeBytes:       int64(len(data)),
		PlaintextSHA256: hex.EncodeToString(sum[:]),
		Transport:       syfthubapi.AttachmentTransportInline,
		InlineDataB64:   base64.StdEncoding.EncodeToString(data),
	}
	if err := s.publishRequest(syfthubapi.MsgTypeAgentUserAttachment,
		syfthubapi.AgentUserAttachmentPayload{SessionID: s.SessionID, Attachment: info}); err != nil {
		return "", err
	}
	return fileID, nil
}

// SendAttachment reads r (up to the inline limit) and sends it as an inline
// attachment via SendAttachmentBytes.
func (s *AgentClientSession) SendAttachment(ctx context.Context, r io.Reader, opts AttachmentOpts) (string, error) {
	data, err := io.ReadAll(io.LimitReader(r, syfthubapi.InlineMaxBytes+1))
	if err != nil {
		return "", fmt.Errorf("read attachment: %w", err)
	}
	return s.SendAttachmentBytes(ctx, data, opts)
}

// DownloadAttachment streams an agent-emitted object-store attachment into w.
// Inline-tier attachments arrive with the agent.attachment event itself and
// need no download; object-store attachments are not yet supported on the
// direct P2P path.
func (s *AgentClientSession) DownloadAttachment(_ context.Context, fileID string, _ io.Writer) error {
	return fmt.Errorf(
		"attachment %s is object-store tier; object-store attachments are not yet supported on the direct peer-to-peer path",
		fileID)
}
