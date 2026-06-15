// Package main — host MCP broker wiring.
//
// mcpHost turns an endpoint's resolved MCP-server allowlist into egress-broker
// routes. stdio servers run as host child processes wrapped by mcpbridge (which
// re-exposes their tools over streamable HTTP); http servers are reverse-proxied
// with their host-held credential injected. Either way the credential stays on
// the host — the container reaches only the loopback relay at /mcp/<name>/.
//
// stdio children are REUSED across endpoint reloads. The SDK drives reloads two
// ways and this host handles both without respawning a child whose config is
// unchanged:
//   - Full reload (LoadEndpoints): re-Provision with no preceding Deprovision.
//     Routes reconciles the live bridges against the new allowlist — matching
//     ones are reused in place, dropped/changed ones are released.
//   - Selective reload / removal (file watcher): Deprovision (→ ReleaseSlug)
//     then maybe Provision. ReleaseSlug schedules each bridge for release after
//     a grace period; a following Provision within the window revives it (so a
//     reload reuses), and a real removal lets the grace timer close it.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/modelcontextprotocol/go-sdk/auth"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/egressbroker"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/mcpbridge"
)

const (
	// mcpBridgeStartTimeout bounds how long a stdio MCP child has to start and
	// report its tools before provisioning gives up on it (and skips it).
	mcpBridgeStartTimeout = 20 * time.Second

	// mcpBridgeReleaseGrace is how long a stdio bridge lingers after its
	// endpoint is deprovisioned, so a reload's Deprovision→Provision reuses the
	// running child instead of respawning it. A real removal (no Provision
	// follows) closes the child after this window.
	mcpBridgeReleaseGrace = 60 * time.Second
)

// mcpBridge is the slice of *mcpbridge.Bridge mcpHost depends on, factored into
// an interface so tests can substitute a fake child without spawning a process.
type mcpBridge interface {
	Start(ctx context.Context) error
	Handler() http.Handler
	Close() error
}

// bridgeFactory builds (but does not start) a stdio bridge. Swapped in tests.
type bridgeFactory func(name string, cfg mcpbridge.Config, logger *slog.Logger) (mcpBridge, error)

func defaultBridgeFactory(name string, cfg mcpbridge.Config, logger *slog.Logger) (mcpBridge, error) {
	return mcpbridge.NewStdio(name, cfg, logger)
}

type bridgeKey struct {
	slug   string
	server string
}

// liveBridge is one running stdio child plus the bookkeeping for reuse and
// deferred release.
type liveBridge struct {
	bridge      mcpBridge
	fingerprint string // identity of the child's config; mismatch ⇒ respawn
	gen         uint64 // bumped on release/revive; a pending sweep only fires if it still matches
	pending     bool   // scheduled for release (awaiting the grace timer)
}

// oauthHandlerProvider yields the non-interactive OAuth handler for a connected
// remote MCP server (implemented by oauthManager). Returns an error when the
// server is not connected.
type oauthHandlerProvider interface {
	Handler(ctx context.Context, server, serverURL string) (auth.OAuthHandler, error)
}

// mcpHost owns the per-endpoint stdio bridges and builds broker routes.
type mcpHost struct {
	registry *mcpRegistry
	oauth    oauthHandlerProvider
	logger   *slog.Logger
	factory  bridgeFactory
	grace    time.Duration

	mu      sync.Mutex
	bridges map[bridgeKey]*liveBridge
}

func newMCPHost(registry *mcpRegistry, oauth oauthHandlerProvider, logger *slog.Logger) *mcpHost {
	if logger == nil {
		logger = slog.Default()
	}
	return &mcpHost{
		registry: registry,
		oauth:    oauth,
		logger:   logger,
		factory:  defaultBridgeFactory,
		grace:    mcpBridgeReleaseGrace,
		bridges:  map[bridgeKey]*liveBridge{},
	}
}

