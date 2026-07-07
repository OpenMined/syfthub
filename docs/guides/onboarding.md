# Developer Onboarding

Welcome to SyftHub -- a registry and discovery platform for AI/ML endpoints, often described as "GitHub for AI endpoints."

## Architecture at a Glance

See [docs/architecture/overview.md](../architecture/overview.md) for full diagrams and details.

| Service | Stack | Port |
|---------|-------|------|
| Backend | FastAPI / Python | 8000 |
| Frontend | React 19 / TypeScript / Vite | 3000 |
| Aggregator | FastAPI / Python (stateless RAG) | 8001 |
| MCP Server | FastMCP / Python (OAuth + MCP) | 8002 |
| Nginx | Reverse proxy | 8080 |
| PostgreSQL | Database | 5432 |
| Redis | Caching / pub-sub | 6379 |
| Meilisearch | Endpoint search | 7700 |

## Getting Started

Follow the [Local Setup Guide](local-setup.md) to get the full stack running.

## Key Concepts

### Endpoints

The core resource. Each endpoint is a `model`, `data_source`, or `model_data_source`, addressed by `/{owner}/{slug}`.

**Visibility levels:**
- `PUBLIC` -- anyone can see it
- `INTERNAL` -- any authenticated user
- `PRIVATE` -- owner or organization members only (returns 404 to others)

### Organizations

Users can create organizations and publish endpoints under them.

### Tokens

| Token | Algorithm | Lifetime | Purpose |
|-------|-----------|----------|---------|
| Hub token | HS256 | 30 min | General API access |
| Satellite token | RS256 | 60 sec | Short-lived, endpoint-scoped |
| Personal access token (PAT) | -- | Long-lived | CI/CD, SDK auth (prefix: `syft_pat_`) |

### Aggregator

A stateless RAG service. Receives a user prompt, retrieves relevant context from data sources, and queries a model endpoint to produce an answer. No session state is stored.

### MCP Server

Exposes SyftHub capabilities to AI assistants via the Model Context Protocol. Uses RS256 OAuth tokens (1 hour, kid `mcp-key-1`).

## Codebase Tour

```
components/
  backend/       FastAPI backend (service/repo pattern, Alembic migrations)
  frontend/      React 19 SPA (shadcn/ui, Tailwind, Zustand, React Query)
  aggregator/    Async RAG pipeline (ONNX reranker, NATS transport)
  mcp/           MCP + OAuth server

sdk/
  python/        syfthub-sdk (pip install syfthub-sdk)
  typescript/    @syfthub/sdk (npm install @syfthub/sdk)
  golang/        Go hub client + server SDK

cli/             Go/Cobra CLI (binary: syft)

deploy/          Docker Compose, Nginx config
```

## Testing

```bash
# Run all tests
make test

# Backend only
cd components/backend && uv run python -m pytest

# Frontend only
cd components/frontend && npm test
```

## Code Quality

```bash
# All linting, formatting, and type checks
make check
```

See [Local Setup](local-setup.md) for per-language commands.

## Key Files

| File | Purpose |
|------|---------|
| `.env.example` | All environment variables with defaults |
| `Makefile` | Dev workflow commands |
| `deploy/` | Docker Compose and Nginx configuration |

## Where to Find Docs

All documentation lives in the `docs/` directory:

- `docs/architecture/` -- system design and component deep-dives
- `docs/api/` -- API reference for backend and aggregator
- `docs/guides/` -- setup, publishing, SDK, and CLI guides
- `docs/explanation/` -- conceptual docs (auth, RAG, invocation)
- `docs/runbooks/` -- deployment and operations procedures

## Common Dev Commands

| Command | What it does |
|---------|-------------|
| `make dev` | Start all services |
| `make stop` | Stop all services |
| `make logs` | Tail logs from all services |
| `make test` | Run the full test suite |
| `make check` | Lint, format-check, and type-check everything |
