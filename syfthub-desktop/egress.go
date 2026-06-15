// Package main — host egress broker wiring.
//
// Every container endpoint reaches its model API only through the host broker,
// so the real LLM credential never enters the container. The broker routes by
// request path: Anthropic-native (claude) → the host's
// ~/.claude/.credentials.json; OpenAI-compatible (basic-agent) → the endpoint's
// host-stored API key. The container only ever carries a sentinel/redacted
// credential, which the broker swaps for the real one.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/egressbroker"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/wailsapp/wails/v2/pkg/runtime"
)

// maxUnixSocketPath is a conservative bound on an AF_UNIX socket path. The
// kernel sun_path limit is 104 bytes on macOS and 108 on Linux; past it
// net.Listen fails with a confusing "invalid argument". A long home dir plus a
// long slug can blow it, so socketPath folds the slug to a short hash when the
// full path would exceed this.
const maxUnixSocketPath = 100

// claudeSentinelToken is the placeholder ANTHROPIC_AUTH_TOKEN injected so
// `claude --bare` makes well-formed requests; the broker replaces it with the
// real subscription token. It is never a valid credential.
const claudeSentinelToken = "sk-ant-syfthub-egress-sentinel"

// newEgressProvisioner builds the filemode.EgressProvisioner backing the
// container egress broker. It caches the provisioner and everything it owns
// (broker, key store, MCP registry/host, credential source with its mtime-keyed
// parse cache) on a.* and reuses them across calls. The CALLER MUST HOLD a.mu:
// it both reads a.egressProvisioner and writes the cached fields, which
// shutdown reads under a.mu — the settings-save path already holds the lock and
// startup acquires it around the call.
func (a *App) newEgressProvisioner() filemode.EgressProvisioner {
	if a.egressProvisioner != nil {
		return a.egressProvisioner
	}
	dir, err := walletDir()
	if err != nil {
		if a.ctx != nil {
			runtime.LogWarning(a.ctx, fmt.Sprintf("egress: cannot resolve desktop dir, brokering disabled: %v", err))
		}
		return nil
	}
	home, _ := os.UserHomeDir()
	claudeCreds := filepath.Join(home, ".claude", ".credentials.json")
	a.egressBroker = egressbroker.New(nil)
	a.egressKeys = &egressKeyStore{dir: filepath.Join(dir, "egress", "keys")}
	a.mcpRegistry = newMCPRegistry(dir)
	a.mcpOAuth = newOAuthManager(filepath.Join(dir, "mcp", "oauth"), claudeCreds, a.openBrowser, nil)
	a.mcpHost = newMCPHost(a.mcpRegistry, a.mcpOAuth, nil)
	a.egressProvisioner = &egressProvisioner{
		broker:    a.egressBroker,
		socketDir: filepath.Join(dir, "egress", "sockets"),
		keyStore:  a.egressKeys,
		mcpHost:   a.mcpHost,
		// One shared source for all endpoints: it caches the parsed credentials
		// file (keyed by mtime/size), so per-Provision construction would give
		// each endpoint its own redundant cache of the same file.
		anthropic: egressbroker.NewClaudeOAuthSource(claudeCreds),
	}
	return a.egressProvisioner
}

// egressProvisioner adapts the host broker to filemode.EgressProvisioner.
type egressProvisioner struct {
	broker    *egressbroker.Broker
	socketDir string
	keyStore  *egressKeyStore
	mcpHost   *mcpHost
	anthropic egressbroker.CredentialSource
}

func (p *egressProvisioner) Provision(req filemode.EgressRequest) (*filemode.EgressProvision, error) {
	slug := req.Slug
	if err := validateSlug(slug); err != nil {
		return nil, err
	}
	// Broker.Add creates the socket dir (0700) itself.
	sock := p.socketPath(slug)

	src := egressbroker.RoutingSource{
		Anthropic: p.anthropic,
		OpenAI:    egressbroker.NewStaticKeySource(func() (string, error) { return p.keyStore.Get(slug) }),
	}

	// Broker the endpoint's allowlisted MCP servers host-side. Only the names
	// actually wired (registered + enabled + started) come back; their
	// credentials stay on the host inside the route handlers.
	var mcpRoutes []egressbroker.Route
	var mcpServers []string
	if p.mcpHost != nil {
		mcpRoutes, mcpServers = p.mcpHost.Routes(slug, req.MCPServers)
	}

	if err := p.broker.Add(egressbroker.EndpointEgress{
		Slug:       slug,
		SocketPath: sock,
		Source:     src,
		Routes:     mcpRoutes,
	}); err != nil {
		return nil, err
	}

	// Sentinel handler creds. claude --bare needs ANTHROPIC_AUTH_TOKEN present
	// to make requests; the broker swaps it. basic-agent needs an API_KEY whose
	// prefix matches the real provider so its model/provider auto-detection
	// lines up with what the broker forwards to.
	// CLAUDE_CODE_ATTRIBUTION_HEADER=0 is a claude-CLI-specific quirk flag,
	// declared here (the claude-aware host) rather than in the generic SDK
	// provider.
	handlerEnv := map[string]string{
		"ANTHROPIC_AUTH_TOKEN":           claudeSentinelToken,
		"CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
	}
	if realKey, _ := p.keyStore.Get(slug); realKey != "" {
		handlerEnv["API_KEY"] = egressbroker.RedactKey(realKey)
	}
	return &filemode.EgressProvision{
		HostSocketPath: sock,
		HandlerEnv:     handlerEnv,
		MCPServers:     mcpServers,
	}, nil
}

