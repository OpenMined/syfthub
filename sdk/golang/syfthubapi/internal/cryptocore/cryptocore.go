package cryptocore

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

// NonceSize is the AES-256-GCM nonce length in bytes (96 bits, NIST default).
const NonceSize = 12

// KeySize is the AES-256-GCM key length in bytes (256 bits).
const KeySize = 32

// Domain wraps an HKDF "info" label byte string. Wrapping it in a named type
// prevents accidental mixing with AAD or other byte parameters at call sites.
// The label is the same byte string the Python aggregator/host expects — these
// labels are part of the wire contract.
type Domain struct{ raw []byte }

// NewDomain constructs a Domain from a string label. The bytes are copied
// defensively so a caller mutating its source string (impossible in Go but
// keeps the semantics explicit) cannot affect previously-built Domains.
func NewDomain(label string) Domain {
	b := make([]byte, len(label))
	copy(b, label)
	return Domain{raw: b}
}

// Bytes returns the raw HKDF info bytes. Callers must NOT mutate the returned
// slice.
func (d Domain) Bytes() []byte { return d.raw }

// DeriveKey performs X25519 ECDH between identityKey and peerPub, then runs
// HKDF-SHA256 over the shared secret with the given salt and Domain to
// produce a 32-byte AES key.
//
// salt may be nil — HKDF then treats it as a zero-filled buffer of HashLen
// bytes (RFC 5869). This is the v1-tunnel behaviour. The v2 agent session
// scheme passes the session id; the manual-review scheme passes the review
// id.
func DeriveKey(identityKey *ecdh.PrivateKey, peerPub, salt []byte, domain Domain) ([]byte, error) {
	pub, err := ecdh.X25519().NewPublicKey(peerPub)
	if err != nil {
		return nil, fmt.Errorf("invalid peer public key: %w", err)
	}
	shared, err := identityKey.ECDH(pub)
	if err != nil {
		return nil, fmt.Errorf("ECDH failed: %w", err)
	}
	r := hkdf.New(sha256.New, shared, salt, domain.Bytes())
	key := make([]byte, KeySize)
	if _, err := io.ReadFull(r, key); err != nil {
		return nil, fmt.Errorf("HKDF key derivation failed: %w", err)
	}
	return key, nil
}

// NewAESGCM builds an AES-256-GCM AEAD from a 32-byte key.
func NewAESGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("AES cipher creation failed: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("GCM creation failed: %w", err)
	}
	return gcm, nil
}

// Seal encrypts plaintext under a fresh cryptographically-random 12-byte
// nonce, binding aad as Additional Authenticated Data. Returns
// base64url-no-padding encoded nonce and ciphertext+tag.
func Seal(aead cipher.AEAD, plaintext, aad []byte) (nonceB64, ciphertextB64 string, err error) {
	return SealWithReader(aead, plaintext, aad, rand.Reader)
}

// SealWithReader is Seal with a caller-supplied nonce source. Production code
// must use Seal (which sources from crypto/rand); SealWithReader exists to
// support deterministic Known-Answer-Test vectors.
func SealWithReader(aead cipher.AEAD, plaintext, aad []byte, r io.Reader) (nonceB64, ciphertextB64 string, err error) {
	nonce := make([]byte, NonceSize)
	if _, err := io.ReadFull(r, nonce); err != nil {
		return "", "", fmt.Errorf("nonce generation failed: %w", err)
	}
	ct := aead.Seal(nil, nonce, plaintext, aad)
	return EncodeB64URL(nonce), EncodeB64URL(ct), nil
}

// Open decrypts a base64url-encoded nonce + ciphertext under the given aad.
// Decoding errors, length errors, and authentication failures are all
// reported as errors. The error message text for an auth failure is fixed
// at "GCM decryption failed (wrong key, nonce, or tampered data)" so log
// grep patterns stay stable.
func Open(aead cipher.AEAD, nonceB64, ciphertextB64 string, aad []byte) ([]byte, error) {
	nonce, err := DecodeB64URL(nonceB64)
	if err != nil {
		return nil, fmt.Errorf("invalid nonce: %w", err)
	}
	if len(nonce) != NonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes, got %d", NonceSize, len(nonce))
	}
	ct, err := DecodeB64URL(ciphertextB64)
	if err != nil {
		return nil, fmt.Errorf("invalid ciphertext: %w", err)
	}
	plaintext, err := aead.Open(nil, nonce, ct, aad)
	if err != nil {
		return nil, fmt.Errorf("GCM decryption failed (wrong key, nonce, or tampered data): %w", err)
	}
	return plaintext, nil
}

// EncodeB64URL encodes bytes as base64url with no padding.
func EncodeB64URL(data []byte) string {
	return base64.RawURLEncoding.EncodeToString(data)
}

// DecodeB64URL decodes a base64url string with no padding.
func DecodeB64URL(s string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(s)
}

// DecodeB64URLLenient tries RawURLEncoding first (no padding) and falls back
// to URLEncoding (padded). Used for inputs that may have come from external
// peers whose encoders apply padding.
func DecodeB64URLLenient(s string) ([]byte, error) {
	if data, err := base64.RawURLEncoding.DecodeString(s); err == nil {
		return data, nil
	}
	return base64.URLEncoding.DecodeString(s)
}
