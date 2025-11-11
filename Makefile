.PHONY: help install install-dev test test-cov lint format check type-check pre-commit build run clean clean-build clean-pyc clean-test clean-all

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

run:  ## Run the main application
	uv run python -m syfthub.main

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
