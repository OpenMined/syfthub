// Package updater implements the auto-update notify + hard-gate mechanism
// for syfthub-desktop. Phase 1 owns: manifest fetch, semver compare,
// disk cache, state machine, background check loop.
//
// Phase 2 adds streaming download with SHA-256 verification.
// Phase 3 adds in-place binary replace on Linux + Windows.
// Phase 4 adds in-place .app-bundle replace on signed/notarized macOS.
// Phase 5 adds Ed25519 manifest signature verification.
package updater

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"
)

// CurrentSchemaVersion is the only manifest schema this client knows how
// to parse. A manifest with a higher schema_version is refused; a manifest
// with a lower schema_version is accepted (fields are additive in v1).
const CurrentSchemaVersion = 1

// ManifestURL is the canonical stable manifest URL. It points at a
// non-versioned GitHub Release whose only asset is manifest.json, kept
// fresh by the release workflow.
const ManifestURL = "https://github.com/OpenMined/syfthub/releases/download/desktop/latest-stable/manifest.json"

// ManifestEnvOverride, when set, replaces ManifestURL. Used for forks and
// integration tests.
const ManifestEnvOverride = "SYFTHUB_DESKTOP_UPDATE_MANIFEST_URL"

// SkipEnv, when set to a truthy value, disables the entire updater
// (no checks, no banner, no gate). Documented in RELEASING.md as the
// emergency bypass.
const SkipEnv = "SYFTHUB_DESKTOP_SKIP_UPDATE_CHECK"

// PlatformAsset describes one downloadable binary in the manifest.
type PlatformAsset struct {
	URL       string `json:"url"`
	SHA256    string `json:"sha256"`
	SizeBytes int64  `json:"size_bytes"`
}

// Manifest is the parsed form of manifest.json.
type Manifest struct {
	SchemaVersion       int                      `json:"schema_version"`
	Version             string                   `json:"version"`
	MinSupportedVersion string                   `json:"min_supported_version"`
	PublishedAt         time.Time                `json:"published_at"`
	ReleaseNotesURL     string                   `json:"release_notes_url"`
	MustUpdateReason    string                   `json:"must_update_reason,omitempty"`
	Platforms           map[string]PlatformAsset `json:"platforms"`
}

// PlatformKey returns the goos/goarch key used in the platforms map.
func PlatformKey(goos, goarch string) string {
	return goos + "/" + goarch
}

// AssetFor returns the asset for the given goos/goarch, or ok=false if
// the manifest has no entry for this platform.
func (m *Manifest) AssetFor(goos, goarch string) (PlatformAsset, bool) {
	a, ok := m.Platforms[PlatformKey(goos, goarch)]
	return a, ok
}

// Validate checks structural invariants. It does NOT fetch anything.
func (m *Manifest) Validate() error {
	if m.SchemaVersion <= 0 {
		return errors.New("manifest: missing schema_version")
	}
	if m.SchemaVersion > CurrentSchemaVersion {
		return fmt.Errorf("manifest: schema_version %d is newer than supported %d — update the app", m.SchemaVersion, CurrentSchemaVersion)
	}
	if m.Version == "" {
		return errors.New("manifest: missing version")
	}
	if m.MinSupportedVersion == "" {
		return errors.New("manifest: missing min_supported_version")
	}
	if !IsValidSemver(m.Version) {
		return fmt.Errorf("manifest: version %q is not valid semver", m.Version)
	}
	if !IsValidSemver(m.MinSupportedVersion) {
		return fmt.Errorf("manifest: min_supported_version %q is not valid semver", m.MinSupportedVersion)
	}
	if len(m.Platforms) == 0 {
		return errors.New("manifest: platforms map is empty")
	}
	for key, asset := range m.Platforms {
		if asset.URL == "" {
			return fmt.Errorf("manifest: platform %q missing url", key)
		}
		if len(asset.SHA256) != 64 {
			return fmt.Errorf("manifest: platform %q has invalid sha256 (expected 64 hex chars, got %d)", key, len(asset.SHA256))
		}
		if asset.SizeBytes <= 0 {
			return fmt.Errorf("manifest: platform %q has non-positive size_bytes", key)
		}
	}
	return nil
}

// maxManifestBytes caps the JSON body to bound memory.
const maxManifestBytes = 1 << 20 // 1 MiB

// FetchManifest downloads, parses, and validates the manifest.
// The HTTP client and URL are caller-supplied to make testing trivial.
//
// Phase 5: the manifest body is verified against the embedded Ed25519
// public key (when configured). The signature is fetched from
// <url>.sig. By default the verification is "lenient" — a missing
// signature is permitted (transition until all clients ship with the
// key); a present-but-invalid signature is always rejected.
// Set SYFTHUB_DESKTOP_REQUIRE_SIGNATURE=1 for strict mode.
func FetchManifest(client *http.Client, url string) (*Manifest, error) {
	return fetchManifestCtx(context.Background(), client, url)
}

// fetchManifestCtx is the context-aware fetch used internally by the
// checker loop. Public callers should use FetchManifest.
func fetchManifestCtx(ctx context.Context, client *http.Client, url string) (*Manifest, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("build manifest request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "syfthub-desktop-updater/1")

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetch manifest: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("fetch manifest: HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxManifestBytes+1))
	if err != nil {
		return nil, fmt.Errorf("read manifest body: %w", err)
	}
	if len(body) > maxManifestBytes {
		return nil, fmt.Errorf("manifest body exceeds %d bytes — refusing to parse", maxManifestBytes)
	}

	// Signature verification BEFORE parsing — defense in depth.
	sig, sigErr := fetchSignature(client, url)
	if sigErr != nil {
		// Network error fetching .sig: in strict mode, refuse. In
		// lenient mode, treat as "no signature" and continue.
		if requireSignature() {
			return nil, fmt.Errorf("fetch signature: %w", sigErr)
		}
	}
	if err := verifyManifest(body, sig); err != nil {
		return nil, err
	}

	return decodeAndValidate(body)
}

// decodeAndValidate parses a JSON manifest body and runs Validate.
func decodeAndValidate(body []byte) (*Manifest, error) {
	var m Manifest
	if err := json.Unmarshal(body, &m); err != nil {
		return nil, fmt.Errorf("parse manifest: %w", err)
	}
	if err := m.Validate(); err != nil {
		return nil, err
	}
	return &m, nil
}
