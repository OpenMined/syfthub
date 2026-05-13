package transport

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// ObjectStoreUploader implements syfthubapi.AttachmentUploader by streaming
// plaintext through the AttachmentEncryptor into a JetStream Object Store
// bucket scoped to the session.
//
// One ObjectStoreUploader instance per session. The encryptor is constructed
// once from the session's SessionEncryptor.AESKey().
type ObjectStoreUploader struct {
	encryptor *AttachmentEncryptor
	store     AttachmentObjectStore
	bucket    string
	ctx       context.Context
}

// NewObjectStoreUploader returns an uploader bound to a specific session
// bucket. EnsureBucket is called immediately so the bucket is reserved
// before the handler runs.
func NewObjectStoreUploader(
	ctx context.Context,
	sessionAESKey []byte,
	store AttachmentObjectStore,
	sessionID string,
) (*ObjectStoreUploader, error) {
	enc, err := NewAttachmentEncryptor(sessionAESKey)
	if err != nil {
		return nil, err
	}
	bucket := BucketNameForSession(sessionID)
	if err := store.EnsureBucket(ctx, bucket, DefaultAttachmentBucketTTL); err != nil {
		return nil, fmt.Errorf("ensure bucket %s: %w", bucket, err)
	}
	return &ObjectStoreUploader{
		encryptor: enc,
		store:     store,
		bucket:    bucket,
		ctx:       ctx,
	}, nil
}

// Upload encrypts r with a fresh per-file key, uploads ciphertext to the
// session's Object Store bucket, wraps the file key under the session AES
// key, and returns a populated AttachmentInfo.
//
// declaredSize is informational only and may be -1; the true size is
// derived from the stream and written into the returned AttachmentInfo.
func (u *ObjectStoreUploader) Upload(
	fileID, name, mime string,
	declaredSize int64,
	r io.Reader,
) (syfthubapi.AttachmentInfo, error) {
	fileKey, err := GenerateFileKey()
	if err != nil {
		return syfthubapi.AttachmentInfo{}, err
	}
	baseNonce, err := GenerateBaseNonce()
	if err != nil {
		return syfthubapi.AttachmentInfo{}, err
	}

	// Tee the plaintext through SHA-256 so we can populate plaintext_sha256.
	hash := sha256.New()
	tee := io.TeeReader(r, hash)

	// We must buffer ciphertext into a bytes.Buffer because the Object Store
	// Put API takes an io.Reader and we want streaming size determination.
	// For Phase-2/PR-5 this is acceptable (max attachment size = 25 MiB by
	// platform default); PR-6+ may pipe directly with a counting writer.
	var ct bytes.Buffer
	plaintextSize, _, err := u.encryptor.EncryptStream(fileKey, baseNonce, fileID, tee, &ct)
	if err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("encrypt stream: %w", err)
	}

	if err := u.store.Put(u.ctx, u.bucket, fileID, &ct); err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("object-store put: %w", err)
	}

	wrappedCT, wrappedNonce, err := u.encryptor.WrapFileKey(fileID, fileKey)
	if err != nil {
		return syfthubapi.AttachmentInfo{}, fmt.Errorf("wrap key: %w", err)
	}

	return syfthubapi.AttachmentInfo{
		FileID:          fileID,
		Name:            name,
		MIME:            mime,
		SizeBytes:       plaintextSize,
		PlaintextSHA256: hex.EncodeToString(hash.Sum(nil)),
		Transport:       syfthubapi.AttachmentTransportObjectStore,
		ObjectBucket:    u.bucket,
		ObjectKey:       fileID,
		ChunkSize:       AttachmentChunkSize,
		BaseNonceB64:    b64urlEncode(baseNonce),
		WrappedKey: &syfthubapi.WrappedKey{
			Algorithm:  "AES-256-GCM",
			Ciphertext: b64urlEncode(wrappedCT),
			Nonce:      b64urlEncode(wrappedNonce),
			Info:       syfthubapi.AttachmentHKDFInfoV1,
		},
	}, nil
}