// Routes resolves an endpoint's requested MCP servers against the registry and
// returns the broker routes plus the names actually wired (a subset of the
// request — unknown, disabled, or failed-to-start servers are skipped and
// logged, never failing the endpoint build). The returned names feed
// EgressProvision.MCPServers, so the container's SYFT_MCP_SERVERS reflects only
// what is genuinely reachable. Reused stdio children are kept in place; this
// slug's stdio bridges no longer in the allowlist are scheduled for release.
func (h *mcpHost) Routes(slug string, servers []string) (routes []egressbroker.Route, wired []string) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// One registry read serves the whole reconcile — get() would re-read and
	// re-parse the file once per requested server.
	defs := map[string]mcpServerDef{}
	if all, err := h.registry.load(); err != nil {
		h.logger.Warn("mcp: registry load failed; no servers wired", "slug", slug, "error", err)
	} else {
		for _, def := range all {
			defs[def.Name] = def
		}
	}

	keptBridge := map[bridgeKey]bool{}
	for _, name := range cleanStrings(servers) {
		def, ok := defs[name]
		switch {
		case !ok:
			h.logger.Warn("mcp: endpoint requests unknown server; skipping", "slug", slug, "server", name)
			continue
		case !def.Enabled:
			h.logger.Warn("mcp: requested server is disabled; skipping", "slug", slug, "server", name)
			continue
		}

		var handler http.Handler
		switch def.Transport {
		case mcpTransportHTTP:
			if def.authMode() == mcpAuthOAuth {
				// OAuth remote server: a go-sdk client (in a bridge) holds the
				// authorized connection and re-exposes its tools; the token stays
				// host-side. Lifecycle-managed like a stdio bridge.
				key := bridgeKey{slug: slug, server: def.Name}
				b, ok := h.ensureOAuthBridgeLocked(key, def)
				if !ok {
					continue
				}
				keptBridge[key] = true
				handler = b.Handler()
			} else {
				// Static-header / public server: a stateless reverse proxy
				// injects the host-held credentials (if any) per request. No
				// child to reuse — built fresh.
				handler = egressbroker.NewCredentialProxy(
					egressbroker.StaticHeaderSource{Upstream: def.URL, Headers: def.Headers},
					h.logger,
				)
			}
		case mcpTransportStdio:
			key := bridgeKey{slug: slug, server: def.Name}
			b, ok := h.ensureStdioBridgeLocked(key, def)
			if !ok {
				continue
			}
			keptBridge[key] = true
			handler = b.Handler()
		default:
			h.logger.Warn("mcp: unknown transport; skipping", "slug", slug, "server", def.Name, "transport", def.Transport)
			continue
		}

		// Prefix carries no trailing slash: MCP clients POST to the bare
		// endpoint URL /mcp/<name>, and the broker matches at a segment
		// boundary and strips the prefix before dispatching (see
		// egressbroker.Route).
		routes = append(routes, egressbroker.Route{
			Prefix:  containermode.EgressMCPPath + "/" + name,
			Handler: handler,
		})
		wired = append(wired, name)
	}

	// Any of this slug's live bridges (stdio or OAuth) that the new allowlist no
	// longer keeps are scheduled for release (config-changed ones were already
	// retired inside ensureBridgeLocked).
	for key, lb := range h.bridges {
		if key.slug == slug && !keptBridge[key] && !lb.pending {
			h.scheduleReleaseLocked(key, lb)
		}
	}
	return routes, wired
}

// ensureStdioBridgeLocked ensures a stdio bridge for key. Caller holds h.mu.
func (h *mcpHost) ensureStdioBridgeLocked(key bridgeKey, def mcpServerDef) (mcpBridge, bool) {
	return h.ensureBridgeLocked(key, stdioFingerprint(def), func() (mcpBridge, error) {
		return h.factory(def.Name, mcpbridge.Config{Command: def.Command, Env: def.Env}, h.logger)
	})
}

// ensureOAuthBridgeLocked ensures an HTTP bridge to a remote OAuth MCP server.
// It loads the server's stored token handler; an unconnected server yields a
// failed start (skipped + logged), surfacing as "not wired" until the user
// connects it. Caller holds h.mu.
func (h *mcpHost) ensureOAuthBridgeLocked(key bridgeKey, def mcpServerDef) (mcpBridge, bool) {
	if h.oauth == nil {
		h.logger.Warn("mcp: oauth server requested but no oauth manager", "slug", key.slug, "server", def.Name)
		return nil, false
	}
	return h.ensureBridgeLocked(key, "oauth\x00"+def.URL, func() (mcpBridge, error) {
		oh, err := h.oauth.Handler(context.Background(), def.Name, def.URL)
		if err != nil {
			return nil, err
		}
		return mcpbridge.NewHTTP(def.Name, def.URL, oh, h.logger)
	})
}

