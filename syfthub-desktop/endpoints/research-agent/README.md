---
slug: research-agent
type: agent
name: Research Agent
description: LLM + MCP client agent. Connects to MCP servers for tools and drives a real agentic loop with streaming, tool calls, and multi-turn conversation.
enabled: true
version: "2.2.0"
runtime:
  workers: 1
  timeout: 300
env:
  optional:
    - API_KEY
    - SYSTEM_PROMPT
---

# Research Agent

A real LLM-powered agent with built-in tools plus any **brokered MCP servers**
the endpoint is allowed to use.

## How it works

1. Discovers brokered MCP tools from `SYFT_MCP_BASE_URL` / `SYFT_MCP_SERVERS`
   (set by the host when this endpoint exposes MCP servers) — see `_mcp.py`
2. Merges them with its built-in tools and passes all of them to the LLM
   (provider auto-detected from your API key)
3. Drives the tool-calling loop: LLM → tool call → (built-in or MCP) → result → LLM → …
4. Streams tokens and events to the UI in real-time
5. Supports multi-turn conversation

In container mode the agent has **no direct internet**: both its model API and
its MCP tool calls go through the host egress broker, which injects the real
credential host-side. No API key or PAT ever enters the container.

## Setup

Copy `.env.example` to `.env` and set your API key:

```bash
cp .env.example .env
# edit .env with your key
```

## Configuration

Only two variables needed:

| Variable | Default | Notes |
|----------|---------|-------|
| `API_KEY` | *(empty)* | Leave empty for local Ollama. OpenAI: `sk-…`. Anthropic: `sk-ant-…`. |
| `SYSTEM_PROMPT` | Built-in default | Optional custom instructions for the agent. |

The provider is detected automatically from the key prefix:

| Key prefix | Provider | Default model |
|-----------|----------|---------------|
| *(empty)* | Ollama (local) | `llama3.2` |
| `sk-ant-…` | Anthropic | `claude-3-5-haiku-20241022` |
| `sk-…` / other | OpenAI | `gpt-4o-mini` |

## Adding MCP tools

MCP servers are configured **on the host**, not in this endpoint — so their
credentials never enter the container. To give this agent a new toolbelt:

1. **Settings → MCP Servers** (host): import your servers from your Claude
   config, or add them to the host's `mcp/servers.json`, then **enable** the
   ones you want available. A server definition holds its own credential (a PAT
   or API key) — that stays on the host.
2. **This endpoint → Sandbox → Tools (MCP)**: check the servers this agent may
   call. That writes `sandbox.expose_mcp` to the endpoint's frontmatter.

On the next reload the host brokers exactly those servers: the agent reaches
each at `http://127.0.0.1:8788/mcp/<name>/` and the broker injects the
credential. The agent sees tool names, schemas, and results — never the secret.

Browse available MCP servers at [modelcontextprotocol.io/servers](https://modelcontextprotocol.io/servers).
