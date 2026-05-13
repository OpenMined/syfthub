package updater

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestSemverCompare(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{
		{"0.1.0", "0.2.0", -1},
		{"0.2.0", "0.1.0", +1},
		{"0.2.0", "0.2.0", 0},
		{"v0.2.0", "0.2.0", 0},
		{"0.2.0-rc.1", "0.2.0", -1},
		{"0.2.0", "0.2.0-rc.1", +1},
		{"0.2.0-rc.1", "0.2.0-rc.2", -1},
		{"0.2.0-alpha", "0.2.0-beta", -1},
		{"0.2.0-rc.2", "0.2.0-rc.10", -1}, // numeric ordering
		{"1.0.0", "0.99.99", +1},
		{"dev", "0.1.0", +1},  // invalid > anything
		{"0.1.0", "dev", -1},
		{"dev", "dev", 0},
	}
	for _, c := range cases {
		t.Run(fmt.Sprintf("%s_vs_%s", c.a, c.b), func(t *testing.T) {
			got := CompareSemver(c.a, c.b)
			if got != c.want {
				t.Errorf("CompareSemver(%q, %q) = %d, want %d", c.a, c.b, got, c.want)
			}
		})
	}
}

func TestIsDevVersion(t *testing.T) {
	cases := map[string]bool{
		"":           true,
		"dev":        true,
		"0.1.0-dev":  true,
		"0.1.0-rc.1": true,
		"0.1.0-beta": true,
		"not-semver": true,
		"0.1.0":      false,
		"1.0.0":      false,
		"v1.0.0":     false,
	}
	for v, want := range cases {
		if got := IsDevVersion(v); got != want {
			t.Errorf("IsDevVersion(%q) = %v, want %v", v, got, want)
		}
	}
}

func validManifest() *Manifest {
	return &Manifest{
		SchemaVersion:       1,
		Version:             "0.2.0",
		MinSupportedVersion: "0.1.0",
		PublishedAt:         time.Now(),
		ReleaseNotesURL:     "https://example.com/r/0.2.0",
		Platforms: map[string]PlatformAsset{
			"linux/amd64": {
				URL:       "https://example.com/dl/linux",
				SHA256:    strings.Repeat("a", 64),
				SizeBytes: 12345,
			},
		},
	}
}

func TestManifestValidate(t *testing.T) {
	t.Run("valid", func(t *testing.T) {
		if err := validManifest().Validate(); err != nil {
			t.Fatalf("valid manifest failed validation: %v", err)
		}
	})

	t.Run("schema_version_too_new", func(t *testing.T) {
		m := validManifest()
		m.SchemaVersion = 99
		if err := m.Validate(); err == nil {
			t.Fatal("expected error for schema_version too new")
		}
	})

	t.Run("missing_min_supported_version", func(t *testing.T) {
		m := validManifest()
		m.MinSupportedVersion = ""
		if err := m.Validate(); err == nil {
			t.Fatal("expected error for missing min_supported_version")
		}
	})

	t.Run("bad_sha256", func(t *testing.T) {
		m := validManifest()
		a := m.Platforms["linux/amd64"]
		a.SHA256 = "tooshort"
		m.Platforms["linux/amd64"] = a
		if err := m.Validate(); err == nil {
			t.Fatal("expected error for bad sha256")
		}
	})

	t.Run("empty_platforms", func(t *testing.T) {
		m := validManifest()
		m.Platforms = map[string]PlatformAsset{}
		if err := m.Validate(); err == nil {
			t.Fatal("expected error for empty platforms")
		}
	})
}

func TestFetchManifestStatusCodes(t *testing.T) {
	cases := []int{404, 500, 502}
	for _, code := range cases {
		t.Run(fmt.Sprintf("HTTP_%d", code), func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(code)
			}))
			defer srv.Close()
			_, err := FetchManifest(srv.Client(), srv.URL)
			if err == nil {
				t.Fatal("expected error from non-200 status")
			}
		})
	}
}

