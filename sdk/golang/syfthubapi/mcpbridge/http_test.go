package mcpbridge

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"golang.org/x/oauth2"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// staticOAuthHandler is a minimal auth.OAuthHandler that always presents a fixed
// bearer (no interactive flow) — the shape the desktop's stored handler takes.
type staticOAuthHandler struct{ token string }

func (h staticOAuthHandler) TokenSource(context.Context) (oauth2.TokenSource, error) {
	return oauth2.StaticTokenSource(&oauth2.Token{AccessToken: h.token}), nil
}
func (h staticOAuthHandler) Authorize(context.Context, *http.Request, *http.Response) error {
	return context.Canceled // non-interactive: cannot re-auth here
}

var _ auth.OAuthHandler = staticOAuthHandler{}

// bearerGuardedMCP wraps a streamable MCP handler, rejecting requests without
// the expected bearer (like a remote OAuth MCP server would).
func bearerGuardedMCP(t *testing.T, want string) http.Handler {
	t.Helper()
	srv := mcp.NewServer(&mcp.Implementation{Name: "remote", Version: "1.0.0"}, nil)
	srv.AddTool(&mcp.Tool{Name: "ping", Description: "pong", InputSchema: map[string]any{"type": "object"}},
		func(context.Context, *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: "pong"}}}, nil
		})
	inner := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return srv },
		&mcp.StreamableHTTPOptions{Stateless: true, JSONResponse: true})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+want {
			w.Header().Set("WWW-Authenticate", `Bearer realm="remote"`)
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		inner.ServeHTTP(w, r)
	})
}

func TestNewHTTPBridgeAttachesBearer(t *testing.T) {
	remote := httptest.NewServer(bearerGuardedMCP(t, "secret-token"))
	defer remote.Close()

	b, err := NewHTTP("remote", remote.URL, staticOAuthHandler{token: "secret-token"}, nil)
	if err != nil {
		t.Fatalf("NewHTTP: %v", err)
	}
	if err := b.Start(context.Background()); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer b.Close()

	// The bridge re-exposes the remote's tools locally.
	ts := httptest.NewServer(b.Handler())
	defer ts.Close()
	cs := connectClient(t, ts.URL)
	res, err := cs.CallTool(context.Background(), &mcp.CallToolParams{Name: "ping"})
	if err != nil {
		t.Fatalf("call: %v", err)
	}
	if tc, ok := res.Content[0].(*mcp.TextContent); !ok || tc.Text != "pong" {
		t.Errorf("result = %+v, want pong", res.Content)
	}
}

func TestNewHTTPBridgeFailsWithoutToken(t *testing.T) {
	remote := httptest.NewServer(bearerGuardedMCP(t, "secret-token"))
	defer remote.Close()

	// Wrong token → upstream 401 → handler.Authorize can't fix it → Start fails.
	b, err := NewHTTP("remote", remote.URL, staticOAuthHandler{token: "wrong"}, nil)
	if err != nil {
		t.Fatalf("NewHTTP: %v", err)
	}
	if err := b.Start(context.Background()); err == nil {
		_ = b.Close()
		t.Fatal("expected Start to fail against an unauthorized upstream")
	}
}

func TestNewHTTPRejectsEmptyURL(t *testing.T) {
	if _, err := NewHTTP("x", "", nil, nil); err == nil {
		t.Error("expected error for empty url")
	}
}

func connectClient(t *testing.T, url string) *mcp.ClientSession {
	t.Helper()
	c := mcp.NewClient(&mcp.Implementation{Name: "container", Version: "1.0.0"}, nil)
	cs, err := c.Connect(context.Background(), &mcp.StreamableClientTransport{Endpoint: url}, nil)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(func() { _ = cs.Close() })
	return cs
}
