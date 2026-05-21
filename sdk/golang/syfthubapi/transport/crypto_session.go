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
	"crypto/cipher"
	"crypto/ecdh"
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/internal/cryptocore"
)

// HKDF domain-separation labels for the v2 identity-keyed agent session crypto.
// The string labels are part of the wire contract and must match the peer's
// implementation byte-for-byte.
var (
	// domain: syfthub-agent-request-v2
	domainAgentRequestV2 = cryptocore.NewDomain("syfthub-agent-request-v2")
	// domain: syfthub-agent-response-v2
	domainAgentResponseV2 = cryptocore.NewDomain("syfthub-agent-response-v2")
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
	peerPubBytes, err := cryptocore.DecodeB64URL(peerIdentityPubB64)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	salt := []byte(sessionID)

	reqKey, err := cryptocore.DeriveKey(identityKey, peerPubBytes, salt, domainAgentRequestV2)
	if err != nil {
		return nil, err
	}
	respKey, err := cryptocore.DeriveKey(identityKey, peerPubBytes, salt, domainAgentResponseV2)
	if err != nil {
		return nil, err
	}

	reqAEAD, err := cryptocore.NewAESGCM(reqKey)
	if err != nil {
		return nil, err
	}
	respAEAD, err := cryptocore.NewAESGCM(respKey)
	if err != nil {
		return nil, err
	}
	return &SessionCipher{reqAEAD: reqAEAD, respAEAD: respAEAD}, nil
}

// EncryptRequest encrypts a client→host message (session_start, user_message,
// session_cancel, user_attachment). correlationID is bound as GCM AAD.
func (c *SessionCipher) EncryptRequest(plaintext []byte, correlationID string) (nonceB64, ciphertextB64 string, err error) {
	return cryptocore.Seal(c.reqAEAD, plaintext, []byte(correlationID))
}

// DecryptRequest decrypts a client→host message.
func (c *SessionCipher) DecryptRequest(nonceB64, ciphertextB64, correlationID string) ([]byte, error) {
	return cryptocore.Open(c.reqAEAD, nonceB64, ciphertextB64, []byte(correlationID))
}

// EncryptResponse encrypts a host→client message (agent_event).
func (c *SessionCipher) EncryptResponse(plaintext []byte, correlationID string) (nonceB64, ciphertextB64 string, err error) {
	return cryptocore.Seal(c.respAEAD, plaintext, []byte(correlationID))
}

// DecryptResponse decrypts a host→client message.
func (c *SessionCipher) DecryptResponse(nonceB64, ciphertextB64, correlationID string) ([]byte, error) {
	return cryptocore.Open(c.respAEAD, nonceB64, ciphertextB64, []byte(correlationID))
}
