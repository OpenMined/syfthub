package manualreview

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"io"

	"golang.org/x/crypto/hkdf"
)

// nonceSize is the AES-256-GCM nonce length in bytes (96 bits, NIST default).
const nonceSize = 12

// ResolutionCipher is a symmetric AES-256-GCM AEAD keyed by the HKDF of an
// identity-pair ECDH secret salted with review_id.
//
// Unlike transport.SessionCipher, there are no separate request/response keys
// — manual-review resolutions are a single message from host to caller. Both
// peers derive the same key from the same inputs (X25519 ECDH is commutative),
// so the host calls Seal and the caller calls Open.
type ResolutionCipher struct {
	aead cipher.AEAD
}

// NewResolutionCipher derives the cipher for one resolution from this peer's
// X25519 identity private key, the remote peer's identity public key
// (base64url-encoded raw 32 bytes), and the review_id (used as the HKDF salt).
//
// Same inputs on both sides produce the same key: the host encrypts to the
// caller, the caller decrypts the host's message.
func NewResolutionCipher(identityKey *ecdh.PrivateKey, peerIdentityPubB64, reviewID string) (*ResolutionCipher, error) {
	if identityKey == nil {
		return nil, fmt.Errorf("identity key is nil")
	}
	if reviewID == "" {
		return nil, fmt.Errorf("review id is empty")
	}
	peerPubBytes, err := b64urlDecode(peerIdentityPubB64)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	peerPub, err := ecdh.X25519().NewPublicKey(peerPubBytes)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	shared, err := identityKey.ECDH(peerPub)
	if err != nil {
		return nil, fmt.Errorf("ECDH failed: %w", err)
	}
	r := hkdf.New(sha256.New, shared, []byte(reviewID), []byte(HKDFInfo))
	key := make([]byte, 32)
	if _, err := io.ReadFull(r, key); err != nil {
		return nil, fmt.Errorf("HKDF key derivation failed: %w", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("AES cipher creation failed: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("GCM creation failed: %w", err)
	}
	return &ResolutionCipher{aead: gcm}, nil
}

// Seal encrypts plaintext under a fresh random nonce, binding reviewID as the
// AAD. Returns base64url(nonce), base64url(ciphertext+tag). The reviewID AAD
// stops a ciphertext from one review being substituted for another (even
// though the per-review key already makes that impractical, it's defense in
// depth).
func (c *ResolutionCipher) Seal(plaintext []byte, reviewID string) (nonceB64, ciphertextB64 string, err error) {
	nonce := make([]byte, nonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", "", fmt.Errorf("nonce generation failed: %w", err)
	}
	ct := c.aead.Seal(nil, nonce, plaintext, []byte(reviewID))
	return b64urlEncode(nonce), b64urlEncode(ct), nil
}

// Open decrypts a base64url nonce + ciphertext under the same review_id AAD
// that Seal used. A decryption failure means wrong key, replayed across
// reviews, or tampering — caller should treat all three the same.
func (c *ResolutionCipher) Open(nonceB64, ciphertextB64, reviewID string) ([]byte, error) {
	nonce, err := b64urlDecode(nonceB64)
	if err != nil {
		return nil, fmt.Errorf("invalid nonce: %w", err)
	}
	if len(nonce) != nonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes, got %d", nonceSize, len(nonce))
	}
	ciphertext, err := b64urlDecode(ciphertextB64)
	if err != nil {
		return nil, fmt.Errorf("invalid ciphertext: %w", err)
	}
	plaintext, err := c.aead.Open(nil, nonce, ciphertext, []byte(reviewID))
	if err != nil {
		return nil, fmt.Errorf("GCM decryption failed (wrong key or tampered data): %w", err)
	}
	return plaintext, nil
}

// b64urlEncode encodes bytes to base64url without padding. Matches
// transport.b64urlEncode so wire output is interchangeable.
func b64urlEncode(data []byte) string {
	return base64.RawURLEncoding.EncodeToString(data)
}

// b64urlDecode decodes a base64url string (with or without padding).
func b64urlDecode(s string) ([]byte, error) {
	if data, err := base64.RawURLEncoding.DecodeString(s); err == nil {
		return data, nil
	}
	return base64.URLEncoding.DecodeString(s)
}
