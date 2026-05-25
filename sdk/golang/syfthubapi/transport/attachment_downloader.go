package transport

import (
	"bytes"
	"context"
	"encoding/base64"
	"fmt"
	"io"
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

// DownloadOption customizes a streaming download.
type DownloadOption func(*downloadOptions)

type downloadOptions struct {
	progress func(downloaded int64, total int64)
}

// WithProgress installs a callback fired as plaintext is written to the
// destination. downloaded is the running plaintext byte count; total is
// info.SizeBytes (declared, may be 0 if the producer didn't set it).
// Fires at most once per AttachmentChunkSize boundary so it's safe to use
// for UI updates without throttling at the call site.
func WithProgress(cb func(downloaded int64, total int64)) DownloadOption {
	return func(o *downloadOptions) { o.progress = cb }
}

// progressWriter is a small wrapper that ticks a progress callback as bytes
// flow through it.
type progressWriter struct {
	w        io.Writer
	total    int64
	written  int64
	progress func(int64, int64)
}

func (pw *progressWriter) Write(p []byte) (int, error) {
	n, err := pw.w.Write(p)
	if n > 0 {
		pw.written += int64(n)
		if pw.progress != nil {
			pw.progress(pw.written, pw.total)
		}
	}
	return n, err
}

// DownloadStream fetches the object-store ciphertext for info, decrypts it,
// verifies the declared size and SHA-256, and writes the plaintext to w.
//
// On verification failure w MAY have received partial data; the caller is
// responsible for cleaning up (truncating / removing the file or buffer).
// Callers that need atomic on-disk semantics should use DownloadAndMaterialize
// instead, which buffers in memory and only writes the file after the SHA
// check passes.
//
// Pass WithProgress to receive per-chunk byte-count callbacks for UI updates.
func (d *ObjectStoreDownloader) DownloadStream(info *syfthubapi.AttachmentInfo, w io.Writer, opts ...DownloadOption) error {
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

	var dlOpts downloadOptions
	for _, o := range opts {
		o(&dlOpts)
	}
	dst := w
	if dlOpts.progress != nil {
		dst = &progressWriter{w: w, total: info.SizeBytes, progress: dlOpts.progress}
	}

	gotSize, gotSHA, err := d.encryptor.DecryptStream(fileKey, baseNonce, info.FileID, info.SizeBytes, &ct, dst)
	if err != nil {
		return fmt.Errorf("decrypt stream: %w", err)
	}
	if gotSize != info.SizeBytes {
		return fmt.Errorf("size mismatch: declared %d, decrypted %d", info.SizeBytes, gotSize)
	}
	if gotSHA != info.PlaintextSHA256 {
		return fmt.Errorf("sha256 mismatch")
	}
	return nil
}

// DownloadAndMaterialize is the atomic on-disk variant of DownloadStream: it
// buffers the plaintext in memory, verifies its SHA, and only then writes a
// 0600-mode file under dir. Sets info.LocalPath on success. Use this when a
// failed download must leave no partial file behind (the host runner path).
// For a streaming variant that writes incrementally to an arbitrary io.Writer,
// use DownloadStream.
func (d *ObjectStoreDownloader) DownloadAndMaterialize(
	dir string,
	info *syfthubapi.AttachmentInfo,
) error {
	var pt bytes.Buffer
	if err := d.DownloadStream(info, &pt); err != nil {
		return err
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
