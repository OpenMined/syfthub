.PHONY: help install install-dev test test-cov lint format check type-check pre-commit build run dev server seed clean clean-build clean-pyc clean-test clean-all docker-dev docker-prod docker-test docker-build docker-down docker-logs docker-clean

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install:  ## Install production dependencies
	cd backend && uv sync

install-dev:  ## Install development dependencies
	cd backend && uv sync --dev
	cd backend && uv run pre-commit install

test:  ## Run tests
	cd backend && uv run pytest

test-cov:  ## Run tests with coverage report
	cd backend && uv run pytest --cov-report=term-missing --cov-report=html

test-watch:  ## Run tests in watch mode (requires pytest-watch)
	cd backend && uv run ptw -- --testmon

lint:  ## Run linting checks
	cd backend && uv run ruff check src/ tests/

format:  ## Format code with ruff
	cd backend && uv run ruff format src/ tests/

check:  ## Run all checks (lint, format check, type check)
	cd backend && uv run ruff check src/ tests/
	cd backend && uv run ruff format --check src/ tests/
	cd backend && uv run mypy src/

fix:  ## Fix auto-fixable issues
	cd backend && uv run ruff check --fix src/ tests/
	cd backend && uv run ruff format src/ tests/

type-check:  ## Run type checking with mypy
	cd backend && uv run mypy src/

pre-commit:  ## Run pre-commit hooks on all files
	cd backend && uv run pre-commit run --all-files

pre-commit-update:  ## Update pre-commit hooks
	cd backend && uv run pre-commit autoupdate

build:  ## Build the package
	cd backend && uv build

run:  ## Run the FastAPI server in production mode
	cd backend && uv run uvicorn syfthub.main:app --host 0.0.0.0 --port 8000

dev:  ## Run the FastAPI server in development mode with reload
	cd backend && uv run uvicorn syfthub.main:app --host 0.0.0.0 --port 8000 --reload

server: dev  ## Alias for dev command

seed:  ## 🌱 Populate database with sample data (server must be running)
	@echo "Seeding database with sample data..."
	@cd backend/scripts && ./run_seed.sh

shell:  ## Start a Python shell with the package imported
	cd backend && uv run python -c "import syfthub; import code; code.interact(local=locals())"

clean: clean-build clean-pyc clean-test  ## Clean all generated files

clean-build:  ## Remove build artifacts
	rm -rf backend/build/
	rm -rf backend/dist/
	rm -rf backend/.eggs/
	find backend -name '*.egg-info' -exec rm -rf {} +
	find backend -name '*.egg' -exec rm -rf {} +

clean-pyc:  ## Remove Python cache files
	find backend -type f -name '*.py[co]' -delete
	find backend -type d -name '__pycache__' -exec rm -rf {} +
	find backend -name '*~' -delete

clean-test:  ## Remove test and coverage artifacts
	rm -rf backend/.tox/
	rm -rf backend/.pytest_cache/
	rm -rf backend/.mypy_cache/
	rm -rf backend/.ruff_cache/
	rm -rf backend/htmlcov/
	rm -rf backend/.coverage
	rm -rf backend/coverage.xml
	rm -rf backend/*.cover

clean-all: clean  ## Clean everything including virtual environment
	rm -rf backend/.venv/
	rm -rf backend/uv.lock

# Docker commands
docker-dev:  ## Start development environment with Docker
	@echo "Starting development environment..."
	@cp -n backend/.env.example backend/.env 2>/dev/null || true
	cd backend && docker compose up -d
	@echo "Development environment started!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"
	@echo "Logs: make docker-logs"

docker-prod:  ## Start production environment with Docker
	@echo "Starting production environment..."
	@if [ ! -f backend/.env ]; then \
		echo "Error: backend/.env file not found. Please copy backend/.env.example and configure it."; \
		exit 1; \
	fi
	cd backend && docker compose -f docker-compose.prod.yml up -d
	@echo "Production environment started!"
	@echo "Running migrations..."
	cd backend && docker compose -f docker-compose.prod.yml run --rm migrate || true
	@echo "Production deployment complete!"

docker-test:  ## Run tests in Docker container
	@echo "Running tests in Docker..."
	cd backend && docker compose run --rm test

docker-build:  ## Build Docker images
	@echo "Building Docker images..."
	cd backend && docker compose build
	@echo "Build complete!"

docker-build-prod:  ## Build production Docker image
	@echo "Building production Docker image..."
	cd backend && docker build --target production -t syfthub:latest .
	@echo "Production image built: syfthub:latest"

docker-down:  ## Stop all Docker containers
	@echo "Stopping Docker containers..."
	cd backend && docker compose down
	cd backend && docker compose -f docker-compose.prod.yml down 2>/dev/null || true
	@echo "All containers stopped"

docker-logs:  ## View Docker container logs
	cd backend && docker compose logs -f api

docker-logs-prod:  ## View production Docker container logs
	cd backend && docker compose -f docker-compose.prod.yml logs -f api

docker-clean:  ## Clean Docker volumes and images
	@echo "Cleaning Docker resources..."
	cd backend && docker compose down -v
	cd backend && docker compose -f docker-compose.prod.yml down -v 2>/dev/null || true
	@echo "Docker volumes cleaned"

docker-shell:  ## Access shell in running Docker container
	cd backend && docker compose exec api bash

docker-shell-prod:  ## Access shell in production Docker container
	cd backend && docker compose -f docker-compose.prod.yml exec api bash

docker-ps:  ## Show running Docker containers
	@cd backend && docker compose ps
	@echo ""
	@cd backend && docker compose -f docker-compose.prod.yml ps 2>/dev/null || true

docker-restart:  ## Restart Docker containers
	cd backend && docker compose restart

docker-restart-prod:  ## Restart production Docker containers
	cd backend && docker compose -f docker-compose.prod.yml restart

docker-health:  ## Check health status of Docker containers
	@echo "Checking container health..."
	@docker inspect syfthub-api-dev --format='Dev API: {{.State.Health.Status}}' 2>/dev/null || echo "Dev API: not running"
	@docker inspect syfthub-api --format='Prod API: {{.State.Health.Status}}' 2>/dev/null || echo "Prod API: not running"

docker-backup:  ## Run database backup in Docker
	cd backend && docker compose -f docker-compose.prod.yml --profile backup run --rm backup

docker-migrate:  ## Run database migrations in Docker
	cd backend && docker compose -f docker-compose.prod.yml run --rm migrate

docker-monitoring:  ## Start monitoring stack (Prometheus/Grafana)
	cd backend && docker compose -f docker-compose.prod.yml --profile monitoring up -d
	@echo "Monitoring started!"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"