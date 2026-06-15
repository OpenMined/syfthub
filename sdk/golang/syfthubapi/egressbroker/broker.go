// Package egressbroker is the host side of the credential-broker / egress-proxy
// pattern. A container-mode endpoint never holds its real LLM credential;
// instead it sends a sentinel/redacted credential to a per-endpoint AF_UNIX
// socket, and this broker swaps in the real credential (held only on the host)
// and forwards the request to the pinned upstream. It is the container's only
// egress path.
//
// The broker is a transparent streaming reverse proxy: it rewrites the
// Authorization header and the upstream host, preserves everything else
// (anthropic-version, anthropic-beta, content-type, body), and streams the
// response back without buffering (SSE-safe).
//
// This mirrors the trust split already used for the wallet key by mppxgate:
// the host holds the secret, the container never does.
package egressbroker

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Credential is what a CredentialSource resolves to for a single request: the
// pinned upstream base URL and the auth headers to inject.
type Credential struct {
	// Upstream is the scheme+host(+base path) the request is forwarded to,
	// e.g. "https://api.anthropic.com" (claude adds /v1/messages itself) or
	// "https://api.anthropic.com/v1" (basic-agent adds /chat/completions).
	// The incoming request path is appended to this base.
	Upstream string
	// Headers are the auth headers injected after stripping any inbound
	// Authorization / x-api-key — typically just "Authorization: Bearer …",
	// but an upstream may need several (e.g. a PAT plus a tenant header).
	// Entries with an empty value are skipped.
	Headers map[string]string
}

// CredentialSource resolves the real credential for a request. Resolve is
// called once per request (it receives the request so a source can route on the
// path, and so live re-reads / expiry checks take effect immediately).
type CredentialSource interface {
	Resolve(r *http.Request) (Credential, error)
}

// Typed errors a CredentialSource may return; the broker maps them to HTTP
// status codes the runner/agent can surface.
var (
	ErrNoCredential      = errors.New("egressbroker: no credential configured")
	ErrCredentialExpired = errors.New("egressbroker: credential expired")
)

// Route mounts an http.Handler under a path prefix on an endpoint's socket,
// matched ahead of the default credential-swap proxy. Matching is at a path
// segment boundary: a Route with Prefix "/mcp/x" handles exactly "/mcp/x" and
// anything under "/mcp/x/…", but not "/mcp/xy". Prefixes therefore must NOT
// carry a trailing slash. Longest matching prefix wins. The broker strips the
// matched prefix before dispatching, normalizing the remainder to start with
// "/" (a request to the bare prefix arrives as "/"), so handlers always see a
// rooted path and need no http.StripPrefix of their own. Used to broker
// non-LLM upstreams (e.g. MCP tool servers, whose clients POST to the bare
// endpoint URL /mcp/<name>).
type Route struct {
	Prefix  string
	Handler http.Handler
}

// EndpointEgress describes one endpoint's broker binding.
type EndpointEgress struct {
	Slug       string
	SocketPath string // AF_UNIX path; created fresh (stale file removed) on Add
	Source     CredentialSource
	// Routes are optional prefix-matched handlers tried before the default LLM
	// credential-swap proxy. A request matching no route falls through to
	// Source. nil Routes ⇒ LLM-only (the original behavior).
	Routes []Route
}

// Broker owns one AF_UNIX listener + reverse proxy per registered endpoint.
type Broker struct {
	logger *slog.Logger
	mu     sync.Mutex
	eps    map[string]*endpointProxy
}

// New returns an empty Broker. Register endpoints with Add and tear everything
// down with Stop.
func New(logger *slog.Logger) *Broker {
	if logger == nil {
		logger = slog.Default()
	}
	return &Broker{logger: logger, eps: map[string]*endpointProxy{}}
}

