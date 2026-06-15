package egressbroker

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sync"
)

type credCtxKey struct{}

// credentialProxy resolves a credential per request, swaps auth headers, and
// reverse-proxies to the resolved upstream without buffering (SSE-safe).
type credentialProxy struct {
	source CredentialSource
	logger *slog.Logger
	proxy  *httputil.ReverseProxy

	// urlCache memoizes parsed upstream URLs. Resolve runs on every request and
	// the set of distinct upstreams is tiny (a few constant provider bases), so
	// caching avoids re-parsing the same string on the per-request hot path.
	// SetURL only reads its target, so sharing a *url.URL across requests is safe.
	mu       sync.RWMutex
	urlCache map[string]*url.URL
}

// upstreamURL returns the parsed upstream, parsing+caching on first sight.
func (cp *credentialProxy) upstreamURL(raw string) (*url.URL, error) {
	cp.mu.RLock()
	u, ok := cp.urlCache[raw]
	cp.mu.RUnlock()
	if ok {
		return u, nil
	}
	u, err := url.Parse(raw)
	if err != nil {
		return nil, err
	}
	cp.mu.Lock()
	if cp.urlCache == nil {
		cp.urlCache = make(map[string]*url.URL)
	}
	cp.urlCache[raw] = u
	cp.mu.Unlock()
	return u, nil
}

// NewCredentialProxy builds an http.Handler that, for each request, resolves a
// credential via src, strips any inbound Authorization / X-Api-Key, injects the
// resolved auth header, and reverse-proxies to the resolved upstream. The
// incoming request path is appended to the upstream base. Streaming responses
// (SSE) are flushed immediately.
//
// This is the broker's default LLM route, and is reused by the host to broker
// any HTTP upstream behind a Route (e.g. an HTTP MCP server whose PAT must stay
// on the host) — pair it with a StaticHeaderSource.
func NewCredentialProxy(src CredentialSource, logger *slog.Logger) http.Handler {
	if logger == nil {
		logger = slog.Default()
	}
	cp := &credentialProxy{source: src, logger: logger}
	cp.proxy = &httputil.ReverseProxy{
		// FlushInterval < 0 flushes writes immediately — required so streamed
		// (SSE) responses reach the caller token-by-token.
		FlushInterval: -1,
		Rewrite: func(pr *httputil.ProxyRequest) {
			cred := pr.In.Context().Value(credCtxKey{}).(Credential)
			target, err := cp.upstreamURL(cred.Upstream)
			if err != nil {
				// Resolve already validated Upstream; treat a parse failure as a
				// routing error by leaving the request unroutable.
				return
			}
			pr.SetURL(target)         // scheme+host, and prefixes target.Path
			pr.Out.Host = target.Host // present the upstream's Host header
			// Swap auth: drop whatever sentinel the caller sent, inject real.
			pr.Out.Header.Del("Authorization")
			pr.Out.Header.Del("X-Api-Key")
			for name, value := range cred.Headers {
				if name != "" && value != "" {
					pr.Out.Header.Set(name, value)
				}
			}
		},
		ErrorHandler: func(w http.ResponseWriter, _ *http.Request, err error) {
			cp.logger.Warn("egress broker upstream error", "error", err)
			http.Error(w, "egress upstream error", http.StatusBadGateway)
		},
	}
	return cp
}

func (cp *credentialProxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	cred, err := cp.source.Resolve(r)
	if err != nil {
		switch {
		case errors.Is(err, ErrCredentialExpired):
			http.Error(w, "egress credential expired — re-authenticate on the host (e.g. `claude` login / `claude setup-token`)", http.StatusUnauthorized)
		case errors.Is(err, ErrNoCredential):
			http.Error(w, "no egress credential configured for this endpoint — set it in the host", http.StatusBadGateway)
		default:
			cp.logger.Warn("egress broker resolve failed", "error", err)
			http.Error(w, "egress credential unavailable", http.StatusBadGateway)
		}
		return
	}
	cp.proxy.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), credCtxKey{}, cred)))
}
