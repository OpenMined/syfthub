package manualreview

import (
	"crypto/cipher"
	"crypto/ecdh"
	"fmt"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/internal/cryptocore"
)

// HKDF domain-separation label for the manual-review resolution scheme. The
// string value comes from the exported HKDFInfo constant (wire contract); the
// Domain wrapper keeps call sites consistent with the transport schemes.
//
// domain: syfthub-mr-resolution-v1
var domainResolutionV1 = cryptocore.NewDomain(HKDFInfo)

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
// (base64url-encoded raw 32 bytes; lenient — accepts padded too), and the
// review_id (used as the HKDF salt).
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
	peerPubBytes, err := cryptocore.DecodeB64URLLenient(peerIdentityPubB64)
	if err != nil {
		return nil, fmt.Errorf("invalid peer identity public key: %w", err)
	}
	key, err := cryptocore.DeriveKey(identityKey, peerPubBytes, []byte(reviewID), domainResolutionV1)
	if err != nil {
		// DeriveKey error messages are descriptive enough to surface directly.
		return nil, err
	}
	gcm, err := cryptocore.NewAESGCM(key)
	if err != nil {
		return nil, err
	}
	return &ResolutionCipher{aead: gcm}, nil
}

// Seal encrypts plaintext under a fresh random nonce, binding reviewID as the
// AAD. Returns base64url(nonce), base64url(ciphertext+tag). The reviewID AAD
// stops a ciphertext from one review being substituted for another (even
// though the per-review key already makes that impractical, it's defense in
// depth).
func (c *ResolutionCipher) Seal(plaintext []byte, reviewID string) (nonceB64, ciphertextB64 string, err error) {
	return cryptocore.Seal(c.aead, plaintext, []byte(reviewID))
}

// Open decrypts a base64url nonce + ciphertext under the same review_id AAD
// that Seal used. A decryption failure means wrong key, replayed across
// reviews, or tampering — caller should treat all three the same.
func (c *ResolutionCipher) Open(nonceB64, ciphertextB64, reviewID string) ([]byte, error) {
	return cryptocore.Open(c.aead, nonceB64, ciphertextB64, []byte(reviewID))
}