func TestFetchManifestSizeCap(t *testing.T) {
	huge := make([]byte, maxManifestBytes+10)
	for i := range huge {
		huge[i] = 'x'
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write(huge)
	}))
	defer srv.Close()
	_, err := FetchManifest(srv.Client(), srv.URL)
	if err == nil {
		t.Fatal("expected error for oversized body")
	}
}

func TestCacheRoundTrip(t *testing.T) {
	dir := t.TempDir()
	c := NewCache(dir)

	if m, _, err := c.Load(); err != nil || m != nil {
		t.Fatalf("Load on empty dir = (%v, _, %v), want (nil, _, nil)", m, err)
	}

	want := validManifest()
	fetchedAt := time.Now().Round(time.Second)
	if err := c.Save(want, fetchedAt); err != nil {
		t.Fatalf("Save: %v", err)
	}

	got, ts, err := c.Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got == nil {
		t.Fatal("got nil after save")
	}
	if got.Version != want.Version {
		t.Errorf("Version = %q, want %q", got.Version, want.Version)
	}
	if !ts.Equal(fetchedAt) {
		t.Errorf("fetchedAt = %v, want %v", ts, fetchedAt)
	}
}

func TestCacheCorruptIgnored(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "manifest-cache.json"), []byte("{{not json"), 0o600); err != nil {
		t.Fatal(err)
	}
	c := NewCache(dir)
	m, _, err := c.Load()
	if err != nil {
		t.Fatalf("corrupt cache should not be an error: %v", err)
	}
	if m != nil {
		t.Fatal("expected nil manifest from corrupt cache")
	}
}

func TestIsFresh(t *testing.T) {
	now := time.Now()
	if !IsFresh(now.Add(-1*time.Hour), now) {
		t.Error("1h-old cache should be fresh")
	}
	if !IsFresh(now.Add(-13*24*time.Hour), now) {
		t.Error("13d-old cache should be fresh")
	}
	if IsFresh(now.Add(-15*24*time.Hour), now) {
		t.Error("15d-old cache should be stale")
	}
	if IsFresh(time.Time{}, now) {
		t.Error("zero time should be stale")
	}
}

// captureEmitter records the most recent state for assertion.
type captureEmitter struct {
	states []State
}

func (c *captureEmitter) Emit(s State) {
	c.states = append(c.states, s)
}

func (c *captureEmitter) Last() State {
	if len(c.states) == 0 {
		return State{}
	}
	return c.states[len(c.states)-1]
}

func makeManifest(version, minSupported string, platforms []string) *Manifest {
	m := &Manifest{
		SchemaVersion:       1,
		Version:             version,
		MinSupportedVersion: minSupported,
		Platforms:           map[string]PlatformAsset{},
	}
	for _, p := range platforms {
		m.Platforms[p] = PlatformAsset{
			URL:       "https://example.com/" + p,
			SHA256:    strings.Repeat("a", 64),
			SizeBytes: 1234,
		}
	}
	return m
}

func newCheckerWithManifest(t *testing.T, current string, m *Manifest) (*Checker, *captureEmitter) {
	t.Helper()
	body, _ := json.Marshal(m)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	t.Cleanup(srv.Close)

	emitter := &captureEmitter{}
	c := NewChecker(Options{
		CurrentVersion:   current,
		ManifestURL:      srv.URL,
		CacheDir:         t.TempDir(),
		HTTPClient:       srv.Client(),
		Emitter:          emitter,
		AutoCheckEnabled: true,
		GOOS:             "linux",
		GOARCH:           "amd64",
	})
	return c, emitter
}

func TestApplyManifestIdle(t *testing.T) {
	m := makeManifest("0.2.0", "0.1.0", []string{"linux/amd64"})
	c, em := newCheckerWithManifest(t, "0.2.0", m)
	c.applyManifest(m, time.Now(), "", time.Now())
	// publish is async via `go`, give it a moment
	time.Sleep(20 * time.Millisecond)
	if c.State().Stage != StageIdle {
		t.Errorf("stage = %v, want idle", c.State().Stage)
	}
	if got := em.Last().Stage; got != StageIdle {
		t.Errorf("emitter last stage = %v, want idle", got)
	}
}

