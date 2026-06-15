// Package main — host OAuth for remote MCP servers.
//
// oauthManager drives the interactive OAuth flow (browser + loopback redirect)
// for remote MCP servers that require it (e.g. figma), persists the tokens
// host-side, and serves them — auto-refreshing — to the MCP bridge. The token
// never enters the container: the bridge holds the authorized connection and
// re-exposes the server's tools on the loopback relay. See sdk/.../mcpoauth.
package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"time"

	"github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpoauth"
)

// openBrowser opens url in the user's default browser via the Wails runtime.
// Used as the oauthManager's browser opener.
func (a *App) openBrowser(url string) {
	if a.ctx != nil {
		runtime.BrowserOpenURL(a.ctx, url)
	}
}

// oauthConnectTimeout bounds how long we wait for the user to complete the
// browser authorization before giving up.
const oauthConnectTimeout = 5 * time.Minute

const oauthClientName = "SyftHub Desktop"

// oauthManager owns the per-server OAuth token store and the interactive
// connect flow. open is the browser opener (Wails runtime), injected so the
// flow is testable without a GUI. claude reads ~/.claude/.credentials.json —
// servers the user has already authorized in Claude are reused from there
// (e.g. figma, whose authorization server gates dynamic client registration
// to Claude).
type oauthManager struct {
	store  *mcpoauth.FileStore
	open   func(url string)
	claude *claudeCredsReader
	logger *slog.Logger
}

func newOAuthManager(dir, claudeCreds string, open func(url string), logger *slog.Logger) *oauthManager {
	if logger == nil {
		logger = slog.Default()
	}
	return &oauthManager{
		store:  mcpoauth.NewFileStore(dir),
		open:   open,
		claude: newClaudeCredsReader(claudeCreds),
		logger: logger,
	}
}

// Connect runs the interactive OAuth flow for a remote MCP server: it stands up
// a loopback redirect server, opens the browser to the authorization URL, and
// captures the returned code. On success the server's tokens are persisted and
// it is ready to broker. Blocks until the user finishes, the context is
// canceled, or the timeout elapses.
func (m *oauthManager) Connect(ctx context.Context, server, serverURL string) error {
	ctx, cancel := context.WithTimeout(ctx, oauthConnectTimeout)
	defer cancel()

	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("oauth: start loopback redirect: %w", err)
	}
	port := ln.Addr().(*net.TCPAddr).Port
	redirectURL := fmt.Sprintf("http://127.0.0.1:%d/callback", port)

	type callback struct {
		code, state string
	}
	cbCh := make(chan callback, 1)
	srv := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/callback" {
			http.NotFound(w, r)
			return
		}
		q := r.URL.Query()
		if e := q.Get("error"); e != "" {
			http.Error(w, "authorization denied: "+e, http.StatusBadRequest)
			select {
			case cbCh <- callback{}:
			default:
			}
			return
		}
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(oauthDoneHTML))
		select {
		case cbCh <- callback{code: q.Get("code"), state: q.Get("state")}:
		default:
		}
	})}
	go func() { _ = srv.Serve(ln) }()
	defer func() {
		shutCtx, c := context.WithTimeout(context.Background(), 2*time.Second)
		defer c()
		_ = srv.Shutdown(shutCtx)
	}()

	fetch := func(ctx context.Context, authURL, state string) (string, error) {
		if m.open != nil {
			m.open(authURL)
		}
		select {
		case cb := <-cbCh:
			if cb.code == "" {
				return "", fmt.Errorf("authorization was denied or returned no code")
			}
			if cb.state != state {
				return "", fmt.Errorf("authorization state mismatch (possible CSRF)")
			}
			return cb.code, nil
		case <-ctx.Done():
			return "", ctx.Err()
		}
	}

	_, err = mcpoauth.Connect(ctx, mcpoauth.ConnectParams{
		Server:      server,
		ServerURL:   serverURL,
		RedirectURL: redirectURL,
		ClientName:  oauthClientName,
		Fetch:       fetch,
		Store:       m.store,
	})
	if err != nil {
		return err
	}
	m.logger.Info("mcp oauth: server connected", "server", server)
	return nil
}

// preferClaude reports whether serverURL should be served from a token Claude
// already holds instead of our own stored token: our token is unusable (absent,
// or expired with no refresh) AND Claude has a usable one. Centralizing the
// rule keeps Handler and Status from disagreeing about what "connected" means —
// e.g. a dead-but-present stored token must not shadow a valid Claude token.
func (m *oauthManager) preferClaude(server, serverURL string) bool {
	st, err := mcpoauth.ServerStatus(m.store, server)
	if err != nil {
		return false
	}
	return st != mcpoauth.StatusConnected && m.claudeHasToken(serverURL)
}

// Handler returns the non-interactive auth.OAuthHandler for the bridge. It
// serves a token Claude holds for serverURL whenever our own stored token is
// unusable (so an expired/dead stored token can't shadow a valid Claude one);
// otherwise it uses the stored token, which refreshes itself on demand. Returns
// mcpoauth.ErrNotConnected when neither a usable stored nor Claude token exists.
func (m *oauthManager) Handler(ctx context.Context, server, serverURL string) (auth.OAuthHandler, error) {
	if m.preferClaude(server, serverURL) {
		return mcpoauth.NewHandler(&claudeMCPTokenSource{reader: m.claude, serverURL: serverURL}), nil
	}
	return mcpoauth.Handler(ctx, m.store, server, nil)
}

// Status reports a server's authorization state ("not_connected" | "connected"
// | "expired"), counting a token Claude holds for serverURL as connected — even
// when our own stored token is present but expired.
func (m *oauthManager) Status(server, serverURL string) (string, error) {
	st, err := mcpoauth.ServerStatus(m.store, server)
	if err != nil {
		return string(st), err
	}
	if st != mcpoauth.StatusConnected && m.claudeHasToken(serverURL) {
		return string(mcpoauth.StatusConnected), nil
	}
	return string(st), nil
}

// Disconnect clears a server's SyftHub-stored tokens. (Tokens that live in
// Claude's store are not touched.)
func (m *oauthManager) Disconnect(server string) error {
	return m.store.Delete(server)
}

// claudeHasToken reports whether Claude holds a valid token for serverURL.
func (m *oauthManager) claudeHasToken(serverURL string) bool {
	return m.claude.hasMCPToken(serverURL)
}

const oauthDoneHTML = `<!doctype html><html><head><meta charset="utf-8">
<title>SyftHub Desktop</title></head>
<body style="font-family:system-ui;background:#1a1625;color:#eee;display:flex;
height:100vh;align-items:center;justify-content:center;margin:0">
<div style="text-align:center">
<h2>Authorization complete</h2>
<p>You can close this tab and return to SyftHub Desktop.</p>
</div></body></html>`
