package updater

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// CacheTTL is the maximum age a cached manifest may have before it's
// considered expired for the offline hard-gate check. 14 days balances
// security (force-update reaches users even offline) with availability
// (don't brick a user who's been offline for two weeks).
const CacheTTL = 14 * 24 * time.Hour

// cacheFileName is the file (under the caller-provided dir) that holds
// the cached manifest + fetch timestamp.
const cacheFileName = "manifest-cache.json"

// cachedManifest is the disk representation. Wrapping the manifest in an
// envelope lets us add fields (e.g., signature) without changing the
// manifest schema.
type cachedManifest struct {
	FetchedAt time.Time `json:"fetched_at"`
	Manifest  *Manifest `json:"manifest"`
}

// Cache reads and writes the manifest cache under dir. dir is typically
// the settings directory.
type Cache struct {
	dir string
}

func NewCache(dir string) *Cache {
	return &Cache{dir: dir}
}

func (c *Cache) path() string {
	return filepath.Join(c.dir, cacheFileName)
}

// Load returns the cached manifest and its fetch time, or (nil, zero, nil)
// if the cache is missing. Returns an error only on unrecoverable IO /
// parse failures — a corrupted cache is treated as missing.
func (c *Cache) Load() (*Manifest, time.Time, error) {
	data, err := os.ReadFile(c.path())
	if err != nil {
		if os.IsNotExist(err) {
			return nil, time.Time{}, nil
		}
		return nil, time.Time{}, fmt.Errorf("read manifest cache: %w", err)
	}
	var env cachedManifest
	if err := json.Unmarshal(data, &env); err != nil {
		// Corrupt cache is recoverable — pretend it's missing.
		return nil, time.Time{}, nil
	}
	if env.Manifest == nil {
		return nil, time.Time{}, nil
	}
	if err := env.Manifest.Validate(); err != nil {
		// Cache contains a manifest that no longer validates (perhaps a
		// schema mismatch after an upgrade) — discard it.
		return nil, time.Time{}, nil
	}
	return env.Manifest, env.FetchedAt, nil
}

// Save writes manifest to disk with the supplied fetch time. The write
// is atomic (write-to-tmp + rename).
func (c *Cache) Save(m *Manifest, fetchedAt time.Time) error {
	if err := os.MkdirAll(c.dir, 0o755); err != nil {
		return fmt.Errorf("create cache dir: %w", err)
	}
	env := cachedManifest{FetchedAt: fetchedAt, Manifest: m}
	data, err := json.MarshalIndent(env, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal cache: %w", err)
	}
	tmp := c.path() + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return fmt.Errorf("write cache tmp: %w", err)
	}
	if err := os.Rename(tmp, c.path()); err != nil {
		return fmt.Errorf("rename cache: %w", err)
	}
	return nil
}

// IsFresh reports whether the supplied fetch time is within CacheTTL of now.
func IsFresh(fetchedAt time.Time, now time.Time) bool {
	if fetchedAt.IsZero() {
		return false
	}
	return now.Sub(fetchedAt) <= CacheTTL
}