// Add (re)registers an endpoint: it removes any prior binding for the same slug,
// creates the socket, and starts serving. Safe to call on reload.
func (b *Broker) Add(ep EndpointEgress) error {
	if ep.Slug == "" || ep.SocketPath == "" || ep.Source == nil {
		return fmt.Errorf("egressbroker: Add requires slug, socket path, and source")
	}
	b.mu.Lock()
	defer b.mu.Unlock()

	if prev, ok := b.eps[ep.Slug]; ok {
		prev.close()
		delete(b.eps, ep.Slug)
	}

	if err := os.MkdirAll(filepath.Dir(ep.SocketPath), 0o700); err != nil {
		return fmt.Errorf("egressbroker: create socket dir: %w", err)
	}
	// A stale socket file from a previous run blocks Listen with EADDRINUSE.
	_ = os.Remove(ep.SocketPath)

	ln, err := net.Listen("unix", ep.SocketPath)
	if err != nil {
		// The kernel sun_path limit (104 macOS / 108 Linux) surfaces as an
		// opaque "invalid argument"; call it out so the cause is obvious.
		if len(ep.SocketPath) > 104 {
			return fmt.Errorf("egressbroker: listen %q: socket path is %d bytes, over the AF_UNIX limit (~104): %w", ep.SocketPath, len(ep.SocketPath), err)
		}
		return fmt.Errorf("egressbroker: listen %q: %w", ep.SocketPath, err)
	}
	// Manage the socket file ourselves (explicit os.Remove in Add + close)
	// rather than letting the listener unlink on close. A re-Add of the same
	// slug otherwise races: the OLD listener's unlink-on-close can fire after
	// the NEW listener has recreated the file at the same path, deleting the
	// live socket. Disabling auto-unlink makes the lifecycle deterministic.
	if ul, ok := ln.(*net.UnixListener); ok {
		ul.SetUnlinkOnClose(false)
	}
	// Only the container user (same uid) should be able to use the socket.
	if err := os.Chmod(ep.SocketPath, 0o600); err != nil {
		_ = ln.Close()
		return fmt.Errorf("egressbroker: chmod socket: %w", err)
	}

	e := newEndpointProxy(ep.SocketPath, ep.Source, ep.Routes, b.logger)
	e.srv = &http.Server{Handler: e, ReadHeaderTimeout: 30 * time.Second}
	b.eps[ep.Slug] = e

	go func() {
		if err := e.srv.Serve(ln); err != nil && !errors.Is(err, http.ErrServerClosed) {
			b.logger.Warn("egress broker serve ended", "slug", ep.Slug, "error", err)
		}
	}()
	b.logger.Info("egress broker endpoint registered", "slug", ep.Slug, "socket", ep.SocketPath)
	return nil
}

// Remove tears down a single endpoint's socket + server.
func (b *Broker) Remove(slug string) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if e, ok := b.eps[slug]; ok {
		e.close()
		delete(b.eps, slug)
	}
}

// Stop tears down every endpoint. Safe to call multiple times.
func (b *Broker) Stop() {
	b.mu.Lock()
	defer b.mu.Unlock()
	for slug, e := range b.eps {
		e.close()
		delete(b.eps, slug)
	}
}

type endpointProxy struct {
	sock     string
	routes   []Route
	fallback http.Handler // default LLM credential-swap proxy
	srv      *http.Server // Shutdown also closes the listener it serves
}

func newEndpointProxy(sock string, src CredentialSource, routes []Route, logger *slog.Logger) *endpointProxy {
	return &endpointProxy{
		sock:     sock,
		routes:   routes,
		fallback: NewCredentialProxy(src, logger),
	}
}

func (e *endpointProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if rt := e.matchRoute(r.URL.Path); rt.Handler != nil {
		rt.Handler.ServeHTTP(w, stripRoutePrefix(r, rt.Prefix))
		return
	}
	e.fallback.ServeHTTP(w, r)
}

// matchRoute returns the route with the longest registered prefix matching
// path at a segment boundary; a zero Route (nil Handler) means none match and
// the caller falls through to the LLM proxy.
func (e *endpointProxy) matchRoute(path string) Route {
	var best Route
	for _, rt := range e.routes {
		if matchesPrefix(path, rt.Prefix) && len(rt.Prefix) > len(best.Prefix) {
			best = rt
		}
	}
	return best
}

// stripRoutePrefix clones r with the matched route prefix removed from the
// path, normalized so the bare prefix becomes "/" (not the empty path
// http.StripPrefix would leave, which streamable-HTTP MCP handlers reject).
func stripRoutePrefix(r *http.Request, prefix string) *http.Request {
	rest := strings.TrimPrefix(r.URL.Path, prefix)
	if rest == "" || rest[0] != '/' {
		rest = "/" + rest
	}
	r2 := r.Clone(r.Context())
	r2.URL.Path = rest
	r2.URL.RawPath = ""
	return r2
}

// matchesPrefix reports whether path is prefix itself or lies under it at a
// path-segment boundary ("/mcp/x" matches "/mcp/x" and "/mcp/x/y", not
// "/mcp/xy"). prefix must not end in "/".
func matchesPrefix(path, prefix string) bool {
	if !strings.HasPrefix(path, prefix) {
		return false
	}
	rest := path[len(prefix):]
	return rest == "" || rest[0] == '/'
}

func (e *endpointProxy) close() {
	if e.srv != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = e.srv.Shutdown(ctx)
	}
	_ = os.Remove(e.sock)
}
