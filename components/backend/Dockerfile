# Multi-stage Dockerfile for SyftHub
# Supports both development and production environments

# Base stage with Python and system dependencies
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user and data directory
RUN useradd -m -u 1000 syfthub && \
    mkdir -p /app /app/data && \
    chown -R syfthub:syfthub /app

# Set working directory
WORKDIR /app

# ==============================================================================
# Dependencies stage - install Python packages
FROM base AS dependencies

# Copy dependency files
COPY --chown=syfthub:syfthub pyproject.toml ./
COPY --chown=syfthub:syfthub README.md ./

# Create src structure for package installation
RUN mkdir -p src/syfthub && \
    touch src/syfthub/__init__.py && \
    chown -R syfthub:syfthub src

# Switch to non-root user
USER syfthub

# Create virtual environment and install production dependencies
RUN uv venv .venv && \
    uv pip install -e . --python .venv/bin/python

# ==============================================================================
# Development stage
FROM dependencies AS development

# Switch back to root for dev dependencies installation
USER root

# Install development dependencies
RUN uv pip install -e ".[dev]" --python .venv/bin/python

# Install additional dev tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Copy source code (excluding .venv which is already created)
COPY --chown=syfthub:syfthub src src
COPY --chown=syfthub:syfthub tests tests
COPY --chown=syfthub:syfthub requirements.txt .
COPY --chown=syfthub:syfthub uv.lock .
COPY --chown=syfthub:syfthub README.md .

# Switch to non-root user
USER syfthub

# Expose port
EXPOSE 8000

# Set environment for development
ENV ENVIRONMENT=development \
    RELOAD=true \
    LOG_LEVEL=debug

# Development entrypoint - hot reload enabled
CMD ["/app/.venv/bin/uvicorn", "syfthub.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-dir", "src"]

# ==============================================================================
# Testing stage
FROM dependencies AS testing

# Install test dependencies
USER root
RUN uv pip install -e ".[test]" --python .venv/bin/python

# Copy source code (excluding .venv which is already created)
COPY --chown=syfthub:syfthub src src
COPY --chown=syfthub:syfthub tests tests
COPY --chown=syfthub:syfthub requirements.txt .
COPY --chown=syfthub:syfthub uv.lock .
COPY --chown=syfthub:syfthub README.md .

# Switch to non-root user
USER syfthub

# Run tests by default
CMD ["/app/.venv/bin/pytest", "--cov=syfthub", "--cov-report=term-missing"]

# ==============================================================================
# Production build stage
FROM dependencies AS builder

# Copy source code
COPY --chown=syfthub:syfthub src src
COPY --chown=syfthub:syfthub LICENSE* ./
COPY --chown=syfthub:syfthub CHANGELOG* ./

# Build the package
RUN uv build --wheel

# ==============================================================================
# Production runtime stage
FROM python:3.12-slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=info

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN useradd -m -u 1000 syfthub && \
    mkdir -p /app && \
    chown -R syfthub:syfthub /app

WORKDIR /app

# Create fresh virtual environment and install the wheel
COPY --from=builder --chown=syfthub:syfthub /app/dist/*.whl /tmp/
RUN uv venv .venv && \
    uv pip install /tmp/*.whl --python .venv/bin/python && \
    rm -rf /tmp/*.whl

# Create necessary directories
RUN mkdir -p /app/data && \
    chown -R syfthub:syfthub /app/data

# Switch to non-root user
USER syfthub

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Production entrypoint - using gunicorn with uvicorn workers for better performance
CMD [".venv/bin/uvicorn", "syfthub.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info", \
     "--access-log", \
     "--use-colors"]

# ==============================================================================
# Lightweight production stage (alternative)
FROM python:3.12-alpine AS production-alpine

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=info

# Install Alpine packages
RUN apk add --no-cache \
    libpq \
    curl \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev

# Create non-root user
RUN adduser -D -u 1000 syfthub && \
    mkdir -p /app && \
    chown -R syfthub:syfthub /app

WORKDIR /app

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create fresh virtual environment and install the wheel
COPY --from=builder --chown=syfthub:syfthub /app/dist/*.whl /tmp/
RUN uv venv .venv && \
    uv pip install /tmp/*.whl --python .venv/bin/python && \
    rm -rf /tmp/*.whl && \
    apk del .build-deps

# Create necessary directories
RUN mkdir -p /app/data && \
    chown -R syfthub:syfthub /app/data

# Switch to non-root user
USER syfthub

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Production entrypoint
CMD [".venv/bin/uvicorn", "syfthub.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--log-level", "info"]
