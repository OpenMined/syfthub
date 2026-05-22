// Package mppxgate is the Go side of the X402PayPerRequestPolicy. It bridges
// the Python policy_manager policy with the mppx crypto layer: it materializes
// HMAC-bound challenges from policy specs, verifies signed-transfer
// credentials, and broadcasts the held signed transactions after the handler
// succeeds (settle-on-success).
package mppxgate

import (
	"crypto/rand"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// SecretStore returns the HMAC secret bytes for a given kid. The kid mirrors
// the JWT "kid" pattern: it is an opaque, non-secret identifier that the
// Python policy carries in its config (see x402_pay_per_request.py's
// hmac_secret_kid) so the Go gate can look up the secret material the
// Python side never sees.
type SecretStore interface {
	Get(kid string) ([]byte, error)
}

// FileSecretStore is a local-filesystem backed SecretStore that stores each
// kid's secret under <dir>/<kid>.key with 0600 permissions. On the first
// Get for a kid that has no file, FileSecretStore generates 32 fresh random
// bytes, writes them to disk, and returns them.
//
// FileSecretStore is safe for concurrent use; a per-store mutex serializes
// generate+write so two simultaneous Get calls for the same kid cannot
// produce two different secrets.
type FileSecretStore struct {
	dir string
	mu  sync.Mutex
}

// NewFileSecretStore returns a FileSecretStore that reads/writes secrets
// under dir. dir is created (with 0700) on first use if missing.
func NewFileSecretStore(dir string) *FileSecretStore {
	return &FileSecretStore{dir: dir}
}

// Get returns the HMAC secret for kid, generating + persisting a fresh 32-byte
// secret on first ask. The kid must not be empty and must be a single path
// segment (no separators) — both to keep the lookup unambiguous and to avoid
// accidental path traversal.
func (s *FileSecretStore) Get(kid string) ([]byte, error) {
	if err := validateKid(kid); err != nil {
		return nil, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	path := filepath.Join(s.dir, kid+".key")
	if data, err := os.ReadFile(path); err == nil {
		if len(data) == 0 {
			return nil, fmt.Errorf("mppxgate: secret file %q is empty", path)
		}
		return data, nil
	} else if !os.IsNotExist(err) {
		return nil, fmt.Errorf("mppxgate: read secret %q: %w", path, err)
	}

	// Generate + persist.
	if err := os.MkdirAll(s.dir, 0o700); err != nil {
		return nil, fmt.Errorf("mppxgate: create secret dir %q: %w", s.dir, err)
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		return nil, fmt.Errorf("mppxgate: generate secret: %w", err)
	}
	// Write atomically via a temp file in the same dir.
	tmp, err := os.CreateTemp(s.dir, kid+".key.*")
	if err != nil {
		return nil, fmt.Errorf("mppxgate: create temp: %w", err)
	}
	tmpPath := tmp.Name()
	if _, err := tmp.Write(secret); err != nil {
		tmp.Close()
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("mppxgate: write secret: %w", err)
	}
	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("mppxgate: chmod secret: %w", err)
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("mppxgate: close temp: %w", err)
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return nil, fmt.Errorf("mppxgate: rename temp: %w", err)
	}
	return secret, nil
}

// validateKid rejects empty kids and any kid that would let a caller escape
// the configured directory via a path separator or "..".
func validateKid(kid string) error {
	if kid == "" {
		return errors.New("mppxgate: empty kid")
	}
	if kid == "." || kid == ".." {
		return fmt.Errorf("mppxgate: invalid kid %q", kid)
	}
	for _, r := range kid {
		if r == '/' || r == '\\' || r == 0 {
			return fmt.Errorf("mppxgate: kid contains path separator: %q", kid)
		}
	}
	return nil
}

// StaticSecretStore is a SecretStore backed by an in-memory map. Useful for
// tests and any caller that already knows its secrets out-of-band (e.g. read
// once at startup from an env var or KMS).
type StaticSecretStore struct {
	secrets map[string][]byte
}

// NewStaticSecretStore builds a StaticSecretStore from a kid→secret map. The
// map is copied; later mutations of the input map do not affect the store.
func NewStaticSecretStore(secrets map[string][]byte) *StaticSecretStore {
	cp := make(map[string][]byte, len(secrets))
	for k, v := range secrets {
		b := make([]byte, len(v))
		copy(b, v)
		cp[k] = b
	}
	return &StaticSecretStore{secrets: cp}
}

// Get returns the secret for kid or an error if absent.
func (s *StaticSecretStore) Get(kid string) ([]byte, error) {
	if err := validateKid(kid); err != nil {
		return nil, err
	}
	b, ok := s.secrets[kid]
	if !ok {
		return nil, fmt.Errorf("mppxgate: no secret for kid %q", kid)
	}
	out := make([]byte, len(b))
	copy(out, b)
	return out, nil
}
