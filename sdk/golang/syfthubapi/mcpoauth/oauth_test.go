package mcpoauth

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync"
	"testing"
	"time"
)

// fakeAS is a minimal OAuth 2.1 authorization server: metadata, DCR, an
// authorize endpoint that issues codes (recording the PKCE challenge), and a
// token endpoint that verifies PKCE + resource and rotates refresh tokens.
type fakeAS struct {
	srv    *httptest.Server
	mu     sync.Mutex
	codes  map[string]codeRec // code -> challenge/resource
	tokens map[string]string  // refresh_token -> "live"|"dead"
	issued int
}

type codeRec struct{ challenge, resource string }

func newFakeAS(t *testing.T) *fakeAS {
	t.Helper()
	as := &fakeAS{codes: map[string]codeRec{}, tokens: map[string]string{}}
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/oauth-authorization-server", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"issuer":                                as.srv.URL,
			"authorization_endpoint":                as.srv.URL + "/authorize",
			"token_endpoint":                        as.srv.URL + "/token",
			"registration_endpoint":                 as.srv.URL + "/register",
			"response_types_supported":              []string{"code"},
			"grant_types_supported":                 []string{"authorization_code", "refresh_token"},
			"code_challenge_methods_supported":      []string{"S256"},
			"scopes_supported":                      []string{"mcp:connect"},
			"token_endpoint_auth_methods_supported": []string{"none"},
		})
	})
	mux.HandleFunc("/register", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		writeJSON(w, map[string]any{"client_id": "dcr-client-123"})
	})
	mux.HandleFunc("/authorize", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		if q.Get("response_type") != "code" || q.Get("code_challenge") == "" ||
			q.Get("code_challenge_method") != "S256" || q.Get("resource") == "" || q.Get("state") == "" {
			http.Error(w, "bad authorize request", http.StatusBadRequest)
			return
		}
		code := fmt.Sprintf("code-%d", as.next())
		as.mu.Lock()
		as.codes[code] = codeRec{challenge: q.Get("code_challenge"), resource: q.Get("resource")}
		as.mu.Unlock()
		redirect, _ := url.Parse(q.Get("redirect_uri"))
		rq := redirect.Query()
		rq.Set("code", code)
		rq.Set("state", q.Get("state"))
		redirect.RawQuery = rq.Encode()
		http.Redirect(w, r, redirect.String(), http.StatusFound)
	})
	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		_ = r.ParseForm()
		switch r.Form.Get("grant_type") {
		case "authorization_code":
			as.mu.Lock()
			rec, ok := as.codes[r.Form.Get("code")]
			delete(as.codes, r.Form.Get("code"))
			as.mu.Unlock()
			if !ok {
				http.Error(w, "bad code", http.StatusBadRequest)
				return
			}
			if pkceS256(r.Form.Get("code_verifier")) != rec.challenge {
				http.Error(w, "pkce mismatch", http.StatusBadRequest)
				return
			}
			if r.Form.Get("resource") != rec.resource {
				http.Error(w, "resource mismatch", http.StatusBadRequest)
				return
			}
			as.issueToken(w)
		case "refresh_token":
			rt := r.Form.Get("refresh_token")
			if r.Form.Get("resource") == "" {
				http.Error(w, "missing resource on refresh", http.StatusBadRequest)
				return
			}
			as.mu.Lock()
			state := as.tokens[rt]
			as.mu.Unlock()
			if state != "live" {
				http.Error(w, "invalid_grant", http.StatusBadRequest)
				return
			}
			as.issueToken(w)
		default:
			http.Error(w, "unsupported grant", http.StatusBadRequest)
		}
	})
	as.srv = httptest.NewServer(mux)
	t.Cleanup(as.srv.Close)
	return as
}

func (as *fakeAS) next() int {
	as.mu.Lock()
	defer as.mu.Unlock()
	as.issued++
	return as.issued
}

// issueToken issues a fresh access + (rotated) refresh token, marking the old
// refresh tokens dead so rotation is observable.
func (as *fakeAS) issueToken(w http.ResponseWriter) {
	n := as.next()
	rt := fmt.Sprintf("refresh-%d", n)
	as.mu.Lock()
	for k := range as.tokens {
		as.tokens[k] = "dead"
	}
	as.tokens[rt] = "live"
	as.mu.Unlock()
	writeJSON(w, map[string]any{
		"access_token":  fmt.Sprintf("access-%d", n),
		"token_type":    "Bearer",
		"refresh_token": rt,
		"expires_in":    3600,
	})
}

