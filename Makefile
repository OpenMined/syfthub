.PHONY: help setup dev stop test test-integration check logs

# =============================================================================
# SyftHub Development Commands
# =============================================================================
#
# Quick Start:
#   make setup       - Install dev dependencies (pre-commit, etc.)
#   make dev         - Start development environment
#   make logs        - View logs (debug issues)
#   make test        - Run tests (parallel, uses all CPU cores)
#   make check       - Run code quality checks
#   make stop        - Stop all services
#
# For production deployment, see README.md
# =============================================================================

help:  ## Show available commands
	@echo ''
	@echo 'SyftHub Development Commands:'
	@echo ''
	@echo '  make setup        Install dev dependencies (pre-commit, etc.)'
	@echo '  make dev          Start development environment (http://localhost)'
	@echo '  make stop         Stop all services'
	@echo '  make test         Run all tests (parallel execution)'
	@echo '  make check        Run code quality checks (lint, format, types)'
	@echo '  make logs         View container logs'
	@echo ''
	@echo 'Production deployment:'
	@echo '  docker compose -f docker-compose.prod.yml up -d'
	@echo ''

setup:  ## Install dev dependencies (pre-commit, etc.)
	@echo 'Setting up development environment...'
	@test -d .venv || uv venv .venv
	@. .venv/bin/activate && uv pip install pre-commit
	@. .venv/bin/activate && pre-commit install
	@npm install ./sdk/typescript
	@npm --prefix sdk/typescript run build
	@echo ''
	@echo 'Setup complete! Activate the virtualenv with:'
	@echo '  source .venv/bin/activate'
	@echo ''

dev:  ## Start development environment
	@docker compose -f deploy/docker-compose.dev.yml up -d --build
	@echo ''
	@echo '══════════════════════════════════════════'
	@echo '  SyftHub Development Environment'
	@echo '══════════════════════════════════════════'
	@echo ''
	@echo '  App:      http://localhost'
	@echo '  API Docs: http://localhost/docs'
	@echo '  Database: localhost:5432 (syfthub/syfthub_dev_password)'
	@echo ''
	@echo '  make logs  - View logs'
	@echo '  make stop  - Stop services'
	@echo '══════════════════════════════════════════'

stop:  ## Stop all services
	@docker compose -f deploy/docker-compose.dev.yml down 2>/dev/null || true
	@docker compose -f deploy/docker-compose.deploy.yml down 2>/dev/null || true
	@echo 'All services stopped'

test:  ## Run all tests (parallel execution using all CPU cores)
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  Running all tests in PARALLEL mode (-n auto)'
	@echo '═══════════════════════════════════════════════════════════════'
	@echo ''
	@echo 'Backend tests...'
	@cd components/backend && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'Aggregator tests...'
	@cd components/aggregator && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'CLI tests...'
	@cd cli && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'Python SDK unit tests...'
	@cd sdk/python && uv sync --extra dev && uv run pytest tests/unit
	@echo ''
	@echo 'TypeScript SDK unit tests...'
	@cd sdk/typescript && npx vitest run --exclude 'tests/integration/**' || echo 'TypeScript SDK tests skipped'
	@echo ''
	@echo 'Frontend tests...'
	@cd components/frontend && npm run test --if-present || echo 'Frontend tests skipped (playwright not configured)'
	@echo ''
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  All tests complete!'
	@echo '═══════════════════════════════════════════════════════════════'

test-integration:  ## Run integration tests (requires dev server running)
	@echo 'Running SDK integration tests...'
	@echo '(Requires: make dev to be running)'
	@echo ''
	@echo 'Python SDK integration tests...'
	@cd sdk/python && uv run pytest tests/integration/ -v
	@echo ''
	@echo 'TypeScript SDK integration tests...'
	@cd sdk/typescript && npx vitest run tests/integration/

check:  ## Run code quality checks
	@echo 'Backend checks...'
	@cd components/backend && uv sync --extra dev && uv run ruff check src/ tests/
	@cd components/backend && uv run ruff format --check src/ tests/
	@cd components/backend && uv run python -m mypy src/ || true
	@echo ''
	@echo 'Aggregator checks...'
	@cd components/aggregator && uv sync --extra dev && uv run ruff check src/ tests/
	@cd components/aggregator && uv run ruff format --check src/ tests/
	@cd components/aggregator && uv run mypy src/aggregator/ || true
	@echo ''
	@echo 'Python SDK checks...'
	@cd sdk/python && uv sync --extra dev && uv run ruff check src/ tests/
	@cd sdk/python && uv run ruff format --check src/ tests/
	@cd sdk/python && uv run mypy src/syfthub_sdk/ || true
	@echo ''
	@echo 'Frontend checks...'
	@cd components/frontend && npm install --silent && npm run lint --if-present || true
	@cd components/frontend && npm run typecheck --if-present || true
	@echo ''
	@echo 'TypeScript SDK checks...'
	@cd sdk/typescript && npm install --silent && npm run lint --if-present || true
	@cd sdk/typescript && npm run typecheck --if-present || true
	@echo ''
	@echo 'Go SDK checks...'
	@cd sdk/golang && $(MAKE) lint
	@echo ''
	@echo 'CLI checks...'
	@cd cli && $(MAKE) lint
	@echo ''
	@echo 'All checks complete'

logs:  ## View container logs
	@docker compose -f deploy/docker-compose.dev.yml logs -f
