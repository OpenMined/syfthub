# Changelog

All notable changes to the SyftHub Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
