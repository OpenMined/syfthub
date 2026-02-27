package transport

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"

	"golang.org/x/crypto/hkdf"

	"crypto/sha256"

	syfthubapi "github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

// Domain-separation labels for HKDF — must match the Python aggregator exactly.
var (
	hkdfRequestInfo  = []byte("syfthub-tunnel-request-v1")
	hkdfResponseInfo = []byte("syfthub-tunnel-response-v1")
)

const nonceSize = 12 // 96-bit nonce for AES-256-GCM

// GenerateX25519Keypair generates a fresh X25519 keypair.
// Returns the private key and the raw (32-byte) public key bytes.
func GenerateX25519Keypair() (*ecdh.PrivateKey, error) {
	return ecdh.X25519().GenerateKey(rand.Reader)
}

// deriveKey performs X25519 ECDH then HKDF-SHA256 to produce a 32-byte AES key.
// info must be one of hkdfRequestInfo or hkdfResponseInfo for domain separation.
func deriveKey(privateKey *ecdh.PrivateKey, peerPublicKeyBytes []byte, info []byte) ([]byte, error) {
	peerPub, err := ecdh.X25519().NewPublicKey(peerPublicKeyBytes)
	if err != nil {
		return nil, fmt.Errorf("invalid peer public key: %w", err)
	}

	sharedSecret, err := privateKey.ECDH(peerPub)
	if err != nil {
		return nil, fmt.Errorf("ECDH failed: %w", err)
	}

	// HKDF-SHA256: no salt (nil → HKDF uses a zero-filled salt of HashLen bytes per RFC 5869)
	hkdfReader := hkdf.New(sha256.New, sharedSecret, nil, info)
	aesKey := make([]byte, 32)
	if _, err := io.ReadFull(hkdfReader, aesKey); err != nil {
		return nil, fmt.Errorf("HKDF key derivation failed: %w", err)
	}
	return aesKey, nil
}

// encryptPayload encrypts plaintext with AES-256-GCM using a random nonce.
// Returns (nonce, ciphertext_with_tag).
func encryptPayload(plaintext, aesKey, aad []byte) (nonce, ciphertext []byte, err error) {
	block, err := aes.NewCipher(aesKey)
	if err != nil {
		return nil, nil, fmt.Errorf("AES cipher creation failed: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, nil, fmt.Errorf("GCM creation failed: %w", err)
	}

	nonce = make([]byte, nonceSize)
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, nil, fmt.Errorf("nonce generation failed: %w", err)
	}

	ciphertext = gcm.Seal(nil, nonce, plaintext, aad)
	return nonce, ciphertext, nil
}

// decryptPayload decrypts AES-256-GCM ciphertext (which includes the 16-byte GCM tag).
// Returns an error if decryption or authentication fails.
func decryptPayload(ciphertextWithTag, aesKey, nonce, aad []byte) ([]byte, error) {
	block, err := aes.NewCipher(aesKey)
	if err != nil {
		return nil, fmt.Errorf("AES cipher creation failed: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("GCM creation failed: %w", err)
	}

	plaintext, err := gcm.Open(nil, nonce, ciphertextWithTag, aad)
	if err != nil {
		return nil, fmt.Errorf("GCM decryption failed (wrong key, nonce, or tampered data): %w", err)
	}
	return plaintext, nil
}

// b64urlEncode encodes bytes to base64url without padding.
func b64urlEncode(data []byte) string {
	return base64.RawURLEncoding.EncodeToString(data)
}

// b64urlDecode decodes a base64url string (with or without padding).
func b64urlDecode(s string) ([]byte, error) {
	return base64.RawURLEncoding.DecodeString(s)
}

// DecryptTunnelRequest decrypts the encrypted payload in an incoming TunnelRequest.
//
// The aggregator encrypted the payload using:
//   - An ephemeral public key (in req.EncryptionInfo.EphemeralPublicKey)
//   - ECDH with the space's long-term public key
//   - HKDF-SHA256 with hkdfRequestInfo
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

	ephemeralPubBytes, err := b64urlDecode(encInfo.EphemeralPublicKey)
	if err != nil {
		return nil, fmt.Errorf("invalid ephemeral_public_key: %w", err)
	}

	nonce, err := b64urlDecode(encInfo.Nonce)
	if err != nil {
		return nil, fmt.Errorf("invalid nonce: %w", err)
	}
	if len(nonce) != nonceSize {
		return nil, fmt.Errorf("nonce must be %d bytes, got %d", nonceSize, len(nonce))
	}

	ciphertext, err := b64urlDecode(encryptedPayloadB64)
	if err != nil {
		return nil, fmt.Errorf("invalid encrypted_payload: %w", err)
	}

	aesKey, err := deriveKey(privateKey, ephemeralPubBytes, hkdfRequestInfo)
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
//   - aes_key = HKDF-SHA256(shared_secret, hkdfResponseInfo)
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

	reqEphemeralPubBytes, err := b64urlDecode(requestEphemeralPubKeyB64)
	if err != nil {
		return nil, "", fmt.Errorf("invalid request ephemeral_public_key: %w", err)
	}

	aesKey, err := deriveKey(respPriv, reqEphemeralPubBytes, hkdfResponseInfo)
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
		EphemeralPublicKey: b64urlEncode(respPubBytes),
		Nonce:              b64urlEncode(nonce),
	}
	return encInfo, b64urlEncode(ciphertext), nil
}
