package transport

import (
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/rand"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/internal/cryptocore"
)

// HKDF domain-separation labels for the v1 ephemeral tunnel scheme — must
// match the Python aggregator exactly. These are part of the wire contract.
var (
	// domain: syfthub-tunnel-request-v1
	domainTunnelRequestV1 = cryptocore.NewDomain("syfthub-tunnel-request-v1")
	// domain: syfthub-tunnel-response-v1
	domainTunnelResponseV1 = cryptocore.NewDomain("syfthub-tunnel-response-v1")
)

// Backward-compatible byte aliases for the labels above. Existing v1 tests
// reference the byte-slice form (hkdfRequestInfo / hkdfResponseInfo); these
// re-export the same bytes from the Domain values so neither the wire format
// nor the test surface changes.
var (
	hkdfRequestInfo  = domainTunnelRequestV1.Bytes()
	hkdfResponseInfo = domainTunnelResponseV1.Bytes()
)

// nonceSize is the package-local alias of cryptocore.NonceSize, kept so
// in-package callers (attachment_encryptor.go, tests) and the package's
// existing cross-language constant test continue to compile against a const.
const nonceSize = cryptocore.NonceSize

// GenerateX25519Keypair generates a fresh X25519 keypair.
// Returns the private key and the raw (32-byte) public key bytes.
func GenerateX25519Keypair() (*ecdh.PrivateKey, error) {
	return ecdh.X25519().GenerateKey(rand.Reader)
}

// LoadOrGenerateKey loads an X25519 private key from keyPath, or generates a new
// one and saves it if the file does not exist. The key file stores the raw 32-byte
// seed with mode 0600. Uses O_CREATE|O_EXCL for atomic creation to avoid TOCTOU races.
func LoadOrGenerateKey(keyPath string) (*ecdh.PrivateKey, error) {
	data, err := os.ReadFile(keyPath)
	if err == nil {
		// File exists — parse the raw seed.
		key, parseErr := ecdh.X25519().NewPrivateKey(data)
		if parseErr != nil {
			return nil, fmt.Errorf("corrupt key file %s: %w", keyPath, parseErr)
		}
		return key, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return nil, fmt.Errorf("failed to read key file %s: %w", keyPath, err)
	}

	// File doesn't exist — generate and persist atomically.
	key, err := GenerateX25519Keypair()
	if err != nil {
		return nil, err
	}

	if err := os.MkdirAll(filepath.Dir(keyPath), 0700); err != nil {
		return nil, fmt.Errorf("failed to create key directory: %w", err)
	}

	// O_EXCL ensures atomic create-if-not-exists. If another process raced us,
	// we read the key it wrote instead of overwriting it.
	f, err := os.OpenFile(keyPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if errors.Is(err, os.ErrExist) {
		// Another process created the file between our ReadFile and OpenFile.
		// Read the key it wrote.
		data, err := os.ReadFile(keyPath)
		if err != nil {
			return nil, fmt.Errorf("failed to read key file %s after race: %w", keyPath, err)
		}
		return ecdh.X25519().NewPrivateKey(data)
	}
	if err != nil {
		return nil, fmt.Errorf("failed to create key file %s: %w", keyPath, err)
	}
	_, err = f.Write(key.Bytes())
	f.Close()
	if err != nil {
		os.Remove(keyPath) // clean up partial write
		return nil, fmt.Errorf("failed to write key file %s: %w", keyPath, err)
	}
	return key, nil
}

// deriveKey is the v1-tunnel key derivation: X25519 ECDH + HKDF-SHA256 with
// zero salt. Thin wrapper over cryptocore.DeriveKey kept for in-package test
// helpers that simulate the aggregator side; production paths call
// cryptocore.DeriveKey directly.
func deriveKey(privateKey *ecdh.PrivateKey, peerPublicKeyBytes []byte, info []byte) ([]byte, error) {
	// The v1 scheme used nil salt (HKDF then treats it as a zero-filled
	// HashLen-byte buffer per RFC 5869). Cryptocore preserves that contract.
	domain := domainTunnelRequestV1
	if string(info) == string(hkdfResponseInfo) {
		domain = domainTunnelResponseV1
	}
	return cryptocore.DeriveKey(privateKey, peerPublicKeyBytes, nil, domain)
}

// encryptPayload encrypts plaintext with AES-256-GCM using a random nonce.
// Returns (nonce, ciphertext_with_tag). Used by the v1-tunnel response path
// and by in-package test helpers — operates on raw bytes (no base64 framing),
// which is why it can't be replaced by cryptocore.Seal.
func encryptPayload(plaintext, aesKey, aad []byte) (nonce, ciphertext []byte, err error) {
	gcm, err := cryptocore.NewAESGCM(aesKey)
	if err != nil {
		return nil, nil, err
	}

	nonce = make([]byte, cryptocore.NonceSize)
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, nil, fmt.Errorf("nonce generation failed: %w", err)
	}

	ciphertext = gcm.Seal(nil, nonce, plaintext, aad)
	return nonce, ciphertext, nil
}

// decryptPayload decrypts AES-256-GCM ciphertext (which includes the 16-byte GCM tag).
// Returns an error if decryption or authentication fails. Raw-bytes counterpart
// of encryptPayload; kept here because the v1 tunnel scheme passes nonce and
// ciphertext as separate base64 fields rather than as a single bundle.
func decryptPayload(ciphertextWithTag, aesKey, nonce, aad []byte) ([]byte, error) {
	gcm, err := cryptocore.NewAESGCM(aesKey)
	if err != nil {
		return nil, err
	}

	plaintext, err := gcm.Open(nil, nonce, ciphertextWithTag, aad)
	if err != nil {
		return nil, fmt.Errorf("GCM decryption failed (wrong key, nonce, or tampered data): %w", err)
	}
	return plaintext, nil
}

// b64urlEncode encodes bytes to base64url without padding. Thin wrapper over
// cryptocore.EncodeB64URL kept for in-package callers and tests.
func b64urlEncode(data []byte) string {
	return cryptocore.EncodeB64URL(data)
}

// b64urlDecode decodes a base64url string with no padding.
func b64urlDecode(s string) ([]byte, error) {
	return cryptocore.DecodeB64URL(s)
}

// DecryptTunnelRequest decrypts the encrypted payload in an incoming TunnelRequest.
//
// The aggregator encrypted the payload using:
//   - An ephemeral public key (in req.EncryptionInfo.EphemeralPublicKey)
//   - ECDH with the space's long-term public key
//   - HKDF-SHA256 with domainTunnelRequestV1
//
// We reverse this using our long-term private key.
//
// Args:
//
//	encryptedPayloadB64: Base64url-encoded ciphertext+tag from TunnelRequest.EncryptedPayload.
//	encInfo: The EncryptionInfo from the request (ephemeral_public_key + nonce).
//	privateKey: Our long-term X25519 private key.
//	correlationID: The request's correlation_id — used as GCM AAD.
//
// Returns the decrypted payload bytes (raw JSON), or an error.
func DecryptTunnelRequest(
	encryptedPayloadB64 string,
	encInfo *syfthubapi.EncryptionInfo,
	privateKey *ecdh.PrivateKey,
	correlationID string,
) ([]byte, error) {
	if encInfo == nil {
		return nil, fmt.Errorf("encryption_info is nil")
	}

	ephemeralPubBytes, err := cryptocore.DecodeB64URL(encInfo.EphemeralPublicKey)
	if err != nil {
		return nil, fmt.Errorf("invalid ephemeral_public_key: %w", err)
	}

	nonce, err := cryptocore.DecodeB64URL(encInfo.Nonce)
	if err != nil {
		return nil, fmt.Errorf("invalid nonce: %w", err)
	}
	if len(nonce) != cryptocore.NonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes, got %d", cryptocore.NonceSize, len(nonce))
	}

	ciphertext, err := cryptocore.DecodeB64URL(encryptedPayloadB64)
	if err != nil {
		return nil, fmt.Errorf("invalid encrypted_payload: %w", err)
	}

	aesKey, err := cryptocore.DeriveKey(privateKey, ephemeralPubBytes, nil, domainTunnelRequestV1)
	if err != nil {
		return nil, err
	}

	aad := []byte(correlationID)
	return decryptPayload(ciphertext, aesKey, nonce, aad)
}

// EncryptTunnelResponse encrypts a tunnel response payload.
//
// The response is encrypted using a fresh ephemeral keypair so the aggregator
// can decrypt it using the request's ephemeral private key (which it retains):
//   - Generate fresh response ephemeral keypair (priv_r, pub_r)
//   - shared_secret = X25519(priv_r, request_ephemeral_pub)
//   - aes_key = HKDF-SHA256(shared_secret, domainTunnelResponseV1)
//   - Encrypt payload with AES-256-GCM; AAD = correlationID
//
// Args:
//
//	payloadJSON: JSON bytes of the response payload.
//	requestEphemeralPubKeyB64: Base64url-encoded ephemeral public key from the request.
//	correlationID: The request's correlation_id — used as GCM AAD.
//
// Returns:
//
//	encInfo: EncryptionInfo to embed in the TunnelResponse.
//	encryptedPayloadB64: Base64url-encoded ciphertext+tag.
func EncryptTunnelResponse(
	payloadJSON []byte,
	requestEphemeralPubKeyB64 string,
	correlationID string,
) (*syfthubapi.EncryptionInfo, string, error) {
	// Generate a fresh ephemeral keypair for this response
	respPriv, err := GenerateX25519Keypair()
	if err != nil {
		return nil, "", fmt.Errorf("keypair generation failed: %w", err)
	}
	respPubBytes := respPriv.PublicKey().Bytes()

	reqEphemeralPubBytes, err := cryptocore.DecodeB64URL(requestEphemeralPubKeyB64)
	if err != nil {
		return nil, "", fmt.Errorf("invalid request ephemeral_public_key: %w", err)
	}

	aesKey, err := cryptocore.DeriveKey(respPriv, reqEphemeralPubBytes, nil, domainTunnelResponseV1)
	if err != nil {
		return nil, "", err
	}

	aad := []byte(correlationID)
	nonce, ciphertext, err := encryptPayload(payloadJSON, aesKey, aad)
	if err != nil {
		return nil, "", err
	}

	encInfo := &syfthubapi.EncryptionInfo{
		Algorithm:          "X25519-ECDH-AES-256-GCM",
		EphemeralPublicKey: cryptocore.EncodeB64URL(respPubBytes),
		Nonce:              cryptocore.EncodeB64URL(nonce),
	}
	return encInfo, cryptocore.EncodeB64URL(ciphertext), nil
}

// SessionEncryptor pre-computes the expensive X25519 ECDH + HKDF key derivation
// once per session, then reuses the derived AES-256-GCM key and GCM cipher for all
// subsequent encryptions. Each call to Encrypt uses a fresh random nonce.
//
// This is designed for agent event relay loops where hundreds of events share the
// same session-level ephemeral keypair, avoiding ~0.5-1ms of keypair generation
// and ECDH per event.
//
// Security properties:
//   - Session-level forward secrecy: each SessionEncryptor has a unique ephemeral keypair.
//   - Nonce uniqueness: each Encrypt call generates a cryptographically random 96-bit nonce.
//     With random nonces, the birthday-bound collision probability is negligible for
//     well under 2^32 messages per session (GCM safety margin).
//   - The same ephemeral public key is included in every event's EncryptionInfo, which
//     is backward-compatible: the decryptor derives the same AES key each time.
type SessionEncryptor struct {
	gcm          cipher.AEAD
	ephPubKeyB64 string
}

// EphemeralPublicKeyB64 returns the base64url-encoded ephemeral public key
// the session is using for the response direction. Exposed so callers (e.g.,
// the attachments-relay code) can echo it in correlated artifacts.
func (e *SessionEncryptor) EphemeralPublicKeyB64() string {
	return e.ephPubKeyB64
}

// NewSessionEncryptor generates a single ephemeral X25519 keypair, performs ECDH
// with the peer's public key, and derives the AES-256-GCM key via HKDF. All
// subsequent Encrypt calls reuse this derived key.
//
// Args:
//
//	requestEphemeralPubKeyB64: Base64url-encoded ephemeral public key from the request
//	    (the aggregator's key that it retains for decryption).
func NewSessionEncryptor(requestEphemeralPubKeyB64 string) (*SessionEncryptor, error) {
	respPriv, err := GenerateX25519Keypair()
	if err != nil {
		return nil, fmt.Errorf("keypair generation failed: %w", err)
	}

	reqEphemeralPubBytes, err := cryptocore.DecodeB64URL(requestEphemeralPubKeyB64)
	if err != nil {
		return nil, fmt.Errorf("invalid request ephemeral_public_key: %w", err)
	}

	aesKey, err := cryptocore.DeriveKey(respPriv, reqEphemeralPubBytes, nil, domainTunnelResponseV1)
	if err != nil {
		return nil, err
	}

	gcm, err := cryptocore.NewAESGCM(aesKey)
	if err != nil {
		return nil, err
	}

	return &SessionEncryptor{
		gcm:          gcm,
		ephPubKeyB64: cryptocore.EncodeB64URL(respPriv.PublicKey().Bytes()),
	}, nil
}

// Encrypt encrypts a payload using the pre-derived AES-256-GCM key with a fresh
// random nonce. The correlationID is used as GCM AAD (must match what the
// decryptor will use).
//
// Returns the EncryptionInfo (with the session's constant ephemeral public key and
// a per-message nonce) and the base64url-encoded ciphertext.
func (e *SessionEncryptor) Encrypt(payloadJSON []byte, correlationID string) (*syfthubapi.EncryptionInfo, string, error) {
	nonce := make([]byte, cryptocore.NonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, "", fmt.Errorf("nonce generation failed: %w", err)
	}

	aad := []byte(correlationID)
	ciphertext := e.gcm.Seal(nil, nonce, payloadJSON, aad)

	encInfo := &syfthubapi.EncryptionInfo{
		Algorithm:          "X25519-ECDH-AES-256-GCM",
		EphemeralPublicKey: e.ephPubKeyB64,
		Nonce:              cryptocore.EncodeB64URL(nonce),
	}
	return encInfo, cryptocore.EncodeB64URL(ciphertext), nil
}
