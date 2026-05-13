package mppx

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"errors"
	"fmt"
	"strings"
)

// CanonicalFieldOrder is the fixed seven-slot pipe-delimited template that
// the HMAC-SHA256 challenge ID is computed over. It is the **single source of
// truth** for what the ID binds to and MUST match the TypeScript reference
// implementation's `idBindingInput` byte-for-byte.
//
// Slots (1-based):
//
//  1. realm
//  2. method
//  3. intent
//  4. request   (RFC 8785 canonical-JSON, then base64url, no padding)
//  5. expires   ("" if absent)
//  6. digest    ("" if absent)
//  7. opaque    ("" if absent)
//
// Optional slots use the empty string when absent so the slot count is stable
// — adding a new optional field changes all HMACs exactly once.
const CanonicalFieldOrder = "realm|method|intent|request|expires|digest|opaque"

// canonicalHMACInput returns the exact byte string the HMAC is computed over.
// It is exported only via ComputeChallengeID to keep callers from introducing
// alternative orderings by accident.
func canonicalHMACInput(c Challenge) ([]byte, error) {
	requestEncoded, err := EncodeRequest(c.Request)
	if err != nil {
		return nil, fmt.Errorf("mppx: encode request for HMAC: %w", err)
	}
	expires := ""
	if c.HasExpiry() {
		expires = formatExpires(c.Expires)
	}
	parts := []string{
		c.Realm,
		c.Method,
		c.Intent,
		requestEncoded,
		expires,
		c.Digest,
		c.Opaque,
	}
	return []byte(strings.Join(parts, "|")), nil
}

// ComputeChallengeID returns the HMAC-SHA256 challenge identifier for the
// given challenge under the supplied secret key, base64url-encoded without
// padding. The input is structured per [CanonicalFieldOrder].
//
// The challenge's existing ID field is ignored on input.
func ComputeChallengeID(secretKey []byte, c Challenge) (string, error) {
	if len(secretKey) == 0 {
		return "", errors.New("mppx: secretKey is required")
	}
	input, err := canonicalHMACInput(c)
	if err != nil {
		return "", err
	}
	mac := hmac.New(sha256.New, secretKey)
	mac.Write(input)
	return base64URLNoPad.EncodeToString(mac.Sum(nil)), nil
}

// VerifyChallengeID re-derives the expected HMAC for the challenge under the
// given secret key and compares it in constant time to the challenge's ID
// field. Returns nil when the IDs match, an error otherwise.
//
// Callers MUST run this before honouring any credential — it is the only
// thing that proves the challenge contents have not been tampered with.
func VerifyChallengeID(secretKey []byte, c Challenge) error {
	expected, err := ComputeChallengeID(secretKey, c)
	if err != nil {
		return err
	}
	if subtle.ConstantTimeCompare([]byte(expected), []byte(c.ID)) != 1 {
		return errors.New("mppx: challenge ID does not match expected HMAC")
	}
	return nil
}
