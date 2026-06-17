# Changelog

All notable changes to the SyftHub TypeScript SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
