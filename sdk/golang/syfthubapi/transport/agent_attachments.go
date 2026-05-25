// agent_attachments.go adds the client-side attachment surface to an
// AgentClientSession. Both transports are supported on the direct P2P path:
//   - inline (≤ InlineMaxBytes): bytes ride, encrypted, inside an
//     agent_user_attachment NATS message (single round-trip).
//   - object_store (> InlineMaxBytes): ciphertext stored in NATS JetStream
//     Object Store under a per-session bucket; the user-attachment message
//     carries only metadata + the wrapped per-file key.
//
// Object_store transfers require the dialer to have been built with
// WithAttachmentStore(transport) AND the session opened with the
// AttachmentCapability so the session AES key has been minted and shared.

package transport

import (
	"bytes"
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

// SendAttachmentBytes is a buffered convenience wrapper around SendAttachment.
// Prefer SendAttachment with an io.Reader for large payloads to avoid the
// in-memory copy.
func (s *AgentClientSession) SendAttachmentBytes(ctx context.Context, data []byte, opts AttachmentOpts) (syfthubapi.AttachmentInfo, error) {
	return s.SendAttachment(ctx, bytes.NewReader(data), opts)
}

// SendAttachment streams r to the agent as an attachment and returns the
// AttachmentInfo describing the transmitted file (file_id, transport, size,
// plaintext SHA-256). Reference the file in subsequent text with the URI
// scheme attachment://{file_id}.
//
// Behavior:
//   - Payloads ≤ syfthubapi.InlineMaxBytes ride inline (base64) in the
//     encrypted user-attachment message — single round-trip, low latency.
//   - Larger payloads spill to JetStream Object Store via the dialer's
//     transport. Requires the dialer to have been built with
//     WithAttachmentStore(transport) AND the session opened with the
//     AttachmentCapability; otherwise this returns an error and the file
//     is NOT sent.
func (s *AgentClientSession) SendAttachment(_ context.Context, r io.Reader, opts AttachmentOpts) (syfthubapi.AttachmentInfo, error) {
	name := opts.Name
	if name == "" {
		name = "attachment.bin"
	}
	mimeType := opts.MIME
	if mimeType == "" {
		mimeType = "application/octet-stream"
	}

	// Read up to InlineMaxBytes+1 so we can detect spill-over in a single
	// pass without re-reading on the small-file path.
	head, err := io.ReadAll(io.LimitReader(r, int64(syfthubapi.InlineMaxBytes)+1))
	if err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("read attachment head: %w", err)
	}

	fileID := "att-" + uuid.NewString()

	if len(head) <= syfthubapi.InlineMaxBytes {
		sum := sha256.Sum256(head)
		info := syfthubapi.AttachmentInfo{
			FileID:          fileID,
			Name:            name,
			MIME:            mimeType,
			SizeBytes:       int64(len(head)),
			PlaintextSHA256: hex.EncodeToString(sum[:]),
			Transport:       syfthubapi.AttachmentTransportInline,
			InlineDataB64:   base64.StdEncoding.EncodeToString(head),
		}
		if err := s.publishUserAttachment(info); err != nil {
			return syfthubapi.AttachmentInfo{}, err
		}
		return info, nil
	}

	// Spill-over: route through Object Store.
	up, err := s.ensureUploader()
	if err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("attachment exceeds inline limit (%d bytes): %w",
			syfthubapi.InlineMaxBytes, err)
	}
	combined := io.MultiReader(bytes.NewReader(head), r)
	info, err := up.Upload(fileID, name, mimeType, -1, combined)
	if err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("object-store upload: %w", err)
	}
	if err := s.publishUserAttachment(info); err != nil {
		return syfthubapi.AttachmentInfo{}, err
	}
	return info, nil
}

func (s *AgentClientSession) publishUserAttachment(info syfthubapi.AttachmentInfo) error {
	return s.publishRequest(syfthubapi.MsgTypeAgentUserAttachment,
		syfthubapi.AgentUserAttachmentPayload{SessionID: s.SessionID, Attachment: info})
}

// DownloadAttachment streams the plaintext bytes of an agent-emitted
// object_store-tier attachment to w. Inline-tier attachments arrive with the
// agent.attachment event itself and need no download — read
// AttachmentEvent.Bytes() instead. info is the AttachmentInfo form of the
// inbound event; convert from agenttypes.AttachmentEvent via
// syfthubapi.AttachmentInfoFromEvent.
//
// On verification failure w MAY have received partial data; the caller is
// responsible for cleanup. Requires the dialer to have been built with
// WithAttachmentStore(transport) AND the session opened with the
// AttachmentCapability.
func (s *AgentClientSession) DownloadAttachment(_ context.Context, info syfthubapi.AttachmentInfo, w io.Writer) error {
	if info.Transport != syfthubapi.AttachmentTransportObjectStore {
		return fmt.Errorf("attachment %s has transport=%q; DownloadAttachment is for object_store only",
			info.FileID, info.Transport)
	}
	dl, err := s.ensureDownloader()
	if err != nil {
		return fmt.Errorf("object-store downloader unavailable: %w", err)
	}
	osDl, ok := dl.(*ObjectStoreDownloader)
	if !ok {
		return fmt.Errorf("downloader %T does not support streaming", dl)
	}
	return osDl.DownloadStream(&info, w)
}

// ensureUploader lazily builds the object-store uploader on first large-file
// send. Returns an error if the dialer wasn't built with WithAttachmentStore
// or the session lacks an attachment key.
func (s *AgentClientSession) ensureUploader() (syfthubapi.AttachmentUploader, error) {
	s.upOnce.Do(func() {
		if s.attachmentStore == nil {
			s.upErr = fmt.Errorf("dialer not configured for object-store attachments — call WithAttachmentStore(transport)")
			return
		}
		if len(s.sessionAESKey) != 32 {
			s.upErr = fmt.Errorf("session lacks session_attachment_key — open the session with AttachmentCapability")
			return
		}
		up, err := NewObjectStoreUploader(context.Background(), s.sessionAESKey, s.attachmentStore, s.SessionID)
		if err != nil {
			s.upErr = err
			return
		}
		s.uploader = up
	})
	return s.uploader, s.upErr
}

// ensureDownloader lazily builds the object-store downloader on first large-
// file receive. Same prerequisites as ensureUploader.
func (s *AgentClientSession) ensureDownloader() (syfthubapi.AttachmentDownloader, error) {
	s.dlOnce.Do(func() {
		if s.attachmentStore == nil {
			s.dlErr = fmt.Errorf("dialer not configured for object-store attachments — call WithAttachmentStore(transport)")
			return
		}
		if len(s.sessionAESKey) != 32 {
			s.dlErr = fmt.Errorf("session lacks session_attachment_key — open the session with AttachmentCapability")
			return
		}
		dl, err := NewObjectStoreDownloader(context.Background(), s.sessionAESKey, s.attachmentStore)
		if err != nil {
			s.dlErr = err
			return
		}
		s.downloader = dl
	})
	return s.downloader, s.dlErr
}
