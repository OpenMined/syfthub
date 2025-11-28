# SyftHub

A modern full-stack application with Python backend and React frontend.

[![CI](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml/badge.svg)](https://github.com/IonesioJunior/syfthub/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/node.js-18%2B-green)](https://nodejs.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/badge/uv-package%20manager-orange)](https://github.com/astral-sh/uv)

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS
- **Package Management**: uv (backend) + npm (frontend)
- **Testing**: pytest (backend) + Playwright (frontend)
- **CI/CD**: GitHub Actions with parallel backend/frontend jobs

## Features

### Backend
- Modern Python packaging with [uv](https://github.com/astral-sh/uv)
- FastAPI for high-performance APIs
- SQLAlchemy ORM with PostgreSQL
- JWT authentication with token blacklist
- Code formatting and linting with [Ruff](https://github.com/astral-sh/ruff)
- Static type checking with mypy
- Comprehensive test coverage with pytest (80% threshold)

### Frontend
- React 19 with modern features
- TypeScript for type safety
- Vite for lightning-fast development
- Tailwind CSS + shadcn/ui components
- Playwright for E2E testing
- ESLint + Prettier for code quality

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

2. Start the development environment:
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
│   │   ├── auth/             # JWT authentication & security
│   │   ├── core/             # Configuration
│   │   ├── database/         # Database connection & dependencies
│   │   ├── domain/           # Value objects & exceptions
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── repositories/     # Data access layer
│   │   ├── schemas/          # Pydantic DTOs
│   │   ├── services/         # Business logic
│   │   ├── templates/        # Jinja2 templates
│   │   └── main.py           # FastAPI app entry point
│   ├── tests/                # Backend test suite
│   ├── scripts/              # Utility scripts
│   ├── pyproject.toml        # Dependencies & tool config
│   └── uv.lock               # Locked Python dependencies
├── frontend/                 # React TypeScript frontend
│   ├── src/
│   │   ├── components/       # React components
│   │   │   ├── ui/           # shadcn/ui components
│   │   │   ├── auth/         # Authentication components
│   │   │   └── providers/    # Context providers
│   │   ├── context/          # React context (auth)
│   │   ├── lib/              # Utilities & API clients
│   │   ├── pages/            # Route pages
│   │   ├── assets/           # Static assets (images, etc.)
│   │   ├── styles/           # Global styles
│   │   ├── app.tsx           # App root component
│   │   └── main.tsx          # React entry point
│   ├── __tests__/            # Playwright E2E tests
│   ├── package.json          # Frontend dependencies
│   └── package-lock.json     # Locked npm dependencies
├── nginx/                    # Nginx reverse proxy config
├── docs/                     # Documentation
├── docker-compose.dev.yml    # Development environment
├── docker-compose.prod.yml   # Production environment
├── .github/workflows/        # CI/CD pipelines
├── Makefile                  # Development commands
├── .pre-commit-config.yaml   # Code quality hooks
└── README.md                 # This file
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see LICENSE file for details.
