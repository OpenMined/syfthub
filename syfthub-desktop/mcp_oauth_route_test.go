package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"golang.org/x/oauth2"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// fakeOAuthProvider returns a static-bearer handler — the shape mcpHost gets
// from oauthManager for a connected server, without the real OAuth flow.
type fakeOAuthProvider struct {
	token string
	err   error
}

func (p fakeOAuthProvider) Handler(context.Context, string, string) (auth.OAuthHandler, error) {
	if p.err != nil {
		return nil, p.err
	}
	return staticBearer{token: p.token}, nil
}

type staticBearer struct{ token string }

func (h staticBearer) TokenSource(context.Context) (oauth2.TokenSource, error) {
	return oauth2.StaticTokenSource(&oauth2.Token{AccessToken: h.token}), nil
}
func (h staticBearer) Authorize(context.Context, *http.Request, *http.Response) error {
	return context.Canceled
}

// bearerMCP is a streamable MCP server that requires a specific bearer.
func bearerMCP(t *testing.T, want string) http.Handler {
	t.Helper()
	srv := mcp.NewServer(&mcp.Implementation{Name: "figma", Version: "1.0.0"}, nil)
	srv.AddTool(&mcp.Tool{Name: "whoami", Description: "id", InputSchema: map[string]any{"type": "object"}},
		func(context.Context, *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: "me"}}}, nil
		})
	inner := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+want {
			w.Header().Set("WWW-Authenticate", `Bearer realm="figma"`)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		inner.ServeHTTP(w, r)
	})
}

// TestMCPHostRoutesOAuthServerThroughBridge: an http server with auth=oauth is
// wired via a bridge that attaches the host-held token — the container never
// supplies it.
func TestMCPHostRoutesOAuthServerThroughBridge(t *testing.T) {
	remote := httptest.NewServer(bearerMCP(t, "figma-token"))
	defer remote.Close()

	reg := newMCPRegistry(t.TempDir())
	if err := reg.upsert(mcpServerDef{
		Name: "figma", Transport: mcpTransportHTTP, URL: remote.URL,
		Auth: mcpAuthOAuth, Enabled: true,
	}); err != nil {
		t.Fatal(err)
	}
	host := newMCPHost(reg, fakeOAuthProvider{token: "figma-token"}, nil)
	defer host.Stop()

	routes, wired := host.Routes("ep", []string{"figma"})
	if len(wired) != 1 || wired[0] != "figma" {
		t.Fatalf("wired = %v, want [figma]", wired)
	}
	if len(routes) != 1 || routes[0].Prefix != "/mcp/figma" {
		t.Fatalf("routes = %+v", routes)
	}

	// Drive it as a container would (no auth header) → bridge re-exposes the
	// remote tool, attaching the host token. The broker strips the route
	// prefix before dispatching, so the handler is mounted at "/".
	ts := httptest.NewServer(routes[0].Handler)
	defer ts.Close()
	cs := connectMCP(t, ts.URL)
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "whoami"})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if tc, ok := res.Content[0].(*mcp.TextContent); !ok || tc.Text != "me" {
		t.Errorf("result = %+v, want me", res.Content)
	}
}

// TestMCPHostSkipsUnconnectedOAuthServer: an OAuth server with no stored token
// (provider errors) is skipped — not wired — rather than failing the endpoint.
func TestMCPHostSkipsUnconnectedOAuthServer(t *testing.T) {
	reg := newMCPRegistry(t.TempDir())
	_ = reg.upsert(mcpServerDef{Name: "figma", Transport: mcpTransportHTTP, URL: "https://mcp.figma.com/mcp", Auth: mcpAuthOAuth, Enabled: true})
	host := newMCPHost(reg, fakeOAuthProvider{err: context.Canceled}, nil)
	defer host.Stop()

	_, wired := host.Routes("ep", []string{"figma"})
	if len(wired) != 0 {
		t.Errorf("wired = %v, want empty (unconnected oauth server skipped)", wired)
	}
}

func connectMCP(t *testing.T, url string) *mcp.ClientSession {
	t.Helper()
	c := mcp.NewClient(&mcp.Implementation{Name: "container", Version: "1.0.0"}, nil)
	cs, err := c.Connect(context.Background(), &mcp.StreamableClientTransport{Endpoint: url}, nil)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })
	return cs
}
