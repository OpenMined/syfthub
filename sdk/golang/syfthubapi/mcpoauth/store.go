package mcpoauth

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sync"

	"golang.org/x/oauth2"
)

// Record is the persisted OAuth state for one MCP server: the resolved
// endpoints, the registered client, the resource indicator, and the current
// token (access + refresh + expiry). It holds secrets — store 0600, host-only.
type Record struct {
	AuthServer    string        `json:"auth_server"`
	AuthEndpoint  string        `json:"auth_endpoint"`
	TokenEndpoint string        `json:"token_endpoint"`
	ClientID      string        `json:"client_id"`
	ClientSecret  string        `json:"client_secret,omitempty"`
	Scopes        []string      `json:"scopes,omitempty"`
	Resource      string        `json:"resource"`
	Token         *oauth2.Token `json:"token"`
}

// config rebuilds the oauth2.Config used to refresh the token.
func (r *Record) config() *oauth2.Config {
	return &oauth2.Config{
		ClientID:     r.ClientID,
		ClientSecret: r.ClientSecret,
		Endpoint:     oauth2.Endpoint{AuthURL: r.AuthEndpoint, TokenURL: r.TokenEndpoint},
		Scopes:       r.Scopes,
	}
}

// TokenStore persists per-server OAuth records. Load returns (nil, nil) when no
// record exists for the server.
type TokenStore interface {
	Load(server string) (*Record, error)
	Save(server string, rec *Record) error
	Delete(server string) error
}

var safeServerName = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]*$`)

// ValidServerName reports whether name is a safe MCP server name: lowercase
// letters, digits, '-' or '_', starting with a letter or digit. This is the
// single naming rule shared by FileStore (names become token filenames) and
// hosts that key their registries/broker routes by server name — a name that
// passes here is guaranteed storable.
func ValidServerName(name string) bool { return safeServerName.MatchString(name) }

// FileStore persists each server's record as <dir>/<server>.json, 0600.
type FileStore struct {
	dir string
	mu  sync.Mutex
}

// NewFileStore stores records under dir (created on first Save).
func NewFileStore(dir string) *FileStore { return &FileStore{dir: dir} }

func (s *FileStore) path(server string) (string, bool) {
	if !safeServerName.MatchString(server) {
		return "", false
	}
	return filepath.Join(s.dir, server+".json"), true
}

func (s *FileStore) Load(server string) (*Record, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	path, ok := s.path(server)
	if !ok {
		return nil, nil
	}
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var rec Record
	if err := json.Unmarshal(data, &rec); err != nil {
		return nil, err
	}
	return &rec, nil
}

func (s *FileStore) Save(server string, rec *Record) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	path, ok := s.path(server)
	if !ok {
		return os.ErrInvalid
	}
	if err := os.MkdirAll(s.dir, 0o700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(rec, "", "  ")
	if err != nil {
		return err
	}
	// Temp-file + rename so a crash mid-write can never leave a torn token
	// record (this file is the server's only credential).
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o600); err != nil {
		return err
	}
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}

func (s *FileStore) Delete(server string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	path, ok := s.path(server)
	if !ok {
		return nil
	}
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
