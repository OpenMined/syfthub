# Brokered MCP tools for container endpoints

Container endpoints can call host-configured MCP tool servers **without the
container ever holding the server's credential** (PAT/API key). This is the
same trust split the egress broker already uses for LLM credentials, applied to
MCP: the secret stays on the host, the container talks to a loopback relay, and
the host injects the credential per request.

```
┌─ container ──────────────────────────────────────────────┐
│  agent runner (claude / research-agent / …)              │
│    LLM:  http://127.0.0.1:8788/v1/...        (sentinel)  │
│    MCP:  http://127.0.0.1:8788/mcp/<server>/  (no auth)  │
│                       │  server.py relay (byte pump)     │
└───────────────────────┼──────────────────────────────────┘
                        ▼ AF_UNIX  <desktopDir>/egress/sockets/<slug>.sock
┌─ host ───────────────────────────────────────────────────┐
│  egressbroker (per-slug listener + route mux)            │
│    default route ─────► LLM credential swap              │
│    /mcp/github/ ──────► reverse proxy + PAT header (http)│
│    /mcp/linear/ ──────► mcpbridge → stdio child (stdio)  │
│                                                          │
│  MCP registry: <desktopDir>/mcp/servers.json (0600)      │
└──────────────────────────────────────────────────────────┘
```

## Components

| Layer | Where | Role |
|-------|-------|------|
| Registry | `syfthub-desktop/mcp_registry.go` | Host-only catalog of MCP servers + their credentials (`<desktopDir>/mcp/servers.json`, 0600). Import from `~/.claude.json`. |
| Host wiring | `syfthub-desktop/mcp_host.go` | Per-endpoint bridges + broker `Route`s. stdio → `mcpbridge`; http → `StaticHeaderSource` proxy. |
| Bridge | `sdk/.../mcpbridge` | Runs one stdio MCP child, re-exposes its **tools** as a stateless streamable-HTTP handler. |
| Route mux | `sdk/.../egressbroker` | `Route{Prefix,Handler}` matched (longest prefix) ahead of the LLM proxy. |
| Discovery env | `sdk/.../containermode/egress.go` | `SYFT_MCP_BASE_URL`, `SYFT_MCP_SERVERS` — handler-visible, no secret. |
| Schema | `sdk/.../filemode` `SandboxConfig.ExposeMCP` | Per-endpoint allowlist (`sandbox.expose_mcp` frontmatter). |
| UI | `SandboxModal` (per-endpoint expose), `SettingsModal`/`McpServersSection` (registry) | |

## Enforcement (the security boundary is the host, not the config)

1. **Allowlist = route registration.** `mcpHost.Routes` only registers
   `/mcp/<name>/` for servers that are in the registry **and** enabled **and**
   listed in the endpoint's `sandbox.expose_mcp`. A handler probing any other
   `/mcp/*` path gets a 404 from the broker — independent of what config it was
   handed.
2. **Per-endpoint socket, 0600.** Endpoint A cannot reach endpoint B's brokered
   servers even if both name the same server.
3. **stdio children get an explicit env** (registry `env` + a small allowlist of
   benign host vars), never the desktop's full environment.
4. **The credential never crosses into the container.** It appears only in the
   outbound request the host makes (http: injected header; stdio: child env).
   `EgressProvision.HandlerEnv` and `SYFT_MCP_SERVERS` carry **names only** —
   asserted by `TestProvisionNeverLeaksMCPCredentialIntoHandlerEnv`.

The tool *names and schemas* do enter the model's context (that is how tool
calling works); the PAT does not.

## Wire contract for runners

When an endpoint exposes ≥1 MCP server, the host sets two handler-visible env
vars (no credential):

```
SYFT_MCP_BASE_URL=http://127.0.0.1:8788/mcp
SYFT_MCP_SERVERS=github,linear
```

Each server is reachable at `${SYFT_MCP_BASE_URL}/<name>` as a **stateless,
JSON-response** streamable-HTTP MCP endpoint. "Stateless + JSON" means a runner
can speak MCP with a dependency-free client: a plain JSON-RPC `POST` returns a
JSON-RPC response — **no session-id handshake, no SSE parsing**. (Full
streamable-HTTP clients such as `claude` also work; the server stays
spec-compatible.)

```
POST ${SYFT_MCP_BASE_URL}/github
Content-Type: application/json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}

POST ${SYFT_MCP_BASE_URL}/github
{"jsonrpc":"2.0","id":2,"method":"tools/call",
 "params":{"name":"search_issues","arguments":{"q":"open bugs"}}}
```

### research-agent (in this repo)

`syfthub-desktop/endpoints/research-agent/_mcp.py` is a ~120-line stdlib MCP
client. The runner calls `tool_defs, dispatch = _mcp.discover()` at startup,
merges `tool_defs` into its OpenAI tool list (namespaced `mcp__<server>__<tool>`),
and routes those calls through `dispatch`.

### claude (`claude --bare`)

Generate an MCP config of plain http URLs (no auth — the broker injects it) and
pass it with `--strict-mcp-config` so claude loads only these:

```python
import json, os, tempfile
base = os.environ.get("SYFT_MCP_BASE_URL", "")
servers = [s for s in os.environ.get("SYFT_MCP_SERVERS", "").split(",") if s]
if base and servers:
    cfg = {"mcpServers": {s: {"type": "http", "url": f"{base}/{s}"} for s in servers}}
    path = os.path.join(tempfile.gettempdir(), "syft-mcp.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    extra_args = ["--mcp-config", path, "--strict-mcp-config"]
```

The config holds only loopback URLs; it is written to the container's ephemeral
`$HOME`/tmp and contains no secret.

## Scope (Phase 1) and follow-ups

Implemented: tools (list + call), stdio and http servers, per-server allowlist,
registry + Claude import, SandboxModal/Settings UI, research-agent client.

stdio children are **reused across endpoint reloads** (`mcpHost`): a full
reload reconciles live bridges in place; a selective reload's
Deprovision→Provision revives within a grace window; a real removal closes the
child after the grace period; a config change respawns. So a mount/sandbox edit
no longer respawns the endpoint's MCP servers.

**OAuth remote servers** (e.g. figma) are supported: a server marked
`auth: oauth` routes through a bridge built with `mcpbridge.NewHTTP(url,
oauthHandler)`, where the handler comes from `mcpoauth` (discovery → DCR → PKCE
→ token, persisted host-side, auto-refreshed). The user authorizes once via a
browser ("Connect" in Settings → MCP Servers); the token never enters the
container. See `sdk/.../mcpoauth` and `syfthub-desktop/mcp_oauth.go`.

Not yet (Phase 2): per-tool allowlists and audit/manual-review gating (needs
JSON-RPC termination on the http path), dynamic `listChanged`, idle-reap of
bridges whose endpoint is alive but unused, resources/prompts/sampling
passthrough, multi-header static http injection (Phase 1 injects one auth
header), and a manual pre-registered-client fallback for OAuth servers whose
authorization server lacks Dynamic Client Registration.
