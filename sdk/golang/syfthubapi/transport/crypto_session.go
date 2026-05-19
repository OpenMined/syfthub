// crypto_session.go implements the identity-keyed crypto for direct
// peer-to-peer agent sessions (tunnel protocol v2).
//
// Unlike the v1 ephemeral scheme in crypto.go (DecryptTunnelRequest /
// EncryptTunnelResponse / SessionEncryptor) — which the anonymous aggregator
// uses for the model/data_source path — a v2 agent session runs directly
// between two peers that each hold a long-term X25519 identity key:
//
//	shared   = X25519(my_identity_priv, peer_identity_pub)
//	req_key  = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-request-v2")
//	resp_key = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-response-v2")
//	per message: AES-256-GCM, fresh random 12-byte nonce, AAD = correlation_id
//
// The identity-pair shared secret is stable across sessions, so the session_id
// is used as the HKDF salt to make every session's keys unique.
//
// The scheme is symmetric: one SessionCipher type serves both peers. The
// client uses EncryptRequest/DecryptResponse; the host uses
// DecryptRequest/EncryptResponse. X25519 ECDH is commutative, so both sides
// derive identical request and response keys.
//
// SECURITY NOTE: this is static-static ECDH and has no forward secrecy —
// compromise of an identity key exposes recorded past sessions between that
// peer pair. This is a deliberate, documented tradeoff (decision D1); the
// "-v2" domain labels reserve room for a "-v3" that adds an ephemeral leg.
// See syfthub-desktop/docs/p2p-agent-direct-nats-design.md.

package transport

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/rand"
	"crypto/sha256"
	"fmt"
	"io"

	"golang.org/x/crypto/hkdf"
)

// HKDF domain-separation labels for the v2 identity-keyed agent session crypto.
var (
	hkdfAgentRequestInfoV2  = []byte("syfthub-agent-request-v2")
	hkdfAgentResponseInfoV2 = []byte("syfthub-agent-response-v2")
)

// SessionCipher holds the AES-256-GCM ciphers for both directions of one
// agent session. See the file header for the derivation scheme.
type SessionCipher struct {
	reqAEAD  cipher.AEAD
	respAEAD cipher.AEAD
}

// NewSessionCipher derives the request and response ciphers for one agent
// session from this peer's X25519 identity private key, the remote peer's
// identity public key (base64url-encoded raw 32 bytes), and the session id
// (used as the HKDF salt).
func NewSessionCipher(identityKey *ecdh.PrivateKey, peerIdentityPubB64, sessionID string) (*SessionCipher, error) {
	if identityKey == nil {
		return nil, fmt.Errorf("identity key is nil")
	}
	if sessionID == "" {
		return nil, fmt.Errorf("session id is empty")
	}
	peerPubBytes, err := b64urlDecode(peerIdentityPubB64)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	salt := []byte(sessionID)

	reqKey, err := deriveSessionKey(identityKey, peerPubBytes, salt, hkdfAgentRequestInfoV2)
	if err != nil {
		return nil, err
	}
	respKey, err := deriveSessionKey(identityKey, peerPubBytes, salt, hkdfAgentResponseInfoV2)
	if err != nil {
		return nil, err
	}

	reqAEAD, err := newAESGCM(reqKey)
	if err != nil {
		return nil, err
	}
	respAEAD, err := newAESGCM(respKey)
	if err != nil {
		return nil, err
	}
	return &SessionCipher{reqAEAD: reqAEAD, respAEAD: respAEAD}, nil
}

// EncryptRequest encrypts a client→host message (session_start, user_message,
// session_cancel, user_attachment). correlationID is bound as GCM AAD.
func (c *SessionCipher) EncryptRequest(plaintext []byte, correlationID string) (nonceB64, ciphertextB64 string, err error) {
	return sealAEAD(c.reqAEAD, plaintext, correlationID)
}

// DecryptRequest decrypts a client→host message.
func (c *SessionCipher) DecryptRequest(nonceB64, ciphertextB64, correlationID string) ([]byte, error) {
	return openAEAD(c.reqAEAD, nonceB64, ciphertextB64, correlationID)
}

// EncryptResponse encrypts a host→client message (agent_event).
func (c *SessionCipher) EncryptResponse(plaintext []byte, correlationID string) (nonceB64, ciphertextB64 string, err error) {
	return sealAEAD(c.respAEAD, plaintext, correlationID)
}

// DecryptResponse decrypts a host→client message.
func (c *SessionCipher) DecryptResponse(nonceB64, ciphertextB64, correlationID string) ([]byte, error) {
	return openAEAD(c.respAEAD, nonceB64, ciphertextB64, correlationID)
}

// deriveSessionKey performs X25519 ECDH then HKDF-SHA256 with an explicit salt,
// producing a 32-byte AES key. Unlike deriveKey (v1, nil salt) it salts the
// derivation with the session id so a stable identity-pair shared secret still
// yields fresh keys for every session.
func deriveSessionKey(identityKey *ecdh.PrivateKey, peerPubBytes, salt, info []byte) ([]byte, error) {
	peerPub, err := ecdh.X25519().NewPublicKey(peerPubBytes)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	shared, err := identityKey.ECDH(peerPub)
	if err != nil {
		return nil, fmt.Errorf("ECDH failed: %w", err)
	}
	r := hkdf.New(sha256.New, shared, salt, info)
	key := make([]byte, 32)
	if _, err := io.ReadFull(r, key); err != nil {
		return nil, fmt.Errorf("HKDF key derivation failed: %w", err)
	}
	return key, nil
}

// newAESGCM builds an AES-256-GCM AEAD from a 32-byte key.
func newAESGCM(key []byte) (cipher.AEAD, error) {
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

// sealAEAD encrypts plaintext under a fresh random nonce; AAD = correlationID.
// Returns base64url(nonce) and base64url(ciphertext+tag).
func sealAEAD(aead cipher.AEAD, plaintext []byte, correlationID string) (nonceB64, ciphertextB64 string, err error) {
	nonce := make([]byte, nonceSize)
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", "", fmt.Errorf("nonce generation failed: %w", err)
	}
	ciphertext := aead.Seal(nil, nonce, plaintext, []byte(correlationID))
	return b64urlEncode(nonce), b64urlEncode(ciphertext), nil
}

// openAEAD decrypts a base64url nonce + ciphertext; AAD = correlationID.
func openAEAD(aead cipher.AEAD, nonceB64, ciphertextB64, correlationID string) ([]byte, error) {
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
	plaintext, err := aead.Open(nil, nonce, ciphertext, []byte(correlationID))
	if err != nil {
		return nil, fmt.Errorf("GCM decryption failed (wrong key, nonce, or tampered data): %w", err)
	}
	return plaintext, nil
}
