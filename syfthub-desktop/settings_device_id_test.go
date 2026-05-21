package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// withTempSettingsDir redirects getSettingsDir to a tempdir for the test.
// We can't override the unexported function directly, so we control the
// environment: on Linux $XDG_CONFIG_HOME is the trump card for getSettingsDir.
func withTempSettingsDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("XDG_CONFIG_HOME", dir)
	t.Setenv("APPDATA", dir) // windows
	t.Setenv("HOME", dir)    // darwin fallback
	return filepath.Join(dir, "syfthub")
}

// First LoadSettings on a fresh dir must mint a DeviceID and persist it so a
// second load returns the same value. Without persistence, every restart
// would steal the previous device's durable JetStream consumer queue.
func TestLoadSettings_MintsDeviceIDOnce(t *testing.T) {
	settingsDir := withTempSettingsDir(t)
	_ = settingsDir // future use; just here to assert side effect of side-effect mkdir

	first, err := LoadSettings()
	if err != nil {
		t.Fatalf("first load: %v", err)
	}
	if first.DeviceID == "" {
		t.Fatal("DeviceID should be set on first load")
	}
	if _, err := uuid.Parse(first.DeviceID); err != nil {
		t.Errorf("DeviceID %q is not a valid UUID: %v", first.DeviceID, err)
	}

	second, err := LoadSettings()
	if err != nil {
		t.Fatalf("second load: %v", err)
	}
	if second.DeviceID != first.DeviceID {
		t.Errorf("DeviceID changed across loads: %q -> %q", first.DeviceID, second.DeviceID)
	}
}

// An existing settings file without device_id (the upgrade path) must mint
// one and write it back without disturbing other fields.
func TestLoadSettings_BackfillsMissingDeviceID(t *testing.T) {
	withTempSettingsDir(t)

	// Write a pre-existing settings.json with no device_id.
	pre := DefaultSettings()
	pre.HubURL = "https://hub.example"
	pre.APIToken = "secret-token"
	pre.DeviceID = ""
	if err := SaveSettings(pre); err != nil {
		t.Fatalf("write pre: %v", err)
	}

	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if loaded.DeviceID == "" {
		t.Fatal("DeviceID should have been backfilled")
	}
	if loaded.HubURL != pre.HubURL || loaded.APIToken != pre.APIToken {
		t.Errorf("backfill mutated unrelated fields: %+v", loaded)
	}

	// Verify it was persisted (a second load should produce the same ID).
	loaded2, err := LoadSettings()
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if loaded2.DeviceID != loaded.DeviceID {
		t.Errorf("DeviceID not persisted on backfill: %q -> %q", loaded.DeviceID, loaded2.DeviceID)
	}
}

// A non-empty DeviceID in the file must be respected — even a malformed value
// is left alone so an operator can hand-edit settings without it being
// silently overwritten. (Validation, if needed later, belongs at the
// subscription naming layer.)
func TestLoadSettings_RespectsExistingDeviceID(t *testing.T) {
	withTempSettingsDir(t)
	pre := DefaultSettings()
	pre.DeviceID = "custom-id-not-a-uuid"
	if err := SaveSettings(pre); err != nil {
		t.Fatalf("save: %v", err)
	}
	loaded, err := LoadSettings()
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if loaded.DeviceID != "custom-id-not-a-uuid" {
		t.Errorf("existing DeviceID was overwritten: %q", loaded.DeviceID)
	}
}

// Sanity: a freshly minted DeviceID is shaped like a UUID v4 (4-prefixed
// version nibble). This guards against ever accidentally swapping in
// non-random generators.
func TestEnsureDeviceID_ShapeIsUUIDv4(t *testing.T) {
	s := &Settings{}
	if changed := ensureDeviceID(s); !changed {
		t.Fatal("expected ensureDeviceID to return true on empty input")
	}
	if !strings.Contains(s.DeviceID, "-") {
		t.Errorf("expected uuid-shaped id, got %q", s.DeviceID)
	}
	parsed, err := uuid.Parse(s.DeviceID)
	if err != nil {
		t.Fatalf("parse uuid: %v", err)
	}
	if parsed.Version() != 4 {
		t.Errorf("expected UUID v4, got version %d", parsed.Version())
	}

	// Idempotent: calling again with a non-empty DeviceID is a no-op.
	original := s.DeviceID
	if changed := ensureDeviceID(s); changed {
		t.Error("expected ensureDeviceID to return false when DeviceID already set")
	}
	if s.DeviceID != original {
		t.Errorf("DeviceID mutated by second ensure: %q -> %q", original, s.DeviceID)
	}
}

// Defensive: settings file is created with 0600 permissions (existing
// convention). Backfill must NOT loosen those permissions.
func TestLoadSettings_BackfillPreservesFilePerms(t *testing.T) {
	withTempSettingsDir(t)
	pre := DefaultSettings()
	pre.DeviceID = ""
	if err := SaveSettings(pre); err != nil {
		t.Fatalf("save: %v", err)
	}
	if _, err := LoadSettings(); err != nil {
		t.Fatalf("load: %v", err)
	}
	p, _ := getSettingsPath()
	info, err := os.Stat(p)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Errorf("settings.json perm = %o, want 0600", info.Mode().Perm())
	}
}
