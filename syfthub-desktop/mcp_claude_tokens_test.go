package main

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

func writeClaudeCreds(t *testing.T, dir, serverURL, token string, expiresAt int64) string {
	t.Helper()
	path := filepath.Join(dir, ".credentials.json")
	body := `{
	  "claudeAiOauth": {"accessToken": "x"},
	  "mcpOAuth": {
	    "plugin:figma:figma|abc": {
	      "serverName": "plugin:figma:figma",
	      "serverUrl": "` + serverURL + `",
	      "accessToken": "` + token + `",
	      "clientId": "c", "clientSecret": "s", "refreshToken": "r",
	      "expiresAt": ` + strconv.FormatInt(expiresAt, 10) + `
	    }
	  }
	}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestReadClaudeMCPToken(t *testing.T) {
	dir := t.TempDir()
	future := time.Now().Add(90 * 24 * time.Hour).UnixMilli()
	path := writeClaudeCreds(t, dir, "https://mcp.figma.com/mcp", "figma-access", future)

	tok, ok, err := newClaudeCredsReader(path).mcpToken("https://mcp.figma.com/mcp")
	if err != nil || !ok {
		t.Fatalf("read: ok=%v err=%v", ok, err)
	}
	if tok.AccessToken != "figma-access" {
		t.Errorf("token = %q", tok.AccessToken)
	}

	// A different server URL is not matched.
	if _, ok, _ := newClaudeCredsReader(path).mcpToken("https://other/mcp"); ok {
		t.Error("unexpected match for a different server URL")
	}
	// Missing file → no match, no error.
	if _, ok, err := newClaudeCredsReader(filepath.Join(dir, "nope.json")).mcpToken("x"); ok || err != nil {
		t.Errorf("missing file: ok=%v err=%v", ok, err)
	}
}

func TestOAuthManagerReusesClaudeToken(t *testing.T) {
	dir := t.TempDir()
	future := time.Now().Add(90 * 24 * time.Hour).UnixMilli()
	claudePath := writeClaudeCreds(t, dir, "https://mcp.figma.com/mcp", "figma-access", future)

	// oauthManager with an empty own-store but a Claude file holding figma.
	m := newOAuthManager(filepath.Join(dir, "oauth"), claudePath, func(string) {}, nil)

	if !m.claudeHasToken("https://mcp.figma.com/mcp") {
		t.Fatal("claudeHasToken = false, want true")
	}
	if st, _ := m.Status("figma", "https://mcp.figma.com/mcp"); st != "connected" {
		t.Errorf("status = %q, want connected (via Claude)", st)
	}
	// Handler falls back to Claude's token.
	h, err := m.Handler(context.Background(), "figma", "https://mcp.figma.com/mcp")
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	ts, _ := h.TokenSource(context.Background())
	tok, err := ts.Token()
	if err != nil || tok.AccessToken != "figma-access" {
		t.Errorf("token = %+v err=%v, want figma-access", tok, err)
	}

	// An expired Claude token is treated as not connected.
	past := time.Now().Add(-time.Hour).UnixMilli()
	_ = writeClaudeCreds(t, dir, "https://mcp.figma.com/mcp", "old", past)
	if m.claudeHasToken("https://mcp.figma.com/mcp") {
		t.Error("expired Claude token counted as valid")
	}
	if st, _ := m.Status("figma", "https://mcp.figma.com/mcp"); st != "not_connected" {
		t.Errorf("status with expired token = %q, want not_connected", st)
	}
}
