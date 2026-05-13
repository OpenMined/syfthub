package transport

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"

	"golang.org/x/crypto/hkdf"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// AttachmentChunkSize is the per-chunk plaintext size for the streaming
// AES-256-GCM scheme. Chunk N's nonce is base_nonce || u32_BE(N) and AAD is
// file_id || u32_BE(N). Wire ciphertext is the concatenation of all chunk
// ciphertext+tag blocks.
//
// MUST equal the Python aggregator constant in PR-6.
const AttachmentChunkSize = 64 * 1024

// AttachmentChunkCounterSize is the on-wire size of the per-chunk counter
// appended to the base nonce + AAD.
const AttachmentChunkCounterSize = 4

// AttachmentBaseNonceSize is the size of the random base nonce stored alongside
// each ciphertext blob (file_nonce_seed in the spec).
const AttachmentBaseNonceSize = 8

// AttachmentTagSize is the GCM authentication tag length.
const AttachmentTagSize = 16

// AttachmentEncryptor performs the per-file envelope encryption documented in
// docs/architecture/attachments.md.
//
// Lifecycle:
//
//  1. Caller obtains the 32-byte session AES key from SessionEncryptor (see
//     SessionEncryptor.AESKey).
//  2. NewAttachmentEncryptor(sessionAESKey) constructs an instance bound to the
//     session.
//  3. For each new attachment, GenerateFileKey() returns a fresh 32-byte K.
//  4. WrapFileKey(fileID, K) → wrapped key + nonce; ride alongside metadata.
//  5. EncryptStream(K, baseNonce, fileID, plaintext, ciphertext) writes the
//     chunked AES-GCM ciphertext to a Writer.
//  6. Reverse direction: UnwrapFileKey + DecryptStream.
type AttachmentEncryptor struct {
	sessionKey []byte // 32 bytes; reused for KEK derivation
}

// NewAttachmentEncryptor binds the encryptor to a session AES key.
// sessionAESKey must be exactly 32 bytes (AES-256).
func NewAttachmentEncryptor(sessionAESKey []byte) (*AttachmentEncryptor, error) {
	if len(sessionAESKey) != 32 {
		return nil, fmt.Errorf("session AES key must be 32 bytes, got %d", len(sessionAESKey))
	}
	// Copy to avoid aliasing surprises from the caller.
	k := make([]byte, 32)
	copy(k, sessionAESKey)
	return &AttachmentEncryptor{sessionKey: k}, nil
}

// DeriveFileKEK derives a per-file Key Encryption Key from the session AES key
// using HKDF-Expand with info = AttachmentHKDFInfoV1 || file_id.
//
// This sub-key is what wraps the per-file content key K (envelope encryption).
// See docs/architecture/attachments.md "Key derivation".
func (e *AttachmentEncryptor) DeriveFileKEK(fileID string) ([]byte, error) {
	if fileID == "" {
		return nil, errors.New("file_id is required")
	}
	info := append([]byte(syfthubapi.AttachmentHKDFInfoV1), []byte(fileID)...)
	r := hkdf.Expand(sha256.New, e.sessionKey, info)
	kek := make([]byte, 32)
	if _, err := io.ReadFull(r, kek); err != nil {
		return nil, fmt.Errorf("HKDF-Expand: %w", err)
	}
	return kek, nil
}

// GenerateFileKey returns a fresh random 32-byte AES-256 file key.
func GenerateFileKey() ([]byte, error) {
	k := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, k); err != nil {
		return nil, fmt.Errorf("rand: %w", err)
	}
	return k, nil
}

// GenerateBaseNonce returns a fresh random 8-byte base nonce. Combined with
// the 4-byte chunk counter this yields the 12-byte GCM nonce.
func GenerateBaseNonce() ([]byte, error) {
	n := make([]byte, AttachmentBaseNonceSize)
	if _, err := io.ReadFull(rand.Reader, n); err != nil {
		return nil, fmt.Errorf("rand: %w", err)
	}
	return n, nil
}

// WrapFileKey envelope-encrypts fileKey under the per-file KEK using AES-256-GCM.
// AAD = file_id; nonce is a fresh random 12 bytes. Returns (ciphertext+tag, nonce).
func (e *AttachmentEncryptor) WrapFileKey(fileID string, fileKey []byte) (ciphertext, nonce []byte, err error) {
	if len(fileKey) != 32 {
		return nil, nil, fmt.Errorf("file key must be 32 bytes, got %d", len(fileKey))
	}
	kek, err := e.DeriveFileKEK(fileID)
	if err != nil {
		return nil, nil, err
	}
	gcm, err := newGCM(kek)
	if err != nil {
		return nil, nil, err
	}
	nonce = make([]byte, nonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, nil, fmt.Errorf("nonce: %w", err)
	}
	ct := gcm.Seal(nil, nonce, fileKey, []byte(fileID))
	return ct, nonce, nil
}

// UnwrapFileKey reverses WrapFileKey.
func (e *AttachmentEncryptor) UnwrapFileKey(fileID string, ciphertext, nonce []byte) ([]byte, error) {
	if len(nonce) != nonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes, got %d", nonceSize, len(nonce))
	}
	kek, err := e.DeriveFileKEK(fileID)
	if err != nil {
		return nil, err
	}
	gcm, err := newGCM(kek)
	if err != nil {
		return nil, err
	}
	pt, err := gcm.Open(nil, nonce, ciphertext, []byte(fileID))
	if err != nil {
		return nil, fmt.Errorf("unwrap: %w", err)
	}
	if len(pt) != 32 {
		return nil, fmt.Errorf("unwrapped key must be 32 bytes, got %d", len(pt))
	}
	return pt, nil
}

