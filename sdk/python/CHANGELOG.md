# Changelog

All notable changes to the SyftHub Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-06-17

### Added

- `syftai.query_data_source` now authenticates and pays like the aggregator:
  - Auto-mints a satellite token (audience = endpoint owner username) when an
    owner is known via the new `owner_username` argument or
    `EndpointRef.owner_username`; falls back to a guest token.
  - Accepts a pre-minted `authorization_token` to send as `Authorization: Bearer`.
  - New `pay` flag settles an MPP `402 Payment Required` challenge via the Hub
    wallet (`/api/v1/wallet/pay`) and retries with the `X-Payment` credential.

### Fixed

- `syftai.query_data_source` now parses the canonical SyftAI-Space response
  shape (`references.documents` with `similarity_score`), so documents are no
  longer silently dropped. A legacy top-level `documents` list is still honoured.

## [0.2.0] - 2026-06-17

### Added

- `aggregators` resource for managing user aggregator configurations
- `api_tokens` resource for creating and managing personal access tokens
- Multi-turn message history support in the `chat` resource
- Heartbeat integration tests

### Changed

- Migrated accounting to the Machine Payments Protocol (MPP) billing flow
- Reworked authentication: satellite/transaction token handling and simplified
  token management
- Expanded chat streaming event handling and response models

### Removed

- **BREAKING:** Removed the Organization entity (organization accounts,
  `OrganizationRole`, `organization_id`, and `owner_type`). Every endpoint is
  now owned by a single user.

## [0.1.1] - 2026-01-27

### Added

- Initial release of the SyftHub Python SDK
- `SyftHubClient` class for API interactions
- Authentication via API key
- Resource APIs:
  - `auth` - Authentication and token management
  - `users` - User management and profiles
  - `hub` - Endpoint discovery and search
  - `chat` - Chat completions API
  - `accounting` - Usage tracking and billing information
  - `my_endpoints` - Manage user's own endpoints
  - `syftai` - SyftAI-specific features
- Automatic pagination handling with async iterator support
- Comprehensive error handling with typed exceptions:
  - `SyftHubError` - Base exception class
  - `AuthenticationError` - Authentication failures
  - `RateLimitError` - Rate limit exceeded
  - `NotFoundError` - Resource not found
  - `ValidationError` - Request validation failures
- Full type hints for IDE support and type checking
- Async HTTP client built on `httpx`
- Pydantic models for request/response validation

### Dependencies

- Python 3.10+
- httpx >= 0.27
- pydantic >= 2.0

[Unreleased]: https://github.com/OpenMined/syfthub/compare/python-sdk/v0.1.1...HEAD
[0.1.1]: https://github.com/OpenMined/syfthub/releases/tag/python-sdk/v0.1.1
