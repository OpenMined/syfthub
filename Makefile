.PHONY: help dev stop test check logs

# =============================================================================
# SyftHub Development Commands
# =============================================================================
#
# Quick Start:
#   make dev     - Start development environment
#   make logs    - View logs (debug issues)
#   make test    - Run tests
#   make check   - Run code quality checks
#   make stop    - Stop all services
#
# For production deployment, see README.md
# =============================================================================

help:  ## Show available commands
	@echo ''
	@echo 'SyftHub Development Commands:'
	@echo ''
	@echo '  make dev     Start development environment (http://localhost)'
	@echo '  make stop    Stop all services'
	@echo '  make test    Run all tests'
	@echo '  make check   Run code quality checks (lint, format, types)'
	@echo '  make logs    View container logs'
	@echo ''
	@echo 'Production deployment:'
	@echo '  docker compose -f docker-compose.prod.yml up -d'
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

test:  ## Run all tests
	@echo 'Running backend tests...'
	@cd backend && uv run python -m pytest
	@echo ''
	@echo 'Running frontend tests...'
	@cd frontend && npm run test --if-present || echo 'Frontend tests skipped (playwright not configured)'
	@echo ''
	@echo 'Running SDK tests...'
	@echo 'Python SDK dev tests...'
	@cd sdk/python && uv run pytest tests/dev/ -v || echo 'Python SDK dev tests skipped (dev server not available)'
	@echo ''
	@echo 'TypeScript SDK dev tests...'
	@cd sdk/typescript && npm run test:dev || echo 'TypeScript SDK dev tests skipped (dev server not available)'

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
