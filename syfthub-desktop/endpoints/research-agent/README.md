---
slug: research-agent
type: agent
name: Research Agent
description: LLM + MCP client agent. Connects to MCP servers for tools and drives a real agentic loop with streaming, tool calls, and multi-turn conversation.
enabled: true
version: "2.2.0"
runtime:
  mode: subprocess
  workers: 1
  timeout: 300
env:
  optional:
    - API_KEY
    - SYSTEM_PROMPT
---

# Research Agent

A real LLM-powered agent that uses MCP servers as its toolbelt.

## How it works

1. Loads MCP server definitions from `mcp.json`
2. Starts each server and discovers its tools
3. Passes tools to the LLM (auto-detected from your API key)
4. Drives the tool-calling loop: LLM → tool call → MCP → result → LLM → …
5. Streams tokens and events to the UI in real-time
6. Supports multi-turn conversation

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

## Adding tools

Edit `mcp.json` to add any MCP server — no code changes needed:

```json
{
  "mcpServers": {
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": { "BRAVE_API_KEY": "${BRAVE_API_KEY}" }
    },
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

Browse available MCP servers at [modelcontextprotocol.io/servers](https://modelcontextprotocol.io/servers).
