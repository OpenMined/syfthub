# Changelog

All notable changes to the SyftHub TypeScript SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - Unreleased

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

[Unreleased]: https://github.com/OpenMined/syfthub/compare/typescript-sdk/v0.1.0...HEAD
[0.1.0]: https://github.com/OpenMined/syfthub/releases/tag/typescript-sdk/v0.1.0
