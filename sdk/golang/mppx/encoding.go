package mppx

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
)

// base64URLNoPad is the encoding used everywhere in the wire format.
// MPP serialises everything with URL-safe base64 without padding.
var base64URLNoPad = base64.RawURLEncoding

// paddedURLEncoding is the lenient fallback for inbound credentials that
// happen to include `=` padding even though the spec mandates none.
var paddedURLEncoding = base64.URLEncoding

// EncodeRequest serialises a method-specific request payload to a base64url
// string using RFC 8785 canonical JSON. It is the same operation as
// `PaymentRequest.serialize` in the TypeScript implementation.
func EncodeRequest(request map[string]any) (string, error) {
	canon, err := CanonicalizeJSON(request)
	if err != nil {
		return "", err
	}
	return base64URLNoPad.EncodeToString(canon), nil
}

// DecodeRequest decodes a base64url-encoded JSON request payload back into a
// generic map. Numeric values are decoded as json.Number so callers can choose
// whether to interpret them as int64, *big.Int, etc., without losing
// precision (Tempo amounts are wei strings, so this matters for splits).
func DecodeRequest(encoded string) (map[string]any, error) {
	raw, err := base64URLNoPad.DecodeString(encoded)
	if err != nil {
		return nil, err
	}
	var out map[string]any
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}
