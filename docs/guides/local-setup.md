# Local Development Setup

## Prerequisites

**Option A — Docker (recommended):**
- Docker and Docker Compose

**Option B — Manual:**
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- Node.js 18+ and npm
- PostgreSQL 15+
- Redis
- Meilisearch

## Quick Start

```bash
git clone https://github.com/OpenMined/syfthub.git
cd syfthub
cp .env.example .env
make dev
```

## Services

| Service | URL / Port |
|---------|-----------|
| App (Nginx) | http://localhost:8080 |
| API docs (Swagger) | http://localhost:8080/docs |
| PostgreSQL | localhost:5432 (user: `syfthub`) |
| Redis | localhost:6379 |
| Meilisearch | localhost:7700 |

## Dev Commands

| Command | Description |
|---------|-------------|
| `make dev` | Start all services |
| `make stop` | Stop all services |
| `make logs` | Tail service logs |
| `make test` | Run all tests |
| `make check` | Run all linting, formatting, and type checks |

## Running Without Docker

### Backend

```bash
cd components/backend
uv sync --all-extras --dev
uv run uvicorn syfthub.main:app --reload --port 8000
```

### Frontend

```bash
cd components/frontend
npm install
npm run dev
```

The frontend dev server runs on port 3000 and proxies API requests to the backend.

## Code Quality

### Backend

```bash
ruff check .          # Lint
ruff format .         # Format
mypy .                # Type check
```

### Frontend

```bash
npx eslint .          # Lint
npx prettier --check . # Format check
npx tsc --noEmit      # Type check
```

## Database Migrations (Alembic)

All migration commands run from `components/backend/`.

```bash
# Generate a new migration from model changes
alembic revision --autogenerate -m "description of change"

# Apply all pending migrations
alembic upgrade head

# Roll back the last migration
alembic downgrade -1
```