func TestApplyManifestAvailable(t *testing.T) {
	m := makeManifest("0.2.0", "0.1.0", []string{"linux/amd64"})
	c, _ := newCheckerWithManifest(t, "0.1.5", m)
	c.applyManifest(m, time.Now(), "", time.Now())
	if c.State().Stage != StageAvailable {
		t.Errorf("stage = %v, want available", c.State().Stage)
	}
}

func TestApplyManifestMustUpdate(t *testing.T) {
	m := makeManifest("0.2.0", "0.1.5", []string{"linux/amd64"})
	c, _ := newCheckerWithManifest(t, "0.1.0", m)
	c.applyManifest(m, time.Now(), "", time.Now())
	if c.State().Stage != StageMustUpdate {
		t.Errorf("stage = %v, want must_update", c.State().Stage)
	}
}

func TestApplyManifestUnsupportedPlatform(t *testing.T) {
	// Manifest only carries darwin; checker is on linux/amd64.
	m := makeManifest("0.2.0", "0.1.0", []string{"darwin/arm64"})
	c, _ := newCheckerWithManifest(t, "0.1.5", m)
	c.applyManifest(m, time.Now(), "", time.Now())
	got := c.State().Stage
	// Below latest but no asset for our platform → unsupported.
	if got != StageUnsupportedPlatform {
		t.Errorf("stage = %v, want unsupported_platform", got)
	}
}

func TestInitialStageDevDisabled(t *testing.T) {
	c := NewChecker(Options{
		CurrentVersion: "dev",
		CacheDir:       t.TempDir(),
	})
	if c.State().Stage != StageDisabled {
		t.Errorf("stage = %v, want disabled", c.State().Stage)
	}
}

func TestInitialStageSkipEnv(t *testing.T) {
	t.Setenv(SkipEnv, "1")
	c := NewChecker(Options{
		CurrentVersion: "0.1.0",
		CacheDir:       t.TempDir(),
	})
	if c.State().Stage != StageDisabled {
		t.Errorf("stage = %v, want disabled (SkipEnv set)", c.State().Stage)
	}
}

func TestApplyFetchErrorWithFreshCache(t *testing.T) {
	dir := t.TempDir()
	// Seed cache with a manifest where current (0.1.0) is below min_supported (0.1.5).
	cached := makeManifest("0.2.0", "0.1.5", []string{"linux/amd64"})
	cache := NewCache(dir)
	if err := cache.Save(cached, time.Now()); err != nil {
		t.Fatal(err)
	}

	em := &captureEmitter{}
	c := NewChecker(Options{
		CurrentVersion:   "0.1.0",
		CacheDir:         dir,
		Emitter:          em,
		AutoCheckEnabled: true,
		GOOS:             "linux",
		GOARCH:           "amd64",
	})

	// applyFetchError should re-apply the cached manifest's must_update
	// even though the live fetch failed.
	c.applyFetchError(fmt.Errorf("simulated network failure"), time.Now())
	got := c.State()
	if got.Stage != StageMustUpdate {
		t.Errorf("stage = %v, want must_update (fresh cache, below floor)", got.Stage)
	}
	if got.LastError == "" {
		t.Error("expected LastError to be set")
	}
}

func TestApplyFetchErrorWithoutCache(t *testing.T) {
	em := &captureEmitter{}
	c := NewChecker(Options{
		CurrentVersion:   "0.1.0",
		CacheDir:         t.TempDir(),
		Emitter:          em,
		AutoCheckEnabled: true,
		GOOS:             "linux",
		GOARCH:           "amd64",
	})
	c.applyFetchError(fmt.Errorf("simulated"), time.Now())
	if c.State().Stage != StageOfflineNoGrace {
		t.Errorf("stage = %v, want offline_no_grace", c.State().Stage)
	}
}