// socketPath returns the AF_UNIX path for an endpoint's broker socket. It uses
// "<slug>.sock" when that fits within maxUnixSocketPath, otherwise a short
// hash of the slug so a long home dir or slug can't push the path past the
// kernel sun_path limit. Deterministic in the slug, so a reload re-derives the
// same path (Deprovision keys the broker by slug, not by socket path).
func (p *egressProvisioner) socketPath(slug string) string {
	sock := filepath.Join(p.socketDir, slug+".sock")
	if len(sock) <= maxUnixSocketPath {
		return sock
	}
	sum := sha256.Sum256([]byte(slug))
	return filepath.Join(p.socketDir, hex.EncodeToString(sum[:8])+".sock")
}

func (p *egressProvisioner) Deprovision(slug string) {
	p.broker.Remove(slug)
	if p.mcpHost != nil {
		p.mcpHost.ReleaseSlug(slug)
	}
}

// egressKeyStore is the host-only secret store for per-endpoint
// OpenAI-compatible API keys (basic-agent style): one file per slug, 0600.
// Get sits on the broker's per-request hot path, so reads are served from an
// in-memory cache after the first disk hit; every write goes through Set/Clear
// in this same process, which keep the cache coherent ("" = known absent).
type egressKeyStore struct {
	dir   string
	mu    sync.Mutex
	cache map[string]string
}

func (s *egressKeyStore) path(slug string) string { return filepath.Join(s.dir, slug+".key") }

func (s *egressKeyStore) Get(slug string) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if key, ok := s.cache[slug]; ok {
		return key, nil
	}
	data, err := os.ReadFile(s.path(slug))
	if err != nil && !os.IsNotExist(err) {
		return "", err
	}
	key := strings.TrimSpace(string(data))
	s.setCache(slug, key)
	return key, nil
}

func (s *egressKeyStore) Set(slug, key string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := os.MkdirAll(s.dir, 0o700); err != nil {
		return err
	}
	key = strings.TrimSpace(key)
	if err := os.WriteFile(s.path(slug), []byte(key), 0o600); err != nil {
		return err
	}
	s.setCache(slug, key)
	return nil
}

func (s *egressKeyStore) Clear(slug string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := os.Remove(s.path(slug)); err != nil && !os.IsNotExist(err) {
		return err
	}
	s.setCache(slug, "")
	return nil
}

func (s *egressKeyStore) setCache(slug, key string) {
	if s.cache == nil {
		s.cache = map[string]string{}
	}
	s.cache[slug] = key
}

// ── Wails bindings ──────────────────────────────────────────────────────────

// SetEndpointEgressKey stores (host-side) the LLM API key the broker injects for
// an OpenAI-compatible endpoint. The key never enters the container.
//
// Deliberately does NOT reload the endpoint: the only caller (SandboxModal's
// Save) follows with SetEndpointSandbox, whose reload re-provisions the
// container with the new key's sentinel — reloading here too would rebuild
// every container twice per Save.
func (a *App) SetEndpointEgressKey(slug, key string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
	if a.egressKeys == nil {
		return fmt.Errorf("egress not initialized")
	}
	return a.egressKeys.Set(slug, key)
}

// ClearEndpointEgressKey removes an endpoint's host-stored egress key.
func (a *App) ClearEndpointEgressKey(slug string) error {
	if err := validateSlug(slug); err != nil {
		return err
	}
	if a.egressKeys == nil {
		return nil
	}
	if err := a.egressKeys.Clear(slug); err != nil {
		return err
	}
	a.reloadAfterEndpointMutation(slug)
	return nil
}

// GetEndpointEgressKeyStatus reports whether a host key is set for the endpoint.
// It never returns the key itself.
func (a *App) GetEndpointEgressKeyStatus(slug string) (bool, error) {
	if err := validateSlug(slug); err != nil {
		return false, err
	}
	if a.egressKeys == nil {
		return false, nil
	}
	key, err := a.egressKeys.Get(slug)
	if err != nil {
		return false, err
	}
	return key != "", nil
}
