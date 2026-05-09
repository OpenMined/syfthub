package mppx

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

// Challenge mirrors the TypeScript `Challenge.Schema` from `mppx`. It is the
// in-memory shape of a payment challenge as parsed from a `WWW-Authenticate:
// Payment …` header value (or a pub/sub challenge message).
//
// The `Request` field holds the method-specific payload (for `tempo/charge`
// it contains amount, currency, recipient, and optional methodDetails). It is
// kept as a generic map so this package can support any MPP method without
// recompilation.
//
// The `ID` field is HMAC-SHA256-bound to the other fields when produced by a
// server that holds a `secretKey`. It is the only field a verifier needs to
// re-derive to detect tampering.
type Challenge struct {
	// ID is the HMAC-SHA256 challenge identifier (base64url, no padding) or
	// an opaque server-chosen string when no secret key is in use.
	ID string

	// Realm identifies the payment context (e.g. a hostname or a pub/sub
	// topic such as "pubsub://alice/pay").
	Realm string

	// Method is the payment method name (e.g. "tempo", "stripe").
	Method string

	// Intent is the method intent (e.g. "charge", "session").
	Intent string

	// Request is the method-specific request payload.
	Request map[string]any

	// Description is an optional human-readable description.
	Description string

	// Digest is an optional body digest (RFC 9530, "sha-256=…").
	Digest string

	// Expires is the optional challenge expiry time. The wire format uses
	// ISO 8601 / RFC 3339; the zero value means "no expiry".
	Expires time.Time

	// Opaque is the optional server-defined correlation data, already
	// serialised as a base64url string per the MPP spec. Clients MUST NOT
	// modify it.
	Opaque string
}

// HasExpiry reports whether the challenge carries an expiry timestamp.
func (c Challenge) HasExpiry() bool { return !c.Expires.IsZero() }

// IsExpired returns true when the challenge has an expiry that lies strictly
// before `now`.
func (c Challenge) IsExpired(now time.Time) bool {
	return c.HasExpiry() && now.After(c.Expires)
}

// SerializeChallenge produces the canonical `Payment id="…", realm="…", …`
// string suitable for use as a `WWW-Authenticate` HTTP header value or as the
// `wwwAuthenticate` field of a pub/sub ChallengeMessage.
//
// The field order is fixed (id, realm, method, intent, request, then optional
// description, digest, expires, opaque) to mirror the TypeScript reference.
func SerializeChallenge(c Challenge) (string, error) {
	if c.ID == "" {
		return "", errors.New("mppx: challenge.ID is required for serialisation")
	}
	if c.Realm == "" {
		return "", errors.New("mppx: challenge.Realm is required")
	}
	if c.Method == "" {
		return "", errors.New("mppx: challenge.Method is required")
	}
	if c.Intent == "" {
		return "", errors.New("mppx: challenge.Intent is required")
	}
	if c.Request == nil {
		return "", errors.New("mppx: challenge.Request is required")
	}
	requestEncoded, err := EncodeRequest(c.Request)
	if err != nil {
		return "", fmt.Errorf("mppx: encode request: %w", err)
	}

	parts := []string{
		fmt.Sprintf(`id=%q`, c.ID),
		fmt.Sprintf(`realm=%q`, c.Realm),
		fmt.Sprintf(`method=%q`, c.Method),
		fmt.Sprintf(`intent=%q`, c.Intent),
		fmt.Sprintf(`request=%q`, requestEncoded),
	}
	if c.Description != "" {
		parts = append(parts, fmt.Sprintf(`description=%q`, c.Description))
	}
	if c.Digest != "" {
		parts = append(parts, fmt.Sprintf(`digest=%q`, c.Digest))
	}
	if c.HasExpiry() {
		parts = append(parts, fmt.Sprintf(`expires=%q`, formatExpires(c.Expires)))
	}
	if c.Opaque != "" {
		parts = append(parts, fmt.Sprintf(`opaque=%q`, c.Opaque))
	}
	return "Payment " + strings.Join(parts, ", "), nil
}

// formatExpires formats t as an RFC 3339 / ISO 8601 string with a trailing
// "Z" UTC suffix. The TypeScript implementation produces millisecond
// precision via `Date.toISOString()`; we match that to keep HMACs stable
// across re-encoding.
func formatExpires(t time.Time) string {
	return t.UTC().Format("2006-01-02T15:04:05.000Z07:00")
}