// EncryptStream encrypts plaintext from src into dst using chunked AES-256-GCM.
// Each chunk encrypts up to AttachmentChunkSize bytes; the final chunk may be
// shorter. Chunk N uses nonce = baseNonce || u32_BE(N) and AAD = fileID || u32_BE(N).
//
// Returns (totalPlaintextBytes, plaintextSHA256Hex, error).
func (e *AttachmentEncryptor) EncryptStream(
	fileKey, baseNonce []byte,
	fileID string,
	src io.Reader,
	dst io.Writer,
) (int64, string, error) {
	if len(fileKey) != 32 {
		return 0, "", fmt.Errorf("file key must be 32 bytes, got %d", len(fileKey))
	}
	if len(baseNonce) != AttachmentBaseNonceSize {
		return 0, "", fmt.Errorf("base nonce must be %d bytes, got %d", AttachmentBaseNonceSize, len(baseNonce))
	}
	gcm, err := newGCM(fileKey)
	if err != nil {
		return 0, "", err
	}

	buf := make([]byte, AttachmentChunkSize)
	hash := sha256.New()
	var counter uint32
	var total int64

	for {
		n, readErr := io.ReadFull(src, buf)
		isFinal := false
		if readErr == io.EOF {
			// No bytes read after last full chunk — emit nothing more.
			break
		}
		if readErr == io.ErrUnexpectedEOF {
			isFinal = true
		} else if readErr != nil {
			return 0, "", fmt.Errorf("read chunk %d: %w", counter, readErr)
		}

		chunk := buf[:n]
		hash.Write(chunk)
		total += int64(n)

		nonce := makeChunkNonce(baseNonce, counter)
		aad := makeChunkAAD(fileID, counter)
		ct := gcm.Seal(nil, nonce, chunk, aad)
		if _, err := dst.Write(ct); err != nil {
			return 0, "", fmt.Errorf("write chunk %d: %w", counter, err)
		}
		counter++
		if isFinal {
			break
		}
	}
	return total, hex.EncodeToString(hash.Sum(nil)), nil
}

// DecryptStream is the inverse of EncryptStream. It reads ciphertext chunks
// from src, decrypts them, verifies the GCM tag, and writes plaintext to dst.
//
// declaredSize is used to detect truncation: if the cumulative plaintext after
// successful decryption does not equal declaredSize the function returns an
// error. Pass -1 to skip the size check.
//
// Returns (totalPlaintextBytes, plaintextSHA256Hex, error).
func (e *AttachmentEncryptor) DecryptStream(
	fileKey, baseNonce []byte,
	fileID string,
	declaredSize int64,
	src io.Reader,
	dst io.Writer,
) (int64, string, error) {
	if len(fileKey) != 32 {
		return 0, "", fmt.Errorf("file key must be 32 bytes, got %d", len(fileKey))
	}
	if len(baseNonce) != AttachmentBaseNonceSize {
		return 0, "", fmt.Errorf("base nonce must be %d bytes, got %d", AttachmentBaseNonceSize, len(baseNonce))
	}
	gcm, err := newGCM(fileKey)
	if err != nil {
		return 0, "", err
	}

	// Ciphertext chunks are AttachmentChunkSize + AttachmentTagSize bytes
	// except the final (possibly partial) chunk.
	ctChunkMax := AttachmentChunkSize + AttachmentTagSize
	buf := make([]byte, ctChunkMax)
	hash := sha256.New()
	var counter uint32
	var total int64

	for {
		n, readErr := io.ReadFull(src, buf)
		isFinal := false
		if readErr == io.EOF {
			break
		}
		if readErr == io.ErrUnexpectedEOF {
			isFinal = true
		} else if readErr != nil {
			return 0, "", fmt.Errorf("read chunk %d: %w", counter, readErr)
		}

		if n < AttachmentTagSize {
			return 0, "", fmt.Errorf("chunk %d truncated: %d bytes", counter, n)
		}
		chunk := buf[:n]
		nonce := makeChunkNonce(baseNonce, counter)
		aad := makeChunkAAD(fileID, counter)
		pt, err := gcm.Open(nil, nonce, chunk, aad)
		if err != nil {
			return 0, "", fmt.Errorf("decrypt chunk %d: %w", counter, err)
		}
		hash.Write(pt)
		total += int64(len(pt))
		if _, err := dst.Write(pt); err != nil {
			return 0, "", fmt.Errorf("write chunk %d: %w", counter, err)
		}
		counter++
		if isFinal {
			break
		}
	}

	if declaredSize >= 0 && total != declaredSize {
		return total, "", fmt.Errorf("plaintext size mismatch: declared %d, actual %d", declaredSize, total)
	}
	return total, hex.EncodeToString(hash.Sum(nil)), nil
}

func makeChunkNonce(baseNonce []byte, counter uint32) []byte {
	out := make([]byte, nonceSize)
	copy(out, baseNonce)
	binary.BigEndian.PutUint32(out[AttachmentBaseNonceSize:], counter)
	return out
}

func makeChunkAAD(fileID string, counter uint32) []byte {
	out := make([]byte, 0, len(fileID)+AttachmentChunkCounterSize)
	out = append(out, []byte(fileID)...)
	cb := make([]byte, AttachmentChunkCounterSize)
	binary.BigEndian.PutUint32(cb, counter)
	out = append(out, cb...)
	return out
}

func newGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("aes: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("gcm: %w", err)
	}
	return gcm, nil
}
