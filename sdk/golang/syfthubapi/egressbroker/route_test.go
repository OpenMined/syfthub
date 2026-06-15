package egressbroker

import (
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

// TestBrokerRoutesByPrefix verifies a request matching a Route prefix is served
// by that route, while everything else falls through to the LLM credential
// proxy.
func TestBrokerRoutesByPrefix(t *testing.T) {
	mcpUp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, "mcp:"+r.URL.Path+":"+r.Header.Get("Authorization"))
	}))
	defer mcpUp.Close()
	llmUp := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = io.WriteString(w, "llm:"+r.Header.Get("Authorization"))
	}))
	defer llmUp.Close()

	// The MCP route (no trailing slash) brokers the PAT host-side; the broker
	// strips the prefix before dispatching.
	mcpRoute := Route{
		Prefix: "/mcp/github",
		Handler: NewCredentialProxy(
			StaticHeaderSource{Upstream: mcpUp.URL, Headers: map[string]string{"Authorization": "Bearer PAT"}}, nil),
	}

	sock := filepath.Join(t.TempDir(), "e.sock")
	b := New(nil)
	defer b.Stop()
	if err := b.Add(EndpointEgress{
		Slug:       "e",
		SocketPath: sock,
		Source:     fixedSource{cred: Credential{Upstream: llmUp.URL, Headers: map[string]string{"Authorization": "Bearer LLMKEY"}}},
		Routes:     []Route{mcpRoute},
	}); err != nil {
		t.Fatalf("Add: %v", err)
	}
	client := unixClient(sock)

	// MCP sub-path → MCP upstream, with the PAT injected host-side.
	resp, err := client.Get("http://broker/mcp/github/tools")
	if err != nil {
		t.Fatalf("mcp request: %v", err)
	}
	got, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if want := "mcp:/tools:Bearer PAT"; string(got) != want {
		t.Errorf("mcp route body = %q, want %q", got, want)
	}

	// Bare endpoint URL (no trailing slash) — the path MCP clients actually
	// POST to — must still route to the MCP upstream, not fall through.
	resp, err = client.Get("http://broker/mcp/github")
	if err != nil {
		t.Fatalf("bare mcp request: %v", err)
	}
	got, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if want := "mcp:/:Bearer PAT"; string(got) != want {
		t.Errorf("bare mcp route body = %q, want %q (must not hit LLM fallback)", got, want)
	}

	// A different server whose name shares a prefix must NOT match (boundary).
	resp, err = client.Get("http://broker/mcp/github-enterprise")
	if err != nil {
		t.Fatalf("prefix-sibling request: %v", err)
	}
	got, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if want := "llm:Bearer LLMKEY"; string(got) != want {
		t.Errorf("prefix-sibling body = %q, want LLM fallback %q", got, want)
	}

	// Non-MCP path → falls through to the LLM credential proxy.
	resp, err = client.Get("http://broker/v1/messages")
	if err != nil {
		t.Fatalf("llm request: %v", err)
	}
	got, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if want := "llm:Bearer LLMKEY"; string(got) != want {
		t.Errorf("llm fallback body = %q, want %q", got, want)
	}
}

// TestBrokerLongestPrefixWins verifies overlapping route prefixes resolve to the
// most specific one.
func TestBrokerLongestPrefixWins(t *testing.T) {
	short := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "short")
	}))
	defer short.Close()
	long := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = io.WriteString(w, "long")
	}))
	defer long.Close()

	sock := filepath.Join(t.TempDir(), "e.sock")
	b := New(nil)
	defer b.Stop()
	if err := b.Add(EndpointEgress{
		Slug:       "e",
		SocketPath: sock,
		Source:     fixedSource{cred: Credential{Upstream: short.URL, Headers: map[string]string{"Authorization": "x"}}},
		Routes: []Route{
			{Prefix: "/mcp", Handler: NewCredentialProxy(StaticHeaderSource{Upstream: short.URL}, nil)},
			{Prefix: "/mcp/playwright", Handler: NewCredentialProxy(StaticHeaderSource{Upstream: long.URL}, nil)},
		},
	}); err != nil {
		t.Fatalf("Add: %v", err)
	}

	resp, err := unixClient(sock).Get("http://broker/mcp/playwright/x")
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	got, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if string(got) != "long" {
		t.Errorf("longest-prefix routing = %q, want long", got)
	}
}

func TestStaticHeaderSource(t *testing.T) {
	s := StaticHeaderSource{
		Upstream: "https://api.example.com/mcp",
		Headers:  map[string]string{"Authorization": "Bearer PAT", "X-Org": "acme"},
	}
	c, err := s.Resolve(nil)
	if err != nil {
		t.Fatalf("Resolve: %v", err)
	}
	if c.Upstream != "https://api.example.com/mcp" || c.Headers["Authorization"] != "Bearer PAT" || c.Headers["X-Org"] != "acme" {
		t.Errorf("credential = %+v", c)
	}
	// Empty upstream ⇒ not configured.
	if _, err := (StaticHeaderSource{}).Resolve(nil); err != ErrNoCredential {
		t.Errorf("empty upstream err = %v, want ErrNoCredential", err)
	}
}
