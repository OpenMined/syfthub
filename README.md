# SyftHub

A registry and discovery platform for AI/ML endpoints with identity provider capabilities.

[![CI](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml/badge.svg)](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/node.js-18%2B-green)](https://nodejs.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/badge/uv-package%20manager-orange)](https://github.com/astral-sh/uv)

## What is SyftHub?

SyftHub is a platform for discovering, managing, and sharing AI/ML endpoints — think of it as **"GitHub for AI endpoints"**. It enables developers and organizations to:

- **Discover** — Browse and search public ML models and data sources, find trending endpoints by stars
- **Share** — Publish your own endpoints with flexible visibility controls (public, internal, private)
- **Collaborate** — Create organizations to manage endpoints as a team with role-based access
- **Integrate** — Use official Python and TypeScript SDKs for programmatic access
- **Federate** — Built-in Identity Provider (IdP) enables satellite services to verify users via RS256-signed tokens

## Core Concepts

### Endpoints

Endpoints are the primary resource in SyftHub. Each endpoint represents either:

| Type | Description |
|------|-------------|
| **Model** | An ML model endpoint (inference, predictions, embeddings, etc.) |
| **Data Source** | A data access endpoint (databases, APIs, datasets, etc.) |

Endpoints support:
- **Visibility**: `public` (anyone), `internal` (authenticated users), `private` (owner/members only)
- **Versioning**: Semantic version tracking (e.g., `0.1.0`)
- **README**: Markdown documentation with syntax highlighting
- **Policies**: Flexible JSON configuration for access policies
- **Connections**: Multiple connection methods with custom configuration
- **Stars**: Community rating system

Endpoints are accessed via GitHub-style URLs: `/{owner}/{endpoint-slug}`

### Organizations

Organizations enable team collaboration on endpoints:

| Role | Permissions |
|------|-------------|
| **Owner** | Full control, can delete organization, manage all members |
| **Admin** | Manage endpoints, add/remove members, update settings |
| **Member** | Access organization endpoints, basic collaboration |

### Identity Provider (IdP)

SyftHub acts as an Identity Provider for satellite services:

1. User authenticates with SyftHub (gets HS256 access token)
2. User requests a satellite token for a specific service (audience)
3. Hub issues RS256-signed short-lived token (60 seconds)
4. Satellite service verifies token using Hub's JWKS endpoint (`/.well-known/jwks.json`)
5. No API call to Hub needed for verification — fully distributed

This enables federated authentication across multiple services with a single SyftHub login.

### Stars

Users can star endpoints to show appreciation and help surface popular content. The trending page ranks endpoints by star count.

## Features

### Endpoint Management
- Create, update, and delete endpoints with full CRUD support
- Auto-generated URL-safe slugs from endpoint names
- Markdown README rendering with syntax highlighting
- Flexible policy and connection configuration (JSON)
- Star/unstar endpoints with trending discovery

### Organization Collaboration
- Create organizations with unique slugs
- Invite members with role-based permissions
- Shared endpoint ownership across team members
- Protected operations (cannot remove last owner)

### Identity Provider
- JWKS endpoint for distributed key verification
- RS256-signed satellite tokens with audience scoping
- Configurable audience allowlist
- Server-side token verification endpoint

### Authentication & Security
- JWT-based authentication (HS256 for hub, RS256 for satellites)
- Access + refresh token flow with configurable expiry
- Token blacklist for secure logout
- Argon2 password hashing
- Role-based access control (admin, user, guest)

### SDKs
- Official Python SDK (`syfthub-sdk`)
- Official TypeScript SDK (`@syfthub/sdk`)
- Full API parity with language-appropriate conventions

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    NGINX (Reverse Proxy)                         │
│                 Port 80/443 (prod) | 8080 (dev)                  │
└─────────────────────┬───────────────────────┬───────────────────┘
                      │                       │
         ┌────────────▼────────────┐  ┌───────▼────────────┐
         │   Frontend (React 19)   │  │  Backend (FastAPI) │
         │   TypeScript + Vite     │  │  Python 3.12       │
         │   Tailwind + shadcn/ui  │  │  SQLAlchemy ORM    │
         └────────────┬────────────┘  └───────┬────────────┘
                      │                       │
                      │    @syfthub/sdk       │
                      └───────────────────────┤
                                              │
                      ┌───────────────────────┴────────────────┐
                      │                                        │
              ┌───────▼───────┐                    ┌───────────▼───────┐
              │  PostgreSQL   │                    │      Redis        │
              │  Database     │                    │  Sessions/Cache   │
              └───────────────┘                    └───────────────────┘
```

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI + SQLAlchemy + PostgreSQL |
| **Frontend** | React 19 + TypeScript + Vite + Tailwind CSS |
| **Package Management** | uv (backend) + npm (frontend) |
| **Testing** | pytest (backend) + Playwright (frontend) |
| **CI/CD** | GitHub Actions with parallel jobs |

## SDKs

SyftHub provides official SDKs for Python and TypeScript. See the [SDK documentation](./sdk/README.md) for full details.

### Python SDK

```bash
pip install syfthub-sdk
# or
uv add syfthub-sdk
```

```python
from syfthub_sdk import SyftHubClient

client = SyftHubClient(base_url="https://hub.syft.com")

# Authentication
client.auth.login(email="alice@example.com", password="secret123")

# Browse public endpoints
for endpoint in client.hub.browse():
    print(f"{endpoint.name}: {endpoint.description}")

# Get trending endpoints
trending = client.hub.trending(min_stars=5)

# Create an endpoint
endpoint = client.my_endpoints.create({
    "name": "My ML Model",
    "type": "model",
    "visibility": "public",
    "description": "A powerful classification model"
})

# Star an endpoint
client.hub.star("alice/awesome-model")
```

### TypeScript SDK

```bash
npm install @syfthub/sdk
# or
yarn add @syfthub/sdk
```

```typescript
import { SyftHubClient } from '@syfthub/sdk';

const client = new SyftHubClient({ baseUrl: 'https://hub.syft.com' });

// Authentication
await client.auth.login({ email: 'alice@example.com', password: 'secret123' });

// Browse public endpoints
for await (const endpoint of client.hub.browse()) {
  console.log(`${endpoint.name}: ${endpoint.description}`);
}

// Create an endpoint
const endpoint = await client.myEndpoints.create({
  name: 'My Data Source',
  type: 'data_source',
  visibility: 'private',
  description: 'Internal company data'
});
```

## API Overview

**Base URL**: `/api/v1`

| Group | Endpoints | Description |
|-------|-----------|-------------|
| **Auth** | `POST /auth/register`<br>`POST /auth/login`<br>`POST /auth/refresh`<br>`GET /auth/me` | User authentication |
| **Users** | `GET /users/me`<br>`PUT /users/me`<br>`GET /users/{id}` | User management |
| **Endpoints** | `POST /endpoints`<br>`GET /endpoints`<br>`GET /endpoints/public`<br>`GET /endpoints/trending`<br>`POST /endpoints/{id}/star` | Endpoint CRUD & discovery |
| **Organizations** | `POST /organizations`<br>`GET /organizations`<br>`POST /organizations/{id}/members` | Organization management |
| **IdP** | `GET /token?aud={service}`<br>`GET /.well-known/jwks.json`<br>`POST /verify` | Identity provider |
| **Public** | `GET /{owner}/{slug}` | GitHub-style endpoint access |

Full API documentation available at `/docs` (Swagger UI) when running the server.

## Installation

### Prerequisites

- **Docker** (recommended) or:
  - **Backend**: Python 3.9+ and [uv](https://github.com/astral-sh/uv)
  - **Frontend**: Node.js 18+ and npm

Install uv (for local development):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Quick Start

1. Clone the repository:
```bash
git clone https://github.com/IonesioJunior/syfthub.git
cd syfthub
```

2. Copy environment template:
```bash
cp .env.example .env
```

3. Start the development environment:
```bash
make dev
```

This starts all services (backend, frontend, PostgreSQL, Redis) via Docker.

## Usage

### Development Mode (Docker - Recommended)

Start the full-stack environment with one command:

```bash
make dev      # Start all services
make logs     # View container logs
make stop     # Stop all services
```

The application will be available at:
- **App**: http://localhost
- **API Documentation**: http://localhost/docs
- **Database**: PostgreSQL on localhost:5432 (user: `syfthub`, password: `syfthub_dev_password`)

### Local Development (Without Docker)

For backend-only local development:

```bash
cd backend
uv sync --all-extras --dev
uv run uvicorn syfthub.main:app --reload --port 8000
```

For frontend-only local development:

```bash
cd frontend
npm install
npm run dev
```

### Production Mode

```bash
docker compose -f docker-compose.prod.yml up -d
```

## Development

### Running Tests

```bash
make test     # Run all tests (backend + frontend)
```

Or run separately:

```bash
# Backend tests
cd backend && uv run python -m pytest

# Frontend tests (Playwright E2E)
cd frontend && npm test
```

### Code Quality

```bash
make check    # Run all code quality checks
```

This runs:
- **Backend**: Ruff linting, Ruff formatting, mypy type checking
- **Frontend**: ESLint, TypeScript type checking

### Manual Quality Commands

**Backend:**
```bash
cd backend
uv run ruff check src/ tests/       # Linting
uv run ruff format src/ tests/      # Formatting
uv run mypy src/                    # Type checking
```

**Frontend:**
```bash
cd frontend
npm run lint                        # ESLint
npm run format                      # Prettier
npm run typecheck                   # TypeScript
```

### Available Make Commands

```bash
make help     # Show available commands
make dev      # Start development environment
make stop     # Stop all services
make test     # Run all tests
make check    # Run code quality checks
make logs     # View container logs
```

## Project Structure

```
syfthub/
├── backend/                  # Python FastAPI backend
│   ├── src/syfthub/          # Main Python package
│   │   ├── api/              # FastAPI routes & endpoints
│   │   │   └── endpoints/    # Route handlers (users, endpoints, orgs, tokens)
│   │   ├── auth/             # Authentication & security
│   │   │   ├── security.py   # JWT tokens, password hashing
│   │   │   ├── keys.py       # RSA key management for IdP
│   │   │   └── satellite_tokens.py  # Satellite token logic
│   │   ├── core/             # Configuration
│   │   ├── database/         # Database connection & dependencies
│   │   ├── domain/           # Value objects & exceptions
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── repositories/     # Data access layer (Repository pattern)
│   │   ├── schemas/          # Pydantic request/response DTOs
│   │   ├── services/         # Business logic layer
│   │   ├── templates/        # Jinja2 templates (endpoint HTML views)
│   │   └── main.py           # FastAPI app entry point
│   ├── tests/                # Backend test suite
│   ├── scripts/              # Utility scripts
│   ├── pyproject.toml        # Dependencies & tool config
│   └── uv.lock               # Locked Python dependencies
├── frontend/                 # React TypeScript frontend
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── ui/           # shadcn/ui base components
│   │   │   ├── auth/         # Authentication (login, register modals)
│   │   │   ├── settings/     # Settings tabs (profile, security, etc.)
│   │   │   └── chat/         # Chat interface components
│   │   ├── context/          # React Context providers (auth, modals)
│   │   ├── hooks/            # Custom hooks (useAPI, useForm)
│   │   ├── lib/              # Utilities, SDK client, types
│   │   ├── layouts/          # Layout components
│   │   ├── pages/            # Route pages (lazy-loaded)
│   │   ├── assets/           # Static assets (fonts, images)
│   │   ├── styles/           # Global CSS & design tokens
│   │   ├── app.tsx           # App root with routing
│   │   └── main.tsx          # React entry point
│   ├── __tests__/            # Playwright E2E tests
│   ├── package.json          # Frontend dependencies
│   └── vite.config.ts        # Vite build configuration
├── sdk/                      # Official client SDKs
│   ├── python/               # Python SDK (syfthub-sdk)
│   │   ├── src/syfthub_sdk/  # SDK source code
│   │   ├── tests/            # SDK tests
│   │   └── pyproject.toml    # SDK dependencies
│   ├── typescript/           # TypeScript SDK (@syfthub/sdk)
│   │   ├── src/              # SDK source code
│   │   ├── dist/             # Built output
│   │   └── package.json      # SDK dependencies
│   └── README.md             # SDK documentation
├── nginx/                    # Nginx reverse proxy config
│   ├── nginx.dev.conf        # Development configuration
│   └── nginx.prod.conf       # Production configuration (SSL)
├── docs/                     # Documentation
│   ├── authentication.md     # Auth system documentation
│   └── pki-workflow.md       # PKI/IdP workflow documentation
├── docker-compose.dev.yml    # Development environment
├── docker-compose.prod.yml   # Production environment
├── .github/workflows/        # CI/CD pipelines
├── Makefile                  # Development commands
├── .pre-commit-config.yaml   # Code quality hooks
├── .env.example              # Environment template
└── README.md                 # This file
```

## Authentication

SyftHub uses a dual-token authentication system:

### Hub Tokens (HS256)
- Standard JWT access + refresh tokens
- Access tokens expire in 30 minutes (configurable)
- Refresh tokens expire in 7 days (configurable)
- Token blacklist for secure logout

### Satellite Tokens (RS256)
- Short-lived tokens for external services (60 seconds)
- Signed with RSA private key
- Services verify using JWKS endpoint without calling Hub API
- Audience-scoped for specific services

For detailed authentication documentation, see [docs/authentication.md](./docs/authentication.md).

For PKI and IdP workflow details, see [docs/pki-workflow.md](./docs/pki-workflow.md).

## Environment Variables

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SECRET_KEY` | JWT signing secret (HS256) | Required |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `ALLOWED_AUDIENCES` | Comma-separated satellite service names | `syftai-space` |
| `AUTO_GENERATE_RSA_KEYS` | Auto-generate RSA keys in dev | `true` |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Issue Labeling

SyftHub uses an automated issue labeling system to help organize and prioritize issues. When you create an issue, labels are automatically applied based on the content. See [.github/LABELING.md](.github/LABELING.md) for details about the labeling system.

## License

MIT License - see LICENSE file for details.
