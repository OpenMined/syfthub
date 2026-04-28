# SyftHub Backend

The FastAPI service that powers SyftHub — user accounts, organizations, the endpoint registry, and the federated identity provider.

For project-level docs, start at the [repository README](../../README.md) and [`docs/`](../../docs/index.md).

## Running locally

The easiest way is from the repo root:

```bash
make dev
```

To work on just the backend:

```bash
cd components/backend
uv sync --all-extras --dev
uv run uvicorn syfthub.main:app --reload --port 8000
```

API docs are served at <http://localhost:8000/docs>.

## Tests & checks

```bash
uv run pytest                 # tests
uv run ruff check src/ tests/ # lint
uv run ruff format src/ tests/
uv run mypy src/              # types
```

Or run everything from the repo root with `make test` / `make check`.

## Learn more

- [Backend architecture](../../docs/architecture/components/backend.md)
- [Backend API reference](../../docs/api/backend.md)
- [Authentication explained](../../docs/explanation/authentication.md)
