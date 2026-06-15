package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"golang.org/x/oauth2"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpoauth"
)

// minimal fake OAuth AS + MCP resource server for the loopback-wiring test.
// (The OAuth protocol itself is covered in mcpoauth; here we exercise
// oauthManager's loopback redirect capture + browser-open seam.)
func fakeOAuthServers(t *testing.T) (resourceURL string) {
	t.Helper()
	var as, res *httptest.Server
	var mu sync.Mutex
	codes := map[string]string{} // code -> challenge

	asMux := http.NewServeMux()
	asMux.HandleFunc("/.well-known/oauth-authorization-server", func(w http.ResponseWriter, r *http.Request) {
		writeJSONt(w, map[string]any{
			"issuer":                           as.URL,
			"authorization_endpoint":           as.URL + "/authorize",
			"token_endpoint":                   as.URL + "/token",
			"registration_endpoint":            as.URL + "/register",
			"response_types_supported":         []string{"code"},
			"code_challenge_methods_supported": []string{"S256"},
			"scopes_supported":                 []string{"mcp:connect"},
		})
	})
	asMux.HandleFunc("/register", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		writeJSONt(w, map[string]any{"client_id": "c1"})
	})
	asMux.HandleFunc("/authorize", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		code := "code-1"
		mu.Lock()
		codes[code] = q.Get("code_challenge")
		mu.Unlock()
		redir, _ := url.Parse(q.Get("redirect_uri"))
		rq := redir.Query()
		rq.Set("code", code)
		rq.Set("state", q.Get("state"))
		redir.RawQuery = rq.Encode()
		http.Redirect(w, r, redir.String(), http.StatusFound)
	})
	asMux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		mu.Lock()
		ch := codes[r.Form.Get("code")]
		mu.Unlock()
		sum := sha256.Sum256([]byte(r.Form.Get("code_verifier")))
		if base64.RawURLEncoding.EncodeToString(sum[:]) != ch {
			http.Error(w, "pkce", http.StatusBadRequest)
			return
		}
		writeJSONt(w, map[string]any{"access_token": "tok-1", "token_type": "Bearer", "refresh_token": "r1", "expires_in": 3600})
	})
	as = httptest.NewServer(asMux)
	t.Cleanup(as.Close)

	resMux := http.NewServeMux()
	resMux.HandleFunc("/.well-known/oauth-protected-resource", func(w http.ResponseWriter, r *http.Request) {
		writeJSONt(w, map[string]any{"resource": res.URL + "/mcp", "authorization_servers": []string{as.URL}, "scopes_supported": []string{"mcp:connect"}})
	})
	resMux.HandleFunc("/mcp", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") == "" {
			w.Header().Set("WWW-Authenticate", `Bearer resource_metadata="`+res.URL+`/.well-known/oauth-protected-resource"`)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		writeJSONt(w, map[string]any{"ok": true})
	})
	res = httptest.NewServer(resMux)
	t.Cleanup(res.Close)
	return res.URL + "/mcp"
}

func TestOAuthManagerConnectViaLoopback(t *testing.T) {
	resourceURL := fakeOAuthServers(t)

	// "Browser": follow the authorize redirect, which lands on oauthManager's
	// loopback /callback and delivers the code.
	open := func(u string) { go func() { _, _ = http.Get(u) }() }
	m := newOAuthManager(t.TempDir(), filepath.Join(t.TempDir(), "no-claude.json"), open, nil)

	if st, _ := m.Status("figma", resourceURL); st != "not_connected" {
		t.Fatalf("initial status = %q", st)
	}
	if err := m.Connect(context.Background(), "figma", resourceURL); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if st, _ := m.Status("figma", resourceURL); st != "connected" {
		t.Errorf("post-connect status = %q, want connected", st)
	}
	// The bridge handler can now produce a token source.
	h, err := m.Handler(context.Background(), "figma", resourceURL)
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	ts, _ := h.TokenSource(context.Background())
	tok, err := ts.Token()
	if err != nil || tok.AccessToken != "tok-1" {
		t.Errorf("token = %+v, err=%v", tok, err)
	}

	if err := m.Disconnect("figma"); err != nil {
		t.Fatalf("Disconnect: %v", err)
	}
	if st, _ := m.Status("figma", resourceURL); st != "not_connected" {
		t.Errorf("post-disconnect status = %q", st)
	}
}

// TestOAuthManagerPrefersClaudeWhenStoredTokenExpired guards the rule that a
// dead-but-present stored token must not shadow a valid token Claude holds for
// the same server: both Status and Handler fall back to Claude.
func TestOAuthManagerPrefersClaudeWhenStoredTokenExpired(t *testing.T) {
	const server = "figma"
	const serverURL = "https://mcp.figma.com/mcp"

	// Claude holds a valid (far-future) token for the same server URL.
	future := time.Now().Add(90 * 24 * time.Hour).UnixMilli()
	credsPath := writeClaudeCreds(t, t.TempDir(), serverURL, "claude-tok", future)
	m := newOAuthManager(t.TempDir(), credsPath, func(string) {}, nil)

	// Our own stored token is present but expired with no refresh token →
	// mcpoauth.ServerStatus reports "expired".
	expired := &mcpoauth.Record{Token: &oauth2.Token{AccessToken: "dead", Expiry: time.Now().Add(-time.Hour)}}
	if err := m.store.Save(server, expired); err != nil {
		t.Fatalf("seed store: %v", err)
	}

	// Status reports connected via Claude, not the dead stored token.
	if st, _ := m.Status(server, serverURL); st != "connected" {
		t.Errorf("Status = %q, want connected (via Claude)", st)
	}
	// Handler serves Claude's token rather than failing on the dead stored one.
	h, err := m.Handler(context.Background(), server, serverURL)
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	ts, _ := h.TokenSource(context.Background())
	if tok, err := ts.Token(); err != nil || tok.AccessToken != "claude-tok" {
		t.Errorf("token = %+v, err=%v; want claude-tok", tok, err)
	}

	// Without a Claude token, an expired stored token stays "expired" (no false
	// "connected").
	m2 := newOAuthManager(t.TempDir(), filepath.Join(t.TempDir(), "absent.json"), func(string) {}, nil)
	if err := m2.store.Save(server, expired); err != nil {
		t.Fatalf("seed store2: %v", err)
	}
	if st, _ := m2.Status(server, serverURL); st != "expired" {
		t.Errorf("Status without Claude = %q, want expired", st)
	}
}

func writeJSONt(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
