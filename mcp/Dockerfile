# SyftHub MCP Server Dockerfile
# Multi-stage build for development and production

# ==============================================================================
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
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN useradd -m -u 1000 syfthub && \
    mkdir -p /app /app/sdk && \
    chown -R syfthub:syfthub /app

# Set working directory
WORKDIR /app

# ==============================================================================
# Dependencies stage - install Python packages
FROM base AS dependencies

# Copy dependency files
COPY --chown=syfthub:syfthub pyproject.toml ./

# Switch to non-root user
USER syfthub

# Create virtual environment
RUN uv venv .venv

# ==============================================================================
# Development stage - SDK mounted as volume
FROM dependencies AS development

# Copy source code
COPY --chown=syfthub:syfthub server.py ./
COPY --chown=syfthub:syfthub syfthub_client.py ./
COPY --chown=syfthub:syfthub fastmcp.json ./

# Expose port
EXPOSE 8002

# Environment variables for development
ENV ENVIRONMENT=development \
    LOG_LEVEL=debug \
    MCP_PORT=8002

# Development entrypoint - hot reload enabled
# SDK will be mounted at /sdk/python via docker-compose (matches pyproject.toml: ../sdk/python)
# Dependencies installed at container startup to pick up SDK mount
CMD uv pip install -e . -e /sdk/python --python .venv/bin/python && \
    /app/.venv/bin/uvicorn server:create_app \
    --host 0.0.0.0 \
    --port 8002 \
    --reload \
    --factory

# ==============================================================================
# Production stage
FROM dependencies AS production

# Copy source code
COPY --chown=syfthub:syfthub server.py ./
COPY --chown=syfthub:syfthub syfthub_client.py ./
COPY --chown=syfthub:syfthub fastmcp.json ./

# Environment variables for production
ENV ENVIRONMENT=production \
    LOG_LEVEL=info \
    MCP_PORT=8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Expose port
EXPOSE 8002

# Production entrypoint
CMD ["/app/.venv/bin/uvicorn", "server:create_app", \
     "--host", "0.0.0.0", \
     "--port", "8002", \
     "--workers", "2", \
     "--log-level", "info", \
     "--factory"]
