package syfthubapi

import (
	"encoding/json"
	"io"
)

// Spec version: see docs/architecture/attachments.md
//
// This file defines the wire-level types for the attachment protocol.
// Bytes flow through one of two transports:
//   - "inline":       base64 bytes embedded in the event payload (≤ InlineMaxBytes)
//   - "object_store": ciphertext stored in NATS JetStream Object Store, keyed
//                     to the session; metadata event carries the wrapped AES key

// Attachment-related NATS message type constants.
const (
	MsgTypeAgentUserAttachment = "agent_user_attachment"
)

// Attachment-related agent event type constants.
const (
	EventTypeUserAttachment  = "user.attachment"
	EventTypeAgentAttachment = "agent.attachment"
)

// AttachmentTransport identifies how the bytes are conveyed.
type AttachmentTransport string

const (
	AttachmentTransportInline      AttachmentTransport = "inline"
	AttachmentTransportObjectStore AttachmentTransport = "object_store"
)

// InlineMaxBytes is the maximum plaintext size for the inline transport.
// Larger files MUST use the object_store transport.
const InlineMaxBytes = 64 * 1024 // 64 KiB

// AttachmentCapability is the capabilities[] string clients/hosts declare in
// session.start to opt into the attachments protocol.
const AttachmentCapability = "attachments"

// AttachmentInfo metadata is the JSON shape carried in the event Data field
// for both EventTypeUserAttachment and EventTypeAgentAttachment.
type AttachmentInfo struct {
	// FileID is the server-minted UUID identifier for this attachment.
	FileID string `json:"file_id"`

	// Name is the original file name (display only).
	Name string `json:"name"`

	// MIME is the declared media type.
	MIME string `json:"mime"`

	// SizeBytes is the plaintext byte length.
	SizeBytes int64 `json:"size_bytes"`

	// PlaintextSHA256 is the hex-encoded SHA-256 of the plaintext file,
	// computed end-to-end by the producer and verified by the consumer.
	PlaintextSHA256 string `json:"plaintext_sha256"`

	// Transport selects between inline and object_store delivery.
	Transport AttachmentTransport `json:"transport"`

	// InlineDataB64 is the base64-encoded plaintext bytes; set only when
	// Transport == AttachmentTransportInline.
	InlineDataB64 string `json:"inline_data_b64,omitempty"`

	// ObjectBucket is the JetStream Object Store bucket name; set only
	// when Transport == AttachmentTransportObjectStore.
	ObjectBucket string `json:"object_bucket,omitempty"`

	// ObjectKey is the JetStream Object Store key (typically equal to
	// FileID); set only when Transport == AttachmentTransportObjectStore.
	ObjectKey string `json:"object_key,omitempty"`

	// ChunkSize is the AES-GCM chunk size used for streaming encryption
	// of the Object Store ciphertext.
	ChunkSize int `json:"chunk_size,omitempty"`

	// BaseNonceB64 is the base64-encoded 8-byte base nonce. Combined with
	// a 4-byte BE chunk counter this yields the 12-byte GCM nonce. Required
	// for object_store transport.
	BaseNonceB64 string `json:"base_nonce,omitempty"`

	// WrappedKey is the envelope-encrypted per-file AES key; set only
	// when Transport == AttachmentTransportObjectStore.
	WrappedKey *WrappedKey `json:"wrapped_key,omitempty"`

	// LocalPath is the on-disk path where the receiving HOST has materialized
	// the plaintext bytes for delivery to the runner. Internal state — not
	// serialized to the wire. Set by materializeInlineAttachment (PR-2) or
	// the Object Store downloader (PR-5).
	LocalPath string `json:"-"`
}

// WrappedKey envelope-encrypts the per-file AES key with a KEK derived from
// the session AES key via HKDF-Expand(info = "syfthub-attachment-v1" || file_id).
type WrappedKey struct {
	// Algorithm is always "AES-256-GCM".
	Algorithm string `json:"algorithm"`

	// Ciphertext is the base64-encoded AES-GCM ciphertext of the per-file key
	// (32 bytes plaintext + 16-byte tag).
	Ciphertext string `json:"ciphertext"`

	// Nonce is the base64-encoded 12-byte AES-GCM nonce.
	Nonce string `json:"nonce"`

	// Info is the HKDF-Expand info string used to derive the KEK; must equal
	// "syfthub-attachment-v1".
	Info string `json:"info"`
}

// AttachmentInfoFromRaw decodes the Data field of an AgentEventPayload (or the
// equivalent inbound user-attachment payload) into a typed AttachmentInfo.
func AttachmentInfoFromRaw(data json.RawMessage) (*AttachmentInfo, error) {
	var info AttachmentInfo
	if err := json.Unmarshal(data, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

// AgentUserAttachmentPayload is the decrypted payload of an agent_user_attachment
// NATS message (CLIENT → HOST direction). Mirrors AgentUserMessagePayload.
type AgentUserAttachmentPayload struct {
	SessionID  string         `json:"session_id"`
	Attachment AttachmentInfo `json:"attachment"`
}

// Attachment-related tunnel error codes.
const (
	TunnelErrorCodeAttachmentQuotaExceeded   TunnelErrorCode = "ATTACHMENT_QUOTA_EXCEEDED"
	TunnelErrorCodeAttachmentNotAccepted     TunnelErrorCode = "ATTACHMENT_NOT_ACCEPTED"
	TunnelErrorCodeAttachmentIntegrity       TunnelErrorCode = "ATTACHMENT_INTEGRITY"
	TunnelErrorCodeAttachmentDecryptFailed   TunnelErrorCode = "ATTACHMENT_DECRYPT_FAILED"
	TunnelErrorCodeAttachmentNotFound        TunnelErrorCode = "ATTACHMENT_NOT_FOUND"
	TunnelErrorCodeAttachmentInvalidMetadata TunnelErrorCode = "ATTACHMENT_INVALID_METADATA"
)

// HKDF info string used to derive a per-file KEK from the session AES key.
// MUST match the Python aggregator constant exactly.
const AttachmentHKDFInfoV1 = "syfthub-attachment-v1"

// AttachmentUploader is the optional injection point that lets a session
// route outbound files via JetStream Object Store (PR-5+) instead of riding
// them inline in the event payload. The transport package supplies a real
// implementation; the syfthubapi package only knows the interface.
//
// Upload reads plaintext from r, encrypts it under a fresh per-file key
// (envelope-wrapped by the session AES key), uploads ciphertext to Object
// Store, and returns a fully populated AttachmentInfo with
// Transport=object_store + WrappedKey + ObjectBucket/Key set.
type AttachmentUploader interface {
	Upload(fileID, name, mime string, sizeBytes int64, r io.Reader) (AttachmentInfo, error)
}

// AttachmentDownloader is the inbound counterpart to AttachmentUploader.
// Given a populated AttachmentInfo with Transport=object_store, it fetches
// ciphertext from Object Store, unwraps the per-file key under the session
// KEK, decrypts the chunked stream, verifies SHA-256, and writes plaintext
// to a 0600 file under dir. On success it sets info.LocalPath.
type AttachmentDownloader interface {
	DownloadAndMaterialize(dir string, info *AttachmentInfo) error
}
