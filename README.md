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
- Comprehensive test coverage with pytest

### Frontend
- React 19 with modern features
- TypeScript for type safety
- Vite for lightning-fast development
- Tailwind CSS + shadcn/ui components
- Playwright for E2E testing
- ESLint + Prettier for code quality

## Installation

### Prerequisites

- **Backend**: Python 3.9+ and [uv](https://github.com/astral-sh/uv)
- **Frontend**: Node.js 18+ and npm

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Quick Start

1. Clone the repository:
```bash
git clone https://github.com/IonesioJunior/syfthub.git
cd syfthub
```

2. Install all dependencies:
```bash
# Backend dependencies
make install-dev

# Frontend dependencies
make frontend-install
```

3. Install pre-commit hooks:
```bash
make install-dev  # This includes pre-commit setup
```

## Usage

### Development Mode

**Option 1: Full-Stack Docker Development (Recommended)**

Start everything with one command using Docker:

```bash
# Start backend + frontend + database + redis
make docker-dev-fullstack

# View logs
make docker-logs-fullstack

# Stop everything
make docker-down-fullstack
```

**Option 2: Local Development**

Start both backend and frontend locally:

```bash
# Terminal 1: Start backend server (port 8000)
make dev

# Terminal 2: Start frontend dev server (port 3000)
make frontend-dev
```

The application will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Database**: PostgreSQL on localhost:5432 (Docker only)
- **Redis**: localhost:6379 (Docker only)

### Production Mode

```bash
# Build frontend
make frontend-build

# Run backend in production mode
make run
```

## Development

### Running Tests

**Backend Tests:**
```bash
make test              # Run backend tests
make test-cov          # Run backend tests with coverage
```

**Frontend Tests:**
```bash
make frontend-test     # Run Playwright E2E tests
```

### Code Quality

**Backend:**
```bash
make lint              # Run Ruff linting
make format            # Format code with Ruff
make type-check        # Run mypy type checking
make check             # Run all backend checks
```

**Frontend:**
```bash
make frontend-lint     # Run ESLint
make frontend-format   # Format with Prettier
make frontend-typecheck # TypeScript type checking
```

**Both:**
```bash
make pre-commit        # Run all pre-commit hooks
```

### Building

```bash
make build             # Build backend package
make frontend-build    # Build frontend for production
```

### Docker Development Commands

```bash
# Full-stack development
make docker-dev-fullstack     # Start all services (recommended)
make docker-down-fullstack    # Stop all services
make docker-logs-fullstack    # View logs for all services
make docker-ps-fullstack      # Show container status

# Backend-only development
make docker-dev               # Start only backend services
make docker-down              # Stop backend services
make docker-logs              # View backend logs
```

### Available Make Commands

Run `make help` to see all available commands for both backend and frontend.

## Project Structure

```
syfthub/
├── backend/                # Python FastAPI backend
│   ├── src/
│   │   └── syfthub/       # Main Python package
│   │       ├── api/       # FastAPI routes
│   │       ├── database/  # Database models & connection
│   │       ├── repositories/ # Data access layer
│   │       ├── schemas/   # Pydantic models
│   │       ├── services/  # Business logic
│   │       └── main.py    # FastAPI app entry point
│   ├── tests/             # Backend test suite
│   ├── scripts/           # Utility scripts
│   ├── pyproject.toml     # Backend dependencies & config
│   └── uv.lock           # Locked Python dependencies
├── frontend/              # React TypeScript frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   │   ├── ui/       # shadcn/ui components
│   │   │   └── auth/     # Authentication components
│   │   ├── lib/          # Utilities & API clients
│   │   ├── pages/        # Route pages
│   │   ├── styles/       # Global styles
│   │   └── main.tsx      # React app entry point
│   ├── public/           # Static assets
│   ├── __tests__/        # Frontend tests
│   ├── package.json      # Frontend dependencies
│   └── package-lock.json # Locked npm dependencies
├── .github/
│   └── workflows/        # CI/CD pipelines
├── Makefile              # Development commands
├── .pre-commit-config.yaml # Code quality hooks
└── README.md             # This file
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see LICENSE file for details.
