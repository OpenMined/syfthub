# Changelog

All notable changes to the SyftHub TypeScript SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-06-17

### Added

- `client.search.query(...)` — retrieval-only search via the Aggregator,
  symmetric to `client.chat.complete(...)`. Queries data sources for relevant
  documents without invoking a model. Satellite-token auth and MPP payment are
  handled server-side by the aggregator exactly as for chat. Resolves to a
  `SearchResponse` with a `documents` array (`SearchDocument`) plus per-source
  `retrievalInfo` and timing `metadata`. The underlying primitive is
  `client.chat.retrieve(...)`. New types: `SearchQueryOptions`, `SearchResponse`,
  `SearchDocument`.

## [0.2.1] - 2026-06-17

### Added

- `syftai.queryDataSource` now authenticates and pays like the aggregator:
  - Auto-mints a satellite token (audience = endpoint owner username) when an
    owner is known via the new `ownerUsername` option or
    `EndpointRef.ownerUsername`; falls back to a guest token.
  - Accepts a pre-minted `authorizationToken` to send as `Authorization: Bearer`.
  - New `pay` option settles an MPP `402 Payment Required` challenge via the Hub
    wallet (`/api/v1/wallet/pay`) and retries with the `X-Payment` credential.

### Fixed

- `syftai.queryDataSource` now parses the canonical SyftAI-Space response shape
  (`references.documents` with `similarity_score`), so documents are no longer
  silently dropped. A legacy top-level `documents` list is still honoured.

## [0.2.0] - 2026-06-17

### Added

- `aggregators` resource for managing user aggregator configurations
- `apiTokens` resource for creating and managing personal access tokens
- `agent` resource and agent models for the agent protocol
- Multi-turn message history support in the `chat` resource

### Changed

- Replaced the legacy accounting service with the Machine Payments Protocol (MPP)
  billing flow
- Reworked authentication: satellite/transaction token handling and simplified
  token management
- Expanded chat streaming event handling and response models

### Removed

- **BREAKING:** Removed the Organization entity (organization accounts,
  `OrganizationRole`, `organizationId`, and `ownerType`). Every endpoint is now
  owned by a single user.

## [0.1.1] - 2026-01-27

### Added

- Initial release of the SyftHub TypeScript SDK
- `SyftHubClient` class for API interactions
- Authentication via API key
- Resource APIs:
  - `auth` - Authentication and token management
  - `users` - User management and profiles
  - `hub` - Endpoint discovery and search
  - `chat` - Chat completions API
  - `accounting` - Usage tracking and billing information
  - `myEndpoints` - Manage user's own endpoints
  - `syftai` - SyftAI-specific features
- Automatic pagination handling with async iterators
- Comprehensive error handling with typed exceptions:
  - `SyftHubError` - Base error class
  - `AuthenticationError` - Authentication failures
  - `RateLimitError` - Rate limit exceeded
  - `NotFoundError` - Resource not found
  - `ValidationError` - Request validation failures
- Full TypeScript type definitions
- Dual module support (ESM and CommonJS)
- Tree-shakeable exports

### Compatibility

- Node.js 18.0.0+
- Modern browsers with ES2022 support
- TypeScript 5.0+

[Unreleased]: https://github.com/OpenMined/syfthub/compare/typescript-sdk/v0.1.1...HEAD
[0.1.1]: https://github.com/OpenMined/syfthub/releases/tag/typescript-sdk/v0.1.1
