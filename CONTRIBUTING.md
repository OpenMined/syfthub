# Contributing to Syfthub

Thank you for your interest in contributing to Syfthub! This document provides guidelines and instructions for contributing.

## Development Setup

1. Fork the repository and clone your fork:
```bash
git clone https://github.com/YOUR_USERNAME/syfthub.git
cd syfthub
```

2. Install uv if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Install the development dependencies:
```bash
uv sync --dev
```

4. Install pre-commit hooks:
```bash
uv run pre-commit install
```

## Code Style

We use [Ruff](https://github.com/astral-sh/ruff) for both linting and formatting. The configuration is in `pyproject.toml`.

Before committing:
- Format your code: `uv run ruff format src/ tests/`
- Check linting: `uv run ruff check src/ tests/`
- Run type checking: `uv run mypy src/`

## Error Handling

### Response Contract

All 4xx/5xx API responses use a consistent shape:

```json
{
  "detail": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Human-readable description",
    "<optional_extra_field>": "..."
  }
}
```

The outer `"detail"` key is Starlette's standard envelope. The inner object is always an `ErrorResponse` with at minimum `code` and `message`.

### Domain Exceptions vs HTTPException

**Raise domain exceptions from services and domain logic.** Never import `HTTPException` from FastAPI in the service or domain layers:

```python
# ✅ CORRECT — raise from service
from syfthub.domain.exceptions import NotFoundError, PermissionDeniedError, ConflictError

raise NotFoundError("User")                       # → 404
raise PermissionDeniedError("Admin role required") # → 403
raise ConflictError("user", "username")            # → 409
```

The `DomainException` handler in `observability/handlers.py` auto-maps these to HTTP responses via `DOMAIN_EXCEPTION_STATUS_MAP`.

**Raise `HTTPException` directly only at the transport boundary** (endpoints / auth dependencies) for errors that are not domain-level:

```python
# ✅ CORRECT — raise at endpoint boundary with structured detail
raise HTTPException(
    status_code=400,
    detail={"code": "MISSING_AUDIENCE", "message": "The 'aud' query parameter is required."},
)
```

```python
# ❌ WRONG — plain string detail
raise HTTPException(status_code=400, detail="Missing audience")
# ❌ WRONG — raising HTTPException from a service
from fastapi import HTTPException
raise HTTPException(status_code=404, detail="User not found")
```

### Adding a New Domain Exception

1. Add the class to `components/backend/src/syfthub/domain/exceptions.py` — follow existing patterns.
2. Add the exception → HTTP status mapping to `DOMAIN_EXCEPTION_STATUS_MAP` in `observability/handlers.py`.
3. Export the new exception from `domain/__init__.py` if callers need it.
4. Add unit tests to `tests/test_domain/test_exceptions.py`.

### Reference Implementation

`auth/router.py:register_user` is the reference for how to handle domain exceptions at the router boundary when you need to catch specific exceptions rather than letting them bubble up.

### What NOT to Do

- **No bare `except Exception: pass`** — always log before swallowing.
- **No raw exception strings in responses** — log server-side, return generic messages to clients.
- **No plain strings in `detail`** — always use `{"code": "...", "message": "..."}`.

## Testing

All code changes should include tests. We use pytest for testing.

- Run all tests: `uv run pytest`
- Run with coverage: `uv run pytest --cov`
- Run specific test file: `uv run pytest tests/test_main.py`

## Commit Messages

Please use clear and descriptive commit messages:
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and pull requests when relevant

## Pull Request Process

1. Create a new branch for your feature or bugfix:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and ensure all tests pass

3. Run the full test suite:
```bash
uv run pre-commit run --all-files
uv run pytest
uv run mypy src/
```

4. Commit your changes with a descriptive message

5. Push to your fork and create a pull request

6. Ensure all CI checks pass

7. Request review from maintainers

## Code Review

All submissions require review. We use GitHub pull requests for this purpose.

## Issues

Feel free to submit issues and enhancement requests.

## Questions?

Feel free to open an issue with your question or reach out to the maintainers.

Thank you for contributing!