// fakeResource is a minimal MCP resource server that 401s without a bearer and
// advertises its protected-resource metadata pointing at the fake AS.
func newFakeResource(t *testing.T, as *fakeAS) *httptest.Server {
	t.Helper()
	var self *httptest.Server
	mux := http.NewServeMux()
	mux.HandleFunc("/.well-known/oauth-protected-resource", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{
			"resource":              self.URL + "/mcp",
			"authorization_servers": []string{as.srv.URL},
			"scopes_supported":      []string{"mcp:connect"},
		})
	})
	mux.HandleFunc("/mcp", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") == "" {
			w.Header().Set("WWW-Authenticate",
				`Bearer resource_metadata="`+self.URL+`/.well-known/oauth-protected-resource", scope="mcp:connect"`)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		writeJSON(w, map[string]any{"jsonrpc": "2.0", "id": 1, "result": map[string]any{"ok": true}})
	})
	self = httptest.NewServer(mux)
	t.Cleanup(self.Close)
	return self
}

func TestConnectFullFlow(t *testing.T) {
	as := newFakeAS(t)
	res := newFakeResource(t, as)
	store := NewFileStore(t.TempDir())

	// Fetch simulates the browser: GET the authorize URL (no auto-redirect),
	// read the redirect, return the code.
	fetch := func(ctx context.Context, authURL, state string) (string, error) {
		noRedirect := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		}}
		resp, err := noRedirect.Get(authURL)
		if err != nil {
			return "", err
		}
		defer resp.Body.Close()
		loc, err := resp.Location()
		if err != nil {
			return "", err
		}
		if loc.Query().Get("state") != state {
			return "", fmt.Errorf("state mismatch")
		}
		return loc.Query().Get("code"), nil
	}

	rec, err := Connect(context.Background(), ConnectParams{
		Server:      "figma",
		ServerURL:   res.URL + "/mcp",
		RedirectURL: "http://127.0.0.1:0/callback",
		ClientName:  "SyftHub Desktop",
		Fetch:       fetch,
		Store:       store,
	})
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	if rec.Token.AccessToken != "access-2" { // 1=code, 2=token
		t.Errorf("access token = %q", rec.Token.AccessToken)
	}
	if rec.ClientID != "dcr-client-123" || rec.Resource != res.URL+"/mcp" {
		t.Errorf("record = %+v", rec)
	}

	// Status is connected; the token is persisted.
	if st, _ := ServerStatus(store, "figma"); st != StatusConnected {
		t.Errorf("status = %q, want connected", st)
	}

	// Build a non-interactive handler; force a refresh by expiring the token.
	h, err := Handler(context.Background(), store, "figma", nil)
	if err != nil {
		t.Fatalf("Handler: %v", err)
	}
	ts, _ := h.TokenSource(context.Background())
	tok, err := ts.Token()
	if err != nil {
		t.Fatalf("Token: %v", err)
	}
	if tok.AccessToken != "access-2" {
		t.Errorf("fresh token = %q, want access-2", tok.AccessToken)
	}

	// Expire it and re-request: the source must refresh and persist a rotated token.
	rec, _ = store.Load("figma")
	rec.Token.Expiry = time.Now().Add(-time.Hour)
	_ = store.Save("figma", rec)
	h2, _ := Handler(context.Background(), store, "figma", nil)
	ts2, _ := h2.TokenSource(context.Background())
	refreshed, err := ts2.Token()
	if err != nil {
		t.Fatalf("refresh: %v", err)
	}
	if refreshed.AccessToken == "access-2" {
		t.Errorf("token was not refreshed: %q", refreshed.AccessToken)
	}
	persisted, _ := store.Load("figma")
	if persisted.Token.AccessToken != refreshed.AccessToken {
		t.Errorf("rotated token not persisted: store=%q live=%q", persisted.Token.AccessToken, refreshed.AccessToken)
	}
}

func pkceS256(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
