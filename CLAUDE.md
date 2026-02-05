# Agent Guidelines for SyftHub

This file provides guidelines for AI agents working on the SyftHub codebase.

## Project Overview

SyftHub is a privacy-preserving AI model and data sharing platform with:
- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS
- **SDKs**: Python and TypeScript clients
- **Aggregator**: RAG orchestration service (Python 3.11+)
- **MCP**: Model Context Protocol server (Python 3.12+)

## Build, Test, and Lint Commands

### Root Level (Makefile)
```bash
make setup      # Install dev dependencies (pre-commit, uv venv)
make dev        # Start development environment (http://localhost:8080)
make stop       # Stop all Docker services
make test       # Run all tests across all components
make check      # Run all code quality checks
make logs       # View container logs
```

### Backend (FastAPI)
```bash
cd backend

# Run tests
uv run pytest                              # Run all tests
uv run pytest tests/test_main.py           # Run specific test file
uv run pytest -k test_name                 # Run specific test
uv run pytest -m "not slow"                # Exclude slow tests

# Lint and format
uv run ruff check src/ tests/              # Check linting
uv run ruff check --fix src/ tests/        # Auto-fix issues
uv run ruff format src/ tests/             # Format code
uv run mypy src/                           # Type checking
```

### Frontend (React/TypeScript)
```bash
cd frontend

# Run tests
npm run test                               # Run unit tests (vitest)
npm run test:unit:watch                    # Run tests in watch mode
npm run test:e2e                         # Run E2E tests (playwright)

# Lint and format
npm run lint                               # ESLint check
npm run lint:fix                           # Auto-fix ESLint issues
npm run typecheck                          # TypeScript check
npm run format                             # Prettier format
```

### Python SDK
```bash
cd sdk/python
uv run pytest                              # Run tests
uv run ruff check --fix src/ tests/        # Lint and fix
uv run ruff format src/ tests/             # Format
uv run mypy src/syfthub_sdk                # Type check
```

### TypeScript SDK
```bash
cd sdk/typescript
npm run test:run                           # Run tests
npm run lint:fix                           # Lint and fix
npm run format                             # Format
npm run typecheck                          # Type check
```

### Aggregator
```bash
cd aggregator
uv run pytest                              # Run tests
uv run ruff check --fix src/ tests/        # Lint and fix
uv run mypy src/                           # Type check
```

### MCP
```bash
cd mcp
uv run python server.py                    # Start server
```

## Code Style Guidelines

### Python

**Formatting & Linting:**
- Use **Ruff** for both linting and formatting
- Line length: 88 characters (backend, SDK)
- Line length: 100 characters (aggregator)
- Use double quotes for strings
- 4-space indentation
- Trailing commas enabled

**Type Hints:**
- Use `typing` imports: `from typing import Annotated, Any, Optional`
- Prefer `from collections.abc` for abstract base classes
- Use `Annotated` for FastAPI dependencies
- Enable strict mypy checking
- SQLAlchemy models have mypy errors ignored (complex typing)

**Naming Conventions:**
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private attributes: `_leading_underscore`
- Test files: `test_*.py`
- Test functions: `test_*`

**Imports:**
```python
# Standard library
import asyncio
from pathlib import Path

# Third-party
import httpx
from fastapi import FastAPI

# First-party (known-first-party = syfthub)
from syfthub.models.user import User
```

**Error Handling:**
- Use FastAPI's `HTTPException` for HTTP errors
- Use `structlog` for structured logging
- Log at appropriate levels: `logger.info()`, `logger.error()`
- Include context in log messages

### TypeScript/React

**Formatting:**
- Use **Prettier** with 100 char line width
- Single quotes (including JSX)
- Semicolons required
- 2-space indentation
- Trailing commas: none

**Linting:**
- ESLint with strict TypeScript rules
- SonarJS for code quality
- Unicorn plugin for best practices

**Naming Conventions:**
- Components: `PascalCase` (e.g., `UserProfile`)
- Functions/variables: `camelCase` (e.g., `getUserData`)
- Constants: `UPPER_SNAKE_CASE` for true constants
- Types/Interfaces: `PascalCase` (e.g., `UserData`)
- Hook files: `use*.ts` (e.g., `useAuth.ts`)
- Test files: `*.test.ts` or `*.spec.ts`

**Imports:**
```typescript
// React first
import { lazy, useState } from 'react';

// Third-party libraries
import { QueryClient } from '@tanstack/react-query';

// Absolute imports (~/* = root, @/* = src)
import { Button } from '@/components/ui/button';
import { config } from '~/config';

// Relative imports last
import { utils } from './utils';
```

**React Patterns:**
- Use functional components with hooks
- Lazy load pages for code splitting
- Use React Query for server state
- Use Zustand for client state
- Use React Hook Form + Zod for forms

**Error Handling:**
- Use Error Boundaries for component errors
- Return error responses from API calls
- Use toast notifications for user feedback

## Git Workflow

**Pre-commit Hooks:**
```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Hooks run:
- Trailing whitespace removal
- Ruff lint/format (Python)
- mypy type checking
- ESLint (Frontend)
- Prettier (Frontend)

**Commit Messages:**
- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Fix bug" not "Fixes bug")
- Limit first line to 72 characters
- Reference issues when relevant

## Testing Guidelines

**Python:**
- Use pytest with fixtures
- Use `pytest-asyncio` for async tests
- Mock external dependencies
- Aim for 80%+ coverage (enforced)
- Use markers: `@pytest.mark.slow`, `@pytest.mark.integration`

**TypeScript:**
- Unit tests: Vitest
- E2E tests: Playwright
- Test components with React Testing Library
- Mock API calls with MSW

## Docker Services

Development uses Docker Compose:
```bash
docker compose -f docker-compose.dev.yml up -d
```

Services:
- **App**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs
- **Database**: localhost:5432 (syfthub/syfthub_dev_password)

## Environment Variables

Copy `.env.example` to `.env` and configure:
- Backend: `backend/.env`
- MCP: `mcp/.env`

Never commit `.env` files or secrets to the repository.

## Key Files

- `backend/src/syfthub/main.py` - FastAPI application entry
- `backend/src/syfthub/api/router.py` - API routes
- `frontend/src/app.tsx` - React application root
- `frontend/src/components/` - Reusable UI components
- `sdk/python/src/syfthub_sdk/` - Python SDK
- `sdk/typescript/src/` - TypeScript SDK
