package mppx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// Credential mirrors the TS `Credential.Credential` type. It echoes the full
// challenge back to the verifier (so the HMAC can be re-checked) plus a
// method-specific Payload (the actual proof — for tempo/charge this is a
// transaction signature) and an optional Source DID identifying the payer.
type Credential struct {
	// Challenge is the full challenge being responded to. The verifier
	// re-derives the HMAC ID from this echoed copy.
	Challenge Challenge

	// Payload carries the method-specific payment proof. For tempo/charge it
	// is a [TempoChargePayload]; other methods use other types. Stored as
	// `any` so this package supports arbitrary methods.
	Payload any

	// Source is the optional payer DID, e.g.
	// "did:pkh:eip155:42431:0xC40DcC…".
	Source string
}

// SerializeCredential serialises a credential to its `Authorization: Payment …`
// header value. The challenge is embedded with the original `request` field
// re-encoded as a base64url string (matching the TS wire shape).
//
// Field order in the resulting JSON is: challenge, payload, source. Within
// the embedded challenge: id, realm, method, intent, then any optional
// fields in their declaration order, then the request as a base64url string.
// This ordering is *not* required for re-parsing but is preserved for
// byte-for-byte comparison with TS-emitted credentials in tests.
func SerializeCredential(c Credential) (string, error) {
	if c.Challenge.ID == "" {
		return "", errors.New("mppx: credential.Challenge.ID is required")
	}
	requestEncoded, err := EncodeRequest(c.Challenge.Request)
	if err != nil {
		return "", err
	}
	chWire := credentialChallengeWire{
		ID:          c.Challenge.ID,
		Realm:       c.Challenge.Realm,
		Method:      c.Challenge.Method,
		Intent:      c.Challenge.Intent,
		Description: optString(c.Challenge.Description),
		Digest:      optString(c.Challenge.Digest),
		Opaque:      optString(c.Challenge.Opaque),
		Request:     requestEncoded,
	}
	if c.Challenge.HasExpiry() {
		chWire.Expires = optString(formatExpires(c.Challenge.Expires))
	}

	wire := credentialWire{
		Challenge: chWire,
		Payload:   c.Payload,
		Source:    optString(c.Source),
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(wire); err != nil {
		return "", err
	}
	raw := bytes.TrimRight(buf.Bytes(), "\n")
	return "Payment " + base64URLNoPad.EncodeToString(raw), nil
}

// DeserializeCredential parses a `Payment <base64url-JSON>` value into a
// Credential. The embedded challenge's `request` (a base64url string on the
// wire) is decoded back into a structured map.
func DeserializeCredential(authorization string) (Credential, error) {
	body, ok := stripPaymentScheme(authorization)
	if !ok {
		return Credential{}, errors.New("mppx: missing Payment scheme")
	}
	raw, err := base64URLNoPad.DecodeString(strings.TrimSpace(body))
	if err != nil {
		// Some senders pad; fall back to standard URL encoding.
		if raw2, err2 := base64URLDecodeFlexible(strings.TrimSpace(body)); err2 == nil {
			raw = raw2
		} else {
			return Credential{}, fmt.Errorf("mppx: invalid base64: %w", err)
		}
	}
	var wire credentialWire
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&wire); err != nil {
		return Credential{}, fmt.Errorf("mppx: invalid credential JSON: %w", err)
	}
	requestMap, err := DecodeRequest(wire.Challenge.Request)
	if err != nil {
		return Credential{}, fmt.Errorf("mppx: invalid embedded request: %w", err)
	}
	cred := Credential{
		Challenge: Challenge{
			ID:      wire.Challenge.ID,
			Realm:   wire.Challenge.Realm,
			Method:  wire.Challenge.Method,
			Intent:  wire.Challenge.Intent,
			Request: requestMap,
		},
		Payload: wire.Payload,
	}
	if wire.Challenge.Description != nil {
		cred.Challenge.Description = *wire.Challenge.Description
	}
	if wire.Challenge.Digest != nil {
		cred.Challenge.Digest = *wire.Challenge.Digest
	}
	if wire.Challenge.Expires != nil {
		t, err := parseExpires(*wire.Challenge.Expires)
		if err != nil {
			return Credential{}, err
		}
		cred.Challenge.Expires = t
	}
	if wire.Challenge.Opaque != nil {
		cred.Challenge.Opaque = *wire.Challenge.Opaque
	}
	if wire.Source != nil {
		cred.Source = *wire.Source
	}
	return cred, nil
}

// optString returns nil for the empty string and a pointer to s otherwise.
// Used to drive `omitempty` on optional `*string` JSON fields.
func optString(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// base64URLDecodeFlexible accepts both padded and unpadded URL base64.
func base64URLDecodeFlexible(s string) ([]byte, error) {
	// Re-pad to a multiple of 4 then use the padded URL encoding.
	switch len(s) % 4 {
	case 2:
		s += "=="
	case 3:
		s += "="
	}
	return paddedURLEncoding.DecodeString(s)
}

// ── wire types ────────────────────────────────────────────────────────────

type credentialChallengeWire struct {
	ID          string  `json:"id"`
	Realm       string  `json:"realm"`
	Method      string  `json:"method"`
	Intent      string  `json:"intent"`
	Description *string `json:"description,omitempty"`
	Digest      *string `json:"digest,omitempty"`
	Expires     *string `json:"expires,omitempty"`
	Opaque      *string `json:"opaque,omitempty"`
	// Request is base64url(canonical-JSON) on the wire.
	Request string `json:"request"`
}

type credentialWire struct {
	Challenge credentialChallengeWire `json:"challenge"`
	Payload   any                     `json:"payload"`
	Source    *string                 `json:"source,omitempty"`
}
