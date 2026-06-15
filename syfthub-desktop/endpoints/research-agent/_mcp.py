"""Minimal MCP client for brokered tool servers — zero dependencies.

The host egress broker exposes each allowed MCP server at
  {SYFT_MCP_BASE_URL}/{server_name}
as a *stateless, JSON-response* streamable-HTTP MCP endpoint (see
sdk/golang/syfthubapi/mcpbridge). That lets this client be trivial: a plain
JSON-RPC POST returns a JSON-RPC response — no session handshake, no SSE.

The credential for each server lives on the host; the broker injects it. This
client (running inside the container) only ever sees a loopback URL and tool
names/results — never a PAT.

Public surface:
  discover() -> (tool_defs, dispatch)
    tool_defs  : OpenAI-style function tool definitions for all brokered tools,
                 namespaced "mcp__<server>__<tool>".
    dispatch   : {namespaced_name: callable(arguments_dict) -> str}
"""

import concurrent.futures
import json
import os
import urllib.error
import urllib.request

_TOOL_PREFIX = "mcp"
_NAMESPACE_SEP = "__"


def _rpc(url: str, method: str, params: dict, timeout: int = 60) -> dict:
    """One JSON-RPC call. Returns the `result` object, or raises RuntimeError."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    # Stateless+JSON returns application/json; tolerate an SSE data: frame too.
    text = raw
    if "data:" in raw and ("event:" in raw or raw.lstrip().startswith("data:")):
        for line in raw.splitlines():
            if line.startswith("data:"):
                text = line[len("data:"):].strip()
    msg = json.loads(text)
    if "error" in msg and msg["error"]:
        raise RuntimeError(f"MCP {method} error: {msg['error']}")
    return msg.get("result") or {}


def _server_url(base: str, name: str) -> str:
    return f"{base.rstrip('/')}/{name}"


def _namespaced(server: str, tool: str) -> str:
    return f"{_TOOL_PREFIX}{_NAMESPACE_SEP}{server}{_NAMESPACE_SEP}{tool}"


def _result_to_text(result: dict) -> str:
    """Flatten an MCP CallToolResult to a string for the LLM tool message."""
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
        else:
            parts.append(json.dumps(item))
    text = "\n".join(p for p in parts if p)
    if result.get("isError"):
        return f"(tool error) {text}" if text else "(tool error)"
    return text or "(no output)"


def discover():
    """Discover brokered MCP tools. Returns (tool_defs, dispatch).

    Reads SYFT_MCP_BASE_URL / SYFT_MCP_SERVERS (set by the host when the
    endpoint exposes MCP servers). Returns ([], {}) when MCP is not configured.
    A server that fails to list is skipped with a stderr note — one bad server
    never takes down the others or the agent.
    """
    base = os.environ.get("SYFT_MCP_BASE_URL", "").strip()
    servers = [s.strip() for s in os.environ.get("SYFT_MCP_SERVERS", "").split(",") if s.strip()]
    if not base or not servers:
        return [], {}

    def list_tools(server: str):
        try:
            return _rpc(_server_url(base, server), "tools/list", {})
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as e:
            print(f"[mcp] skip server {server!r}: {e}", flush=True)
            return None

    # Each listing is one independent round-trip through the relay; run them
    # concurrently so agent startup pays for the slowest server, not the sum.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(servers))) as pool:
        listings = list(pool.map(list_tools, servers))

    tool_defs = []
    dispatch = {}
    for server, result in zip(servers, listings):
        if result is None:
            continue
        url = _server_url(base, server)
        for tool in result.get("tools") or []:
            name = tool.get("name")
            if not name:
                continue
            qualified = _namespaced(server, name)
            schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
            desc = tool.get("description") or f"{name} (via {server} MCP server)"
            tool_defs.append({
                "type": "function",
                "function": {"name": qualified, "description": desc, "parameters": schema},
            })
            dispatch[qualified] = _make_caller(url, name)
    return tool_defs, dispatch


def _make_caller(url: str, tool: str):
    def call(arguments: dict) -> str:
        try:
            result = _rpc(url, "tools/call", {"name": tool, "arguments": arguments or {}})
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as e:
            return f"Error calling MCP tool {tool}: {e}"
        return _result_to_text(result)

    return call