// DeserializeChallenge parses a `WWW-Authenticate: Payment …` header value
// (or the bare `Payment …` value carried by a pub/sub challenge message)
// into a Challenge. It accepts the same lax parsing the TS implementation
// allows: whitespace around `=`, escaped quoted-string values, and skips a
// leading "Payment " scheme token.
func DeserializeChallenge(wwwAuthenticate string) (Challenge, error) {
	body, ok := stripPaymentScheme(wwwAuthenticate)
	if !ok {
		return Challenge{}, errors.New("mppx: missing Payment scheme")
	}
	params, err := parseAuthParams(body)
	if err != nil {
		return Challenge{}, err
	}

	get := func(key string) string {
		v, ok := params[key]
		if !ok {
			return ""
		}
		return v
	}

	requestEncoded := get("request")
	if requestEncoded == "" {
		return Challenge{}, errors.New("mppx: missing request parameter")
	}
	request, err := DecodeRequest(requestEncoded)
	if err != nil {
		return Challenge{}, fmt.Errorf("mppx: decode request: %w", err)
	}

	c := Challenge{
		ID:          get("id"),
		Realm:       get("realm"),
		Method:      get("method"),
		Intent:      get("intent"),
		Request:     request,
		Description: get("description"),
		Digest:      get("digest"),
		Opaque:      get("opaque"),
	}
	if expiresStr := get("expires"); expiresStr != "" {
		t, err := parseExpires(expiresStr)
		if err != nil {
			return Challenge{}, fmt.Errorf("mppx: parse expires: %w", err)
		}
		c.Expires = t
	}
	return c, nil
}

func parseExpires(s string) (time.Time, error) {
	// Accept both millisecond and second precision RFC 3339.
	for _, layout := range []string{
		"2006-01-02T15:04:05.000Z07:00",
		time.RFC3339Nano,
		time.RFC3339,
	} {
		if t, err := time.Parse(layout, s); err == nil {
			return t.UTC(), nil
		}
	}
	return time.Time{}, fmt.Errorf("invalid timestamp %q", s)
}

// stripPaymentScheme removes the leading "Payment " token (case-insensitive)
// from a header value, returning the remaining auth-params and a boolean
// indicating whether the scheme was found. It does not support multiple
// challenges in one header (use DeserializeChallengeList for that).
func stripPaymentScheme(header string) (string, bool) {
	const scheme = "Payment"
	trimmed := strings.TrimLeft(header, " \t")
	if len(trimmed) < len(scheme)+1 {
		return "", false
	}
	if !strings.EqualFold(trimmed[:len(scheme)], scheme) {
		return "", false
	}
	rest := trimmed[len(scheme):]
	if len(rest) == 0 || (rest[0] != ' ' && rest[0] != '\t') {
		return "", false
	}
	return strings.TrimLeft(rest, " \t"), true
}

// parseAuthParams parses HTTP auth-params. It handles bare and quoted values
// (including backslash-escaped characters inside quotes). It rejects
// duplicate keys.
func parseAuthParams(input string) (map[string]string, error) {
	params := make(map[string]string)
	i := 0
	n := len(input)
	for i < n {
		// skip whitespace and commas
		for i < n && (input[i] == ' ' || input[i] == '\t' || input[i] == ',') {
			i++
		}
		if i >= n {
			break
		}
		// read key
		keyStart := i
		for i < n && (isAuthKeyByte(input[i])) {
			i++
		}
		key := input[keyStart:i]
		if key == "" {
			return nil, fmt.Errorf("mppx: malformed auth-param near %q", input[keyStart:])
		}
		// skip whitespace
		for i < n && (input[i] == ' ' || input[i] == '\t') {
			i++
		}
		if i >= n || input[i] != '=' {
			break // bare token — treat as another auth scheme; stop here.
		}
		i++ // consume '='
		for i < n && (input[i] == ' ' || input[i] == '\t') {
			i++
		}
		var value string
		if i < n && input[i] == '"' {
			i++
			var sb strings.Builder
			escaped := false
			closed := false
			for i < n {
				c := input[i]
				i++
				if escaped {
					sb.WriteByte(c)
					escaped = false
					continue
				}
				if c == '\\' {
					escaped = true
					continue
				}
				if c == '"' {
					closed = true
					break
				}
				sb.WriteByte(c)
			}
			if !closed {
				return nil, errors.New("mppx: unterminated quoted-string")
			}
			value = sb.String()
		} else {
			start := i
			for i < n && input[i] != ',' {
				i++
			}
			value = strings.TrimSpace(input[start:i])
		}
		if _, dup := params[key]; dup {
			return nil, fmt.Errorf("mppx: duplicate parameter %q", key)
		}
		params[key] = value
	}
	return params, nil
}

func isAuthKeyByte(b byte) bool {
	return (b >= 'A' && b <= 'Z') ||
		(b >= 'a' && b <= 'z') ||
		(b >= '0' && b <= '9') ||
		b == '_' || b == '-'
}