// ensureBridgeLocked returns a running bridge for key, reusing the live one when
// its config fingerprint is unchanged, retiring and respawning it when the
// fingerprint changed, or building a fresh one via build(). Caller holds h.mu.
func (h *mcpHost) ensureBridgeLocked(key bridgeKey, fp string, build func() (mcpBridge, error)) (mcpBridge, bool) {
	if lb := h.bridges[key]; lb != nil {
		if lb.fingerprint == fp {
			// Reuse: cancel any pending release (bumping gen voids its sweep).
			lb.gen++
			lb.pending = false
			return lb.bridge, true
		}
		// Config changed — retire the old bridge asynchronously (Close can block
		// on child exit / connection teardown) and build anew.
		delete(h.bridges, key)
		old := lb.bridge
		go func() { _ = old.Close() }()
		h.logger.Info("mcp: server config changed; respawning", "slug", key.slug, "server", key.server)
	}

	b, err := build()
	if err != nil {
		h.logger.Warn("mcp: build bridge failed; skipping", "slug", key.slug, "server", key.server, "error", err)
		return nil, false
	}
	ctx, cancel := context.WithTimeout(context.Background(), mcpBridgeStartTimeout)
	defer cancel()
	if err := b.Start(ctx); err != nil {
		h.logger.Warn("mcp: start bridge failed; skipping", "slug", key.slug, "server", key.server, "error", err)
		_ = b.Close()
		return nil, false
	}
	h.bridges[key] = &liveBridge{bridge: b, fingerprint: fp}
	return b, true
}

// scheduleReleaseLocked marks a bridge for release after the grace period. A
// later reuse (revive) or another release bumps gen, voiding this timer. Caller
// holds h.mu.
func (h *mcpHost) scheduleReleaseLocked(key bridgeKey, lb *liveBridge) {
	lb.gen++
	lb.pending = true
	gen := lb.gen
	time.AfterFunc(h.grace, func() { h.sweep(key, gen) })
}

// sweep closes a bridge iff it is still pending release at the generation the
// timer was scheduled for (i.e. it was not revived or re-released since).
func (h *mcpHost) sweep(key bridgeKey, gen uint64) {
	h.mu.Lock()
	lb := h.bridges[key]
	doClose := lb != nil && lb.pending && lb.gen == gen
	if doClose {
		delete(h.bridges, key)
	}
	h.mu.Unlock()
	if doClose {
		if err := lb.bridge.Close(); err != nil {
			h.logger.Warn("mcp: bridge close error", "slug", key.slug, "server", key.server, "error", err)
		}
		h.logger.Info("mcp: released idle bridge", "slug", key.slug, "server", key.server)
	}
}

// ReleaseSlug schedules every stdio bridge of an endpoint for release. Called on
// Deprovision (reload or removal): a reload's following Provision revives the
// ones it still wants; a removal lets them close after the grace period.
func (h *mcpHost) ReleaseSlug(slug string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	for key, lb := range h.bridges {
		if key.slug == slug && !lb.pending {
			h.scheduleReleaseLocked(key, lb)
		}
	}
}

// Stop tears down every bridge across all endpoints. Called on app shutdown.
func (h *mcpHost) Stop() {
	h.mu.Lock()
	all := h.bridges
	h.bridges = map[bridgeKey]*liveBridge{}
	h.mu.Unlock()
	for key, lb := range all {
		if err := lb.bridge.Close(); err != nil {
			h.logger.Warn("mcp: bridge close error on shutdown", "slug", key.slug, "server", key.server, "error", err)
		}
	}
}

// stdioFingerprint is the config identity of a stdio server: a change here means
// the child must be respawned. json.Marshal emits map keys sorted, so the
// fingerprint is deterministic and unambiguous.
func stdioFingerprint(def mcpServerDef) string {
	data, _ := json.Marshal([]any{def.Transport, def.Command, def.Env})
	return string(data)
}
