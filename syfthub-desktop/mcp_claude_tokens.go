package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sync"
	"time"

	"golang.org/x/oauth2"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpoauth"
)

// claudeCredsFile is the subset of ~/.claude/.credentials.json we read for MCP
// server tokens. Claude stores tokens for MCP servers the user has authorized
// (e.g. figma) under mcpOAuth, keyed by an opaque id; we match by serverUrl.
// Reusing these lets a server connected in Claude work in SyftHub with no extra
// authorization — the same host-only-token trust split the egress broker
// already uses for claudeAiOauth. Read-only: SyftHub never writes this file.
type claudeCredsFile struct {
	MCPOAuth map[string]struct {
		ServerURL   string `json:"serverUrl"`
		AccessToken string `json:"accessToken"`
		ExpiresAt   int64  `json:"expiresAt"` // epoch milliseconds
	} `json:"mcpOAuth"`
}

// claudeCredsReader parses the Claude credentials file, re-reading it only
// when its mtime/size changes — server listings consult it once per OAuth
// server, and the bytes rarely change between checks.
type claudeCredsReader struct {
	path string

	mu      sync.Mutex
	cached  claudeCredsFile
	modTime time.Time
	size    int64
	has     bool
}

func newClaudeCredsReader(path string) *claudeCredsReader {
	return &claudeCredsReader{path: path}
}

// load returns the parsed credentials, or a zero value when the file does not
// exist (a host without Claude is not an error).
func (r *claudeCredsReader) load() (claudeCredsFile, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	info, err := os.Stat(r.path)
	if err != nil {
		r.has = false
		if os.IsNotExist(err) {
			return claudeCredsFile{}, nil
		}
		return claudeCredsFile{}, err
	}
	if r.has && info.ModTime().Equal(r.modTime) && info.Size() == r.size {
		return r.cached, nil
	}

	data, err := os.ReadFile(r.path)
	if err != nil {
		r.has = false
		if os.IsNotExist(err) {
			return claudeCredsFile{}, nil
		}
		return claudeCredsFile{}, err
	}
	var f claudeCredsFile
	if err := json.Unmarshal(data, &f); err != nil {
		r.has = false
		return claudeCredsFile{}, fmt.Errorf("parse claude credentials: %w", err)
	}
	r.cached, r.modTime, r.size, r.has = f, info.ModTime(), info.Size(), true
	return f, nil
}

// mcpToken returns the access token Claude holds for serverURL, or
// (nil, false) when none is stored.
func (r *claudeCredsReader) mcpToken(serverURL string) (*oauth2.Token, bool, error) {
	f, err := r.load()
	if err != nil {
		return nil, false, err
	}
	for _, e := range f.MCPOAuth {
		if e.ServerURL == serverURL && e.AccessToken != "" {
			tok := &oauth2.Token{AccessToken: e.AccessToken}
			if e.ExpiresAt > 0 {
				tok.Expiry = time.UnixMilli(e.ExpiresAt)
			}
			return tok, true, nil
		}
	}
	return nil, false, nil
}

// hasMCPToken reports whether Claude holds a currently-valid token for
// serverURL.
func (r *claudeCredsReader) hasMCPToken(serverURL string) bool {
	tok, ok, err := r.mcpToken(serverURL)
	return err == nil && ok && mcpoauth.TokenValid(tok)
}

// claudeMCPTokenSource serves the access token Claude holds for an MCP server,
// re-reading the credentials file when the cached token nears expiry. Read-only
// by design: SyftHub never refreshes (which would rotate Claude's refresh token
// out from under Claude). When the token expires, the user re-opens the server
// in Claude — or connects it directly in SyftHub for a server with open DCR.
type claudeMCPTokenSource struct {
	reader    *claudeCredsReader
	serverURL string
	mu        sync.Mutex
	cached    *oauth2.Token
}

func (s *claudeMCPTokenSource) Token() (*oauth2.Token, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if mcpoauth.TokenValid(s.cached) {
		return s.cached, nil
	}
	tok, ok, err := s.reader.mcpToken(s.serverURL)
	if err != nil {
		return nil, err
	}
	if !ok || !mcpoauth.TokenValid(tok) {
		return nil, mcpoauth.ErrReconnectRequired
	}
	s.cached = tok
	return tok, nil
}
