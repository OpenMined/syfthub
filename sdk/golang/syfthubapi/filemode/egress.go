package filemode

import (
	"maps"
	"path/filepath"
	"slices"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
)

// credentialEnvKeys are env vars that may carry a real LLM credential. They are
// stripped from the container env when brokering — the broker injects the real
// value host-side and the runner receives only a sentinel. Any key the host's
// provision re-injects as a sentinel (EgressProvision.HandlerEnv) is stripped
// too, so a host that brokers a new credential var can never leave the real
// value sitting next to its sentinel.
var credentialEnvKeys = map[string]struct{}{
	"API_KEY":              {},
	"ANTHROPIC_API_KEY":    {},
	"OPENAI_API_KEY":       {},
	"ANTHROPIC_AUTH_TOKEN": {},
}

// stripCredentialEnv drops any credential-bearing var from a KEY=value slice:
// the static credentialEnvKeys plus everything in alsoStrip (the keys the
// provision overrides with sentinels).
func stripCredentialEnv(env []string, alsoStrip map[string]string) []string {
	out := make([]string, 0, len(env))
	for _, kv := range env {
		key, _, _ := strings.Cut(kv, "=")
		if _, drop := credentialEnvKeys[key]; drop {
			continue
		}
		if _, drop := alsoStrip[key]; drop {
			continue
		}
		out = append(out, kv)
	}
	return out
}

// brokeredEnv rewrites a container env (KEY=value slice) for brokered egress.
// handlerVisible is the env the bwrap child may see: real credentials stripped
// (the broker injects them host-side), base URLs pointed at the in-container
// relay, the provision's sentinel creds appended, and — when the provision
// brokers MCP servers — the handler-visible MCP discovery vars. All sorted, so
// the container spec is deterministic across reloads. relayOnly are the vars
// read by server.py to start the relay — callers must append them only AFTER
// snapshotting the handler env allowlist so they never reach the bwrap child.
func brokeredEnv(env []string, prov *EgressProvision) (handlerVisible, relayOnly []string) {
	handlerVisible = stripCredentialEnv(env, prov.HandlerEnv)
	base := "http://127.0.0.1:" + containermode.EgressLoopbackPort
	handlerVisible = append(handlerVisible,
		"ANTHROPIC_BASE_URL="+base,
		"OPENAI_BASE_URL="+base,
	)
	for _, k := range slices.Sorted(maps.Keys(prov.HandlerEnv)) {
		handlerVisible = append(handlerVisible, k+"="+prov.HandlerEnv[k])
	}
	// MCP discovery vars carry no secret: a loopback base URL and the brokered
	// server names. The broker injects each server's host-held credential, so
	// these are safe for the handler to see (and to pass to claude/child CLIs).
	if len(prov.MCPServers) > 0 {
		handlerVisible = append(handlerVisible,
			containermode.EnvMCPBaseURL+"="+base+containermode.EgressMCPPath,
			containermode.EnvMCPServers+"="+strings.Join(prov.MCPServers, ","),
		)
	}
	relayOnly = []string{
		containermode.EnvEgressPort + "=" + containermode.EgressLoopbackPort,
		containermode.EnvEgressSock + "=" + containermode.EgressGuestSocket,
	}
	return handlerVisible, relayOnly
}

// credentialMountBasenames are file basenames that hold credentials and must
// never be bind-mounted into a brokered container.
var credentialMountBasenames = map[string]struct{}{
	"credentials": {}, // ~/.aws/credentials
	".netrc":      {},
	".npmrc":      {},
	".pypirc":     {},
	".pgpass":     {},
}

// credentialMountDirs are path segments that mark a credential-store directory;
// anything mounted from inside one is treated as a credential.
var credentialMountDirs = map[string]struct{}{
	".aws":   {},
	".ssh":   {},
	".gnupg": {},
}

// isCredentialMount reports whether a bind mount would expose a credential
// inside a brokered container. It inspects BOTH the resolved host source and
// the in-container target, because a credential can be smuggled in either by
// naming it on the target or by pointing an innocent-looking target at a
// credential source on the host. A suffix match on "credentials.json" catches
// ~/.claude/.credentials.json and similar regardless of directory; basename and
// path-segment matches catch the other well-known credential stores. The broker
// holds these host-side, so they must never reach the container.
func isCredentialMount(source, target string) bool {
	for _, p := range [2]string{source, target} {
		if p == "" {
			continue
		}
		lower := strings.ToLower(filepath.ToSlash(p))
		if strings.HasSuffix(lower, "credentials.json") {
			return true
		}
		if _, ok := credentialMountBasenames[strings.ToLower(filepath.Base(p))]; ok {
			return true
		}
		for _, seg := range strings.Split(lower, "/") {
			if _, ok := credentialMountDirs[seg]; ok {
				return true
			}
		}
	}
	return false
}

// EgressRequest is the per-endpoint input to Provision.
type EgressRequest struct {
	// Slug identifies the endpoint being provisioned.
	Slug string
	// MCPServers is the endpoint's requested MCP-server allowlist (frontmatter
	// sandbox.expose_mcp). The host resolves it against its registry; only the
	// servers it actually brokers come back in EgressProvision.MCPServers.
	MCPServers []string
}

// EgressProvisioner is implemented by the host (desktop) to broker an
// endpoint's egress. It is called once per container-mode endpoint at build
// time. Provision registers the endpoint with the host broker, creates the
// per-endpoint AF_UNIX socket, brokers any requested MCP servers, and returns
// the host socket path to bind-mount plus the sentinel credential env the
// handler should carry. The real credentials never leave the host. Deprovision
// is called by the provider on endpoint reload/removal (re-Provision follows on
// reload).
//
// When set on ProviderConfig, every container endpoint's LLM traffic is
// brokered: the handler's base URLs point at the in-container relay, which
// forwards to the bind-mounted broker socket. The container's docker network
// posture is decided by the provider (see buildContainerEndpoint), not here.
type EgressProvisioner interface {
	Provision(req EgressRequest) (*EgressProvision, error)
	Deprovision(slug string)
}

// EgressProvision is the result of Provision.
type EgressProvision struct {
	// HostSocketPath is the host AF_UNIX socket to bind-mount into the
	// container; the in-container relay forwards to it.
	HostSocketPath string

	// HandlerEnv are sentinel/placeholder credential vars for the bwrap child
	// (e.g. ANTHROPIC_AUTH_TOKEN, API_KEY) so the runner/claude emits
	// well-formed requests. The broker swaps these for the real credential
	// host-side. The base URLs and relay vars are added by the provider, not
	// here.
	HandlerEnv map[string]string

	// MCPServers is the set of MCP server names the host actually brokered for
	// this endpoint (a subset of the request — unknown/disabled servers are
	// dropped). When non-empty, the provider adds the handler-visible MCP
	// discovery env (SYFT_MCP_BASE_URL / SYFT_MCP_SERVERS). Never carries a
	// credential — only names.
	MCPServers []string
}
