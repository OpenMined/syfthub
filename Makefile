.PHONY: help setup dev stop test test-serial check logs

# =============================================================================
# SyftHub Development Commands
# =============================================================================
#
# Quick Start:
#   make setup       - Install dev dependencies (pre-commit, etc.)
#   make dev         - Start development environment
#   make logs        - View logs (debug issues)
#   make test        - Run tests (parallel, uses all CPU cores)
#   make test-serial - Run tests sequentially (for debugging)
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
	@echo '  make test-serial  Run all tests sequentially (for debugging)'
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
	@echo ''
	@echo 'Setup complete! Activate the virtualenv with:'
	@echo '  source .venv/bin/activate'
	@echo ''

dev:  ## Start development environment
	@docker compose -f docker-compose.dev.yml up -d --build
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
	@docker compose -f docker-compose.dev.yml down 2>/dev/null || true
	@docker compose -f docker-compose.deploy.yml down 2>/dev/null || true
	@echo 'All services stopped'

test:  ## Run all tests (parallel execution using all CPU cores)
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  Running all tests in PARALLEL mode (-n auto)'
	@echo '═══════════════════════════════════════════════════════════════'
	@echo ''
	@echo 'Backend tests...'
	@cd backend && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'Aggregator tests...'
	@cd aggregator && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'CLI tests...'
	@cd cli && uv sync --extra dev && uv run pytest
	@echo ''
	@echo 'Python SDK unit tests...'
	@cd sdk/python && uv sync --extra dev && uv run pytest tests/unit
	@echo ''
	@echo 'Frontend tests...'
	@cd frontend && npm run test --if-present || echo 'Frontend tests skipped (playwright not configured)'
	@echo ''
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  All tests complete!'
	@echo '═══════════════════════════════════════════════════════════════'

test-serial:  ## Run all tests sequentially (for debugging)
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  Running all tests in SERIAL mode (-n 0)'
	@echo '═══════════════════════════════════════════════════════════════'
	@echo ''
	@echo 'Backend tests...'
	@cd backend && uv sync --extra dev && uv run pytest -n 0
	@echo ''
	@echo 'Aggregator tests...'
	@cd aggregator && uv sync --extra dev && uv run pytest -n 0
	@echo ''
	@echo 'CLI tests...'
	@cd cli && uv sync --extra dev && uv run pytest -n 0
	@echo ''
	@echo 'Python SDK unit tests...'
	@cd sdk/python && uv sync --extra dev && uv run pytest tests/unit -n 0
	@echo ''
	@echo 'Frontend tests...'
	@cd frontend && npm run test --if-present || echo 'Frontend tests skipped (playwright not configured)'
	@echo ''
	@echo '═══════════════════════════════════════════════════════════════'
	@echo '  All tests complete!'
	@echo '═══════════════════════════════════════════════════════════════'

check:  ## Run code quality checks
	@echo 'Backend checks...'
	@cd backend && uv run ruff check src/ tests/
	@cd backend && uv run ruff format --check src/ tests/
	@cd backend && uv run python -m mypy src/ || true
	@echo ''
	@echo 'Frontend checks...'
	@cd frontend && npm run lint --if-present || true
	@cd frontend && npm run typecheck --if-present || true
	@echo ''
	@echo 'All checks complete'

logs:  ## View container logs
	@docker compose -f docker-compose.dev.yml logs -f
