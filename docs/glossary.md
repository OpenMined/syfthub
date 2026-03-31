# SyftHub Glossary

> **Audience:** All SyftHub developers, integrators, and operators
> **Last updated:** 2026-03-27

---

| Term | Definition |
|---|---|
| **Aggregator** | Stateless FastAPI service that implements Retrieval-Augmented Generation (RAG). Receives a chat message, queries registered SyftAI-Space data sources in parallel via NATS, builds an augmented prompt, calls a model endpoint, and returns or streams the response. Runs on port 8001. |
| **API Token (PAT)** | A long-lived personal access token (prefix `syft_pat_`) for programmatic access. Stored as a SHA-256 hash in the `api_tokens` table. Alternative to the short-lived hub token for automation use cases. |
| **Connect** | The connection configuration array on an endpoint, specifying how clients reach the underlying service (URL, auth method, etc.). |
| **Endpoint** | The core SyftHub entity — a published ML model or data source. Has an owner (user or organization), a slug, a type (`model`, `data_source`, or `model_data_source`), a visibility level, a description, tags, connection config, and access policies. Addressed via `/{owner}/{slug}`. |
| **Guest Token** | An RS256 JWT (60 s lifetime) that grants unauthenticated access to policy-free public endpoints. |
| **Health Monitor** | A background job in the backend that checks endpoint URLs every 30 seconds. Uses PostgreSQL advisory lock ID `839201` for distributed-lock across workers. |
| **Heartbeat** | A mechanism for users/organizations to register their domain. `POST /endpoints/health` is the preferred endpoint (sets per-endpoint `health_status`, `health_checked_at`, `health_ttl_seconds`). The older `POST /users/me/heartbeat` and `POST /organizations/{org_id}/heartbeat` routes are deprecated. |
| **Hub Token** | A short-lived (30 min) HS256 JWT issued by the backend on login. Used to authenticate requests to the backend API (`/api/v1/*`). Not accepted by satellite services. |
| **IdP (Identity Provider)** | SyftHub's role as a federated identity provider. Issues RS256 satellite tokens that satellite services verify locally via the JWKS endpoint — no round-trip to the hub on every request. |
| **JWKS** | JSON Web Key Set. A JSON document at `GET /.well-known/jwks.json` containing the RSA public key(s) used to verify satellite tokens. Satellite services cache and use this to verify tokens locally. |
| **MCP** | Model Context Protocol — an open standard for connecting AI assistants to external tools and data. SyftHub's MCP server implements this with OAuth 2.1 authentication, allowing AI assistants (like Claude) to discover and invoke SyftHub endpoints. |
| **MCP Token** | An RS256 JWT (3600 s / 1 hour lifetime, kid: `mcp-key-1`) used for MCP client-to-server authentication. Distinct from satellite tokens. |
| **Meilisearch** | Full-text search engine used for endpoint discovery search (metadata search, not document RAG). Indexed by the backend when endpoints are created or updated. |
| **NATS** | A messaging system (with JetStream) used for pub/sub communication in tunneled SyftAI-Space interactions. The aggregator uses NATS to query data sources in parallel. Uses a correlation-ID pattern on a shared `peer_channel` subject. |
| **Organization** | A team grouping with members and roles. Endpoints can be owned by an organization. Members have roles: `owner`, `admin`, or `member`. |
| **OTP** | One-Time Password. Used in the MCP OAuth flow — SyftBox requests authorization, MCP generates an OTP, SyftBox provides it back to complete the auth exchange. |
| **Peer Token** | An opaque token stored in Redis with a 120 s lifetime. Used for NATS pub/sub tunnel authentication between peers. |
| **Refresh Token** | An opaque, long-lived (7 day) token stored in Redis. Used to obtain a new hub access token via `POST /auth/refresh` without re-authenticating. |
| **Satellite Token** | An RS256 JWT (60 s lifetime) issued by the backend's IdP (`GET /token?aud={username}`). Used by satellite services (aggregator, external SyftAI-Space instances) to authenticate requests. Verified locally using the JWKS endpoint. The audience claim must match an active username in the DB. |
| **Slug** | A URL-friendly identifier for an endpoint within an owner's namespace. Example: `alice/my-language-model`. Unique per owner. Auto-generated from the endpoint name if not provided. |
| **Star** | A bookmark/rating mechanism for endpoints, analogous to GitHub stars. Stars count is denormalized: both `EndpointModel.stars_count` and `EndpointStarModel` rows must be kept in sync. |
| **SyftAI-Space** | External data source instances registered in SyftHub that the aggregator can query during RAG workflows. Each Space runs independently and verifies satellite tokens via JWKS. |
| **SyftBox** | An external service that integrates with SyftHub via the MCP OAuth flow. Uses OTP-based authentication to connect to SyftHub's MCP server. |
| **Tenant** | Multi-tenancy unit for the aggregator. Passed via the `X-Tenant-Name` HTTP header to scope aggregator requests to a specific context. |
| **Visibility** | Access control level for an endpoint: `PUBLIC` (anyone, including unauthenticated), `INTERNAL` (any authenticated user), `PRIVATE` (owner/org members only — returns 404, not 403, to hide existence). |
