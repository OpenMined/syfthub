# SyftHub Documentation

> SyftHub is a registry and discovery platform for AI/ML endpoints — "GitHub for AI endpoints."

---

## Getting Started

| Doc | Audience | Description |
|---|---|---|
| [Developer Onboarding](guides/onboarding.md) | New team members | What is SyftHub, codebase tour, key concepts |
| [Local Setup](guides/local-setup.md) | All developers | Clone to running in 5 minutes |
| [Glossary](glossary.md) | Everyone | Definitions of all SyftHub domain terms |

---

## Architecture

| Doc | Description |
|---|---|
| [Architecture Overview](architecture/overview.md) | C4 diagrams, service map, token architecture, data flows |
| [Backend](architecture/components/backend.md) | FastAPI service — auth, registry, IdP, health monitor |
| [Frontend](architecture/components/frontend.md) | React 19 SPA — routes, state management, auth flow |
| [Aggregator](architecture/components/aggregator.md) | Stateless RAG service — orchestration, retrieval, streaming |
| [MCP Server](architecture/components/mcp.md) | OAuth 2.1 + Model Context Protocol for AI assistants |

---

## API Reference

| Doc | Base URL | Endpoints |
|---|---|---|
| [Backend API](api/backend.md) | `/api/v1` | 89 endpoints — auth, users, endpoints, orgs, IdP, NATS, accounting |
| [Aggregator API](api/aggregator.md) | `/aggregator/api/v1` | RAG chat + streaming (SSE) |
| [MCP API](api/mcp.md) | `/mcp` | OAuth 2.1 flow + MCP tools |

OpenAPI (dev): `http://localhost:8080/docs`

---

## Explanation (Concepts)

| Doc | Topic |
|---|---|
| [Authentication](explanation/authentication.md) | Dual-token architecture (HS256 hub + RS256 satellite), JWKS, PATs |
| [PKI Workflow](explanation/pki-workflow.md) | Identity Provider, JWKS verification, MCP OAuth flow |
| [RAG Architecture](explanation/rag-architecture.md) | Aggregator pipeline — retrieval, reranking, prompt construction, streaming |

---

## How-To Guides

| Doc | Audience |
|---|---|
| [Publishing Endpoints](guides/publishing-endpoints.md) | ML engineers, data scientists |
| [Python SDK](guides/python-sdk.md) | Python developers |
| [TypeScript SDK](guides/typescript-sdk.md) | JavaScript/TypeScript developers |
| [CLI Reference](guides/cli.md) | Terminal users |

---

## Runbooks (Operations)

| Doc | Use When |
|---|---|
| [Deployment](runbooks/deploy.md) | Deploying to dev or production |
| [Rollback](runbooks/rollback.md) | Rolling back a bad deployment |
| [Incident Response](runbooks/incident-response.md) | Triaging production incidents |

---

## SDKs

| SDK | Package | Path | Install |
|---|---|---|---|
| Python | `syfthub-sdk` | `sdk/python/` | `pip install syfthub-sdk` |
| TypeScript | `@syfthub/sdk` | `sdk/typescript/` | `npm install @syfthub/sdk` |
| Go (hub client) | — | `sdk/golang/syfthub/` | `go get` |
| Go (endpoint SDK) | — | `sdk/golang/syfthubapi/` | `go get` |
| CLI | — | `cli/` | Binary from GitHub Releases |

---

## Quick Reference

### Dev Commands
```bash
make dev      # Start all services
make stop     # Stop all services
make logs     # View container logs
make test     # Run all tests
make check    # Lint + type check
```

### Services (dev)
| Service | URL |
|---|---|
| App | http://localhost:8080 |
| API Docs | http://localhost:8080/docs |
| Backend | http://localhost:8080/api/v1 |
| Aggregator | http://localhost:8080/aggregator/api/v1 |
| MCP | http://localhost:8080/mcp |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Meilisearch | localhost:7700 |

### Token Quick Reference
| Token | Algorithm | Lifetime | Get via |
|---|---|---|---|
| Hub access | HS256 | 30 min | `POST /api/v1/auth/login` |
| Refresh | Opaque | 7 days | `POST /api/v1/auth/login` |
| Satellite | RS256 | 60 s | `GET /api/v1/token?aud={user}` |
| PAT | Opaque | Configurable | `POST /api/v1/auth/tokens` |
| MCP | RS256 | 1 hr | MCP OAuth flow |
