.PHONY: help install install-dev test test-cov lint format check type-check pre-commit build run dev server seed clean clean-build clean-pyc clean-test clean-all docker-dev docker-prod docker-test docker-build docker-down docker-logs docker-clean

help:  ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install:  ## Install production dependencies
	uv sync

install-dev:  ## Install development dependencies
	uv sync --dev
	uv run pre-commit install

test:  ## Run tests
	uv run pytest

test-cov:  ## Run tests with coverage report
	uv run pytest --cov-report=term-missing --cov-report=html

test-watch:  ## Run tests in watch mode (requires pytest-watch)
	uv run ptw -- --testmon

lint:  ## Run linting checks
	uv run ruff check src/ tests/

format:  ## Format code with ruff
	uv run ruff format src/ tests/

check:  ## Run all checks (lint, format check, type check)
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

fix:  ## Fix auto-fixable issues
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

type-check:  ## Run type checking with mypy
	uv run mypy src/

pre-commit:  ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

pre-commit-update:  ## Update pre-commit hooks
	uv run pre-commit autoupdate

build:  ## Build the package
	uv build

run:  ## Run the FastAPI server in production mode
	uv run uvicorn syfthub.main:app --host 0.0.0.0 --port 8000

dev:  ## Run the FastAPI server in development mode with reload
	uv run uvicorn syfthub.main:app --host 0.0.0.0 --port 8000 --reload

server: dev  ## Alias for dev command

seed:  ## 🌱 Populate database with sample data (server must be running)
	@echo "Seeding database with sample data..."
	@cd scripts && ./run_seed.sh

shell:  ## Start a Python shell with the package imported
	uv run python -c "import syfthub; import code; code.interact(local=locals())"

clean: clean-build clean-pyc clean-test  ## Clean all generated files

clean-build:  ## Remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -rf {} +

clean-pyc:  ## Remove Python cache files
	find . -type f -name '*.py[co]' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -name '*~' -delete

clean-test:  ## Remove test and coverage artifacts
	rm -rf .tox/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf coverage.xml
	rm -rf *.cover

clean-all: clean  ## Clean everything including virtual environment
	rm -rf .venv/
	rm -rf uv.lock

# Docker commands
docker-dev:  ## Start development environment with Docker
	@echo "Starting development environment..."
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up -d
	@echo "Development environment started!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"
	@echo "Logs: make docker-logs"

docker-prod:  ## Start production environment with Docker
	@echo "Starting production environment..."
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found. Please copy .env.example and configure it."; \
		exit 1; \
	fi
	docker compose -f docker-compose.prod.yml up -d
	@echo "Production environment started!"
	@echo "Running migrations..."
	docker compose -f docker-compose.prod.yml run --rm migrate || true
	@echo "Production deployment complete!"

docker-test:  ## Run tests in Docker container
	@echo "Running tests in Docker..."
	docker compose run --rm test

docker-build:  ## Build Docker images
	@echo "Building Docker images..."
	docker compose build
	@echo "Build complete!"

docker-build-prod:  ## Build production Docker image
	@echo "Building production Docker image..."
	docker build --target production -t syfthub:latest .
	@echo "Production image built: syfthub:latest"

docker-down:  ## Stop all Docker containers
	@echo "Stopping Docker containers..."
	docker compose down
	docker compose -f docker-compose.prod.yml down 2>/dev/null || true
	@echo "All containers stopped"

docker-logs:  ## View Docker container logs
	docker compose logs -f api

docker-logs-prod:  ## View production Docker container logs
	docker compose -f docker-compose.prod.yml logs -f api

docker-clean:  ## Clean Docker volumes and images
	@echo "Cleaning Docker resources..."
	docker compose down -v
	docker compose -f docker-compose.prod.yml down -v 2>/dev/null || true
	@echo "Docker volumes cleaned"

docker-shell:  ## Access shell in running Docker container
	docker compose exec api bash

docker-shell-prod:  ## Access shell in production Docker container
	docker compose -f docker-compose.prod.yml exec api bash

docker-ps:  ## Show running Docker containers
	@docker compose ps
	@echo ""
	@docker compose -f docker-compose.prod.yml ps 2>/dev/null || true

docker-restart:  ## Restart Docker containers
	docker compose restart

docker-restart-prod:  ## Restart production Docker containers
	docker compose -f docker-compose.prod.yml restart

docker-health:  ## Check health status of Docker containers
	@echo "Checking container health..."
	@docker inspect syfthub-api-dev --format='Dev API: {{.State.Health.Status}}' 2>/dev/null || echo "Dev API: not running"
	@docker inspect syfthub-api --format='Prod API: {{.State.Health.Status}}' 2>/dev/null || echo "Prod API: not running"

docker-backup:  ## Run database backup in Docker
	docker compose -f docker-compose.prod.yml --profile backup run --rm backup

docker-migrate:  ## Run database migrations in Docker
	docker compose -f docker-compose.prod.yml run --rm migrate

docker-monitoring:  ## Start monitoring stack (Prometheus/Grafana)
	docker compose -f docker-compose.prod.yml --profile monitoring up -d
	@echo "Monitoring started!"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"
