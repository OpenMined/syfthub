package transport

import (
	"bytes"
	"context"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ObjectStoreDownloader handles the HOST-side inbound path for object_store-
// tier attachments. It is the mirror of ObjectStoreUploader.
//
// Lifecycle: constructed once per session, parameters mirror the uploader
// (session AES key + Object Store handle).
type ObjectStoreDownloader struct {
	encryptor *AttachmentEncryptor
	store     AttachmentObjectStore
	ctx       context.Context
}

// NewObjectStoreDownloader binds a downloader to a specific session.
// The session AES key is decoded from the session_start payload.
func NewObjectStoreDownloader(
	ctx context.Context,
	sessionAESKey []byte,
	store AttachmentObjectStore,
) (*ObjectStoreDownloader, error) {
	enc, err := NewAttachmentEncryptor(sessionAESKey)
	if err != nil {
		return nil, err
	}
	return &ObjectStoreDownloader{
		encryptor: enc,
		store:     store,
		ctx:       ctx,
	}, nil
}

// DownloadAndMaterialize fetches ciphertext from Object Store, unwraps the
// per-file key under the session KEK, decrypts the chunked stream, verifies
// the plaintext SHA, and writes plaintext to a 0600-mode file inside
// dir. Sets info.LocalPath on success.
func (d *ObjectStoreDownloader) DownloadAndMaterialize(
	dir string,
	info *syfthubapi.AttachmentInfo,
) error {
	if info.Transport != syfthubapi.AttachmentTransportObjectStore {
		return fmt.Errorf("downloader called for transport=%q", info.Transport)
	}
	if info.WrappedKey == nil {
		return fmt.Errorf("wrapped_key missing")
	}
	if info.BaseNonceB64 == "" {
		return fmt.Errorf("base_nonce missing")
	}
	if info.ObjectBucket == "" || info.ObjectKey == "" {
		return fmt.Errorf("object_bucket/key missing")
	}

	wrappedCT, err := base64.StdEncoding.DecodeString(info.WrappedKey.Ciphertext)
	if err != nil {
		return fmt.Errorf("decode wrapped key ciphertext: %w", err)
	}
	wrappedNonce, err := base64.StdEncoding.DecodeString(info.WrappedKey.Nonce)
	if err != nil {
		return fmt.Errorf("decode wrapped key nonce: %w", err)
	}
	fileKey, err := d.encryptor.UnwrapFileKey(info.FileID, wrappedCT, wrappedNonce)
	if err != nil {
		return fmt.Errorf("unwrap file key: %w", err)
	}
	baseNonce, err := base64.StdEncoding.DecodeString(info.BaseNonceB64)
	if err != nil {
		return fmt.Errorf("decode base_nonce: %w", err)
	}

	var ct bytes.Buffer
	if err := d.store.Get(d.ctx, info.ObjectBucket, info.ObjectKey, &ct); err != nil {
		return fmt.Errorf("object-store get: %w", err)
	}

	var pt bytes.Buffer
	gotSize, gotSHA, err := d.encryptor.DecryptStream(fileKey, baseNonce, info.FileID, info.SizeBytes, &ct, &pt)
	if err != nil {
		return fmt.Errorf("decrypt stream: %w", err)
	}
	if gotSize != info.SizeBytes {
		return fmt.Errorf("size mismatch: declared %d, decrypted %d", info.SizeBytes, gotSize)
	}
	if gotSHA != info.PlaintextSHA256 {
		return fmt.Errorf("sha256 mismatch")
	}

	name := info.FileID
	if ext := filepath.Ext(info.Name); ext != "" {
		name += ext
	}
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, pt.Bytes(), 0o600); err != nil {
		return fmt.Errorf("write attachment: %w", err)
	}
	info.LocalPath = path
	return nil
}

// MaterializeAttachment dispatches by transport: inline goes through
// materializeInlineAttachment; object_store requires an AttachmentDownloader
// (typically *ObjectStoreDownloader).
func MaterializeAttachment(
	ctx context.Context,
	dir string,
	info *syfthubapi.AttachmentInfo,
	downloader syfthubapi.AttachmentDownloader,
) error {
	_ = ctx
	switch info.Transport {
	case syfthubapi.AttachmentTransportInline:
		return materializeInlineAttachment(dir, info)
	case syfthubapi.AttachmentTransportObjectStore:
		if downloader == nil {
			return fmt.Errorf("object_store attachment requires a downloader (was the session_attachment_key set?)")
		}
		return downloader.DownloadAndMaterialize(dir, info)
	default:
		return fmt.Errorf("unknown transport %q", info.Transport)
	}
}
