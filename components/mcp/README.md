# SyftHub MCP Server

A Model Context Protocol server that lets AI assistants — Claude Desktop, Cursor, and friends — discover and chat with endpoints on SyftHub.

For project-level docs, see the [repository README](../../README.md) and [`docs/`](../../docs/index.md).

## What it does

The MCP server exposes SyftHub to MCP-compatible AI clients over OAuth 2.1 + PKCE. Once connected, the assistant can list public endpoints and run RAG queries against them through SyftHub's aggregator.

## Running locally

From the repo root, `make dev` starts the MCP server at <http://localhost:8080/mcp> alongside the rest of the stack.

To run it on its own:

```bash
cd components/mcp
uv sync
uv run fastmcp run
```

## Learn more

- [MCP architecture](../../docs/architecture/components/mcp.md)
- [MCP API reference](../../docs/api/mcp.md)
- [PKI workflow](../../docs/explanation/pki-workflow.md)
