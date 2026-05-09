package mppx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

// Receipt mirrors the TS `Receipt.Receipt` schema. It is the post-verification
// acknowledgement Alice sends back to Bob, encoded as a base64url JSON value
// in the `Payment-Receipt` HTTP header (or the `paymentReceipt` field of a
// pub/sub ReceiptMessage).
type Receipt struct {
	// Method is the payment method that was settled (e.g. "tempo").
	Method string

	// Reference is the method-specific reference for the settlement. For
	// tempo/charge it is the on-chain transaction hash (`0x…`).
	Reference string

	// ExternalID echoes an optional externalId from the credential payload
	// (used by some merchants for order tracking).
	ExternalID string

	// Status is always "success" — failures are signalled with HTTP 402 plus
	// an RFC 7807 / 9457 Problem Details body, never a receipt.
	Status string

	// Timestamp is the settlement time (RFC 3339).
	Timestamp time.Time
}

// SerializeReceipt encodes the receipt as a base64url(JSON) string suitable
// for the `Payment-Receipt` header value.
func SerializeReceipt(r Receipt) (string, error) {
	if err := validateReceipt(r); err != nil {
		return "", err
	}
	wire := receiptWire{
		Method:     r.Method,
		Reference:  r.Reference,
		ExternalID: optString(r.ExternalID),
		Status:     r.Status,
		Timestamp:  formatExpires(r.Timestamp),
	}
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(wire); err != nil {
		return "", err
	}
	raw := bytes.TrimRight(buf.Bytes(), "\n")
	return base64URLNoPad.EncodeToString(raw), nil
}

// DeserializeReceipt decodes a base64url(JSON) `Payment-Receipt` header value.
func DeserializeReceipt(encoded string) (Receipt, error) {
	encoded = strings.TrimSpace(encoded)
	if encoded == "" {
		return Receipt{}, errors.New("mppx: empty receipt")
	}
	raw, err := base64URLNoPad.DecodeString(encoded)
	if err != nil {
		raw, err = base64URLDecodeFlexible(encoded)
		if err != nil {
			return Receipt{}, fmt.Errorf("mppx: invalid base64: %w", err)
		}
	}
	var wire receiptWire
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&wire); err != nil {
		return Receipt{}, fmt.Errorf("mppx: invalid receipt JSON: %w", err)
	}
	t, err := parseExpires(wire.Timestamp)
	if err != nil {
		return Receipt{}, fmt.Errorf("mppx: parse timestamp: %w", err)
	}
	r := Receipt{
		Method:    wire.Method,
		Reference: wire.Reference,
		Status:    wire.Status,
		Timestamp: t,
	}
	if wire.ExternalID != nil {
		r.ExternalID = *wire.ExternalID
	}
	if err := validateReceipt(r); err != nil {
		return Receipt{}, err
	}
	return r, nil
}

func validateReceipt(r Receipt) error {
	if r.Method == "" {
		return errors.New("mppx: receipt.Method is required")
	}
	if r.Reference == "" {
		return errors.New("mppx: receipt.Reference is required")
	}
	if r.Status == "" {
		return errors.New("mppx: receipt.Status is required")
	}
	if r.Status != "success" {
		return fmt.Errorf(`mppx: receipt.Status must be "success", got %q`, r.Status)
	}
	if r.Timestamp.IsZero() {
		return errors.New("mppx: receipt.Timestamp is required")
	}
	return nil
}

type receiptWire struct {
	Method     string  `json:"method"`
	Reference  string  `json:"reference"`
	ExternalID *string `json:"externalId,omitempty"`
	Status     string  `json:"status"`
	Timestamp  string  `json:"timestamp"`
}
