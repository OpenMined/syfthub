package updater

import (
	"crypto/ed25519"
	"crypto/x509"
	_ "embed"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
)

// SignatureURLSuffix is the URL suffix appended to the manifest URL to
// produce the signature URL.
const SignatureURLSuffix = ".sig"

// RequireSigEnv, when set to a truthy value, makes the client refuse
// any manifest without a valid signature. Default mode is
// "verify if present": clients refuse a manifest whose signature is
// present-but-invalid, but accept a manifest with no signature
// (transition-friendly until the signing key is fully rolled out).
const RequireSigEnv = "SYFTHUB_DESKTOP_REQUIRE_SIGNATURE"

//go:embed embed/manifest_pubkey.pem
var embeddedPubKeyPEM []byte

// ErrSignatureRequired is returned when strict mode is on but no
// signature was published.
var ErrSignatureRequired = errors.New("manifest signature is required but missing")

// ErrSignatureInvalid is returned when a published signature does not
// verify against the embedded public key.
var ErrSignatureInvalid = errors.New("manifest signature does not verify")

// placeholderMarker is the substring present in the placeholder PEM
// shipped before the first key rotation. Manifest signature
// verification is silently skipped when this marker is present —
// useful during the Phase 5 transition and in tests.
const placeholderMarker = "PLACEHOLDER"

// pubKey returns the embedded Ed25519 public key, or (nil, nil) if the
// embedded PEM is the placeholder (no signing key configured yet).
func pubKey() (ed25519.PublicKey, error) {
	if strings.Contains(string(embeddedPubKeyPEM), placeholderMarker) {
		return nil, nil
	}
	block, _ := pem.Decode(embeddedPubKeyPEM)
	if block == nil {
		return nil, errors.New("embedded public key: not a valid PEM block")
	}
	key, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse public key: %w", err)
	}
	ed, ok := key.(ed25519.PublicKey)
	if !ok {
		return nil, errors.New("embedded public key is not Ed25519")
	}
	return ed, nil
}

// requireSignature reports whether the client is in strict mode.
func requireSignature() bool {
	v := os.Getenv(RequireSigEnv)
	return v == "1" || v == "true" || v == "yes"
}

// fetchSignature returns the raw 64-byte signature for the given manifest
// URL, or (nil, nil) if the .sig is missing. Network / parse failures
// return an error.
func fetchSignature(client *http.Client, manifestURL string) ([]byte, error) {
	resp, err := client.Get(manifestURL + SignatureURLSuffix)
	if err != nil {
		return nil, fmt.Errorf("fetch signature: %w", err)
	}
	defer resp.Body.Close()
	switch resp.StatusCode {
	case http.StatusNotFound:
		return nil, nil
	case http.StatusOK:
		// fall through
	default:
		return nil, fmt.Errorf("fetch signature: HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, 4096))
	if err != nil {
		return nil, fmt.Errorf("read signature body: %w", err)
	}
	return decodeSignature(body)
}

// decodeSignature accepts either raw 64 bytes OR base64-encoded
// (standard or URL-safe, with or without padding). Returns the raw
// 64-byte signature.
//
// The raw-size check must happen BEFORE any whitespace trim — random
// signature bytes regularly include 0x20 / 0x0a / 0x09 etc. and
// trimming them would silently corrupt a valid signature.
func decodeSignature(data []byte) ([]byte, error) {
	if len(data) == ed25519.SignatureSize {
		return data, nil
	}
	trimmed := strings.TrimSpace(string(data))
	for _, enc := range []*base64.Encoding{base64.StdEncoding, base64.URLEncoding, base64.RawStdEncoding, base64.RawURLEncoding} {
		decoded, err := enc.DecodeString(trimmed)
		if err == nil && len(decoded) == ed25519.SignatureSize {
			return decoded, nil
		}
	}
	return nil, fmt.Errorf("signature does not match Ed25519 size or any base64 encoding")
}

// verifyManifest checks the supplied signature against the manifest body
// using the embedded public key. Returns nil if verification succeeds,
// the manifest is unsigned and unsigned manifests are permitted, or the
// embedded key is the placeholder.
//
// The body parameter is the EXACT bytes returned by the server — not the
// re-serialized struct, since signatures are computed over the wire form.
func verifyManifest(body, sig []byte) error {
	if len(sig) == 0 {
		if requireSignature() {
			return ErrSignatureRequired
		}
		return nil
	}
	pk, err := pubKey()
	if err != nil {
		return fmt.Errorf("load embedded key: %w", err)
	}
	if pk == nil {
		// Placeholder key — skip verification entirely.
		return nil
	}
	if !ed25519.Verify(pk, body, sig) {
		return ErrSignatureInvalid
	}
	return nil
}
