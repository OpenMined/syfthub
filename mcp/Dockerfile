# SyftHub MCP Server Dockerfile
# Multi-stage build for development and production
#
# Build contexts:
#   - Development: context: ./mcp (SDK mounted as volume)
#   - Production:  context: .     (SDK included in build)

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
    mkdir -p /app /sdk/python && \
    chown -R syfthub:syfthub /app /sdk

# Set working directory
WORKDIR /app

# ==============================================================================
# Development stage - SDK mounted as volume at runtime
# Build with: context: ./mcp
FROM base AS development

# Copy dependency files (from mcp context)
COPY --chown=syfthub:syfthub pyproject.toml ./

# Switch to non-root user
USER syfthub

# Create virtual environment
RUN uv venv .venv

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
# SDK will be mounted at /sdk/python via docker-compose
# Dependencies installed at container startup to pick up SDK mount
CMD uv pip install -e . -e /sdk/python --python .venv/bin/python && \
    /app/.venv/bin/uvicorn server:create_app \
    --host 0.0.0.0 \
    --port 8002 \
    --reload \
    --factory

# ==============================================================================
# Builder stage - install dependencies in base with build tools
# Build with: context: . (repository root)
FROM base AS builder

# Copy SDK from repository root (build context must be .)
COPY --chown=syfthub:syfthub sdk/python /sdk/python

# Copy MCP dependency files (from mcp subdirectory)
COPY --chown=syfthub:syfthub mcp/pyproject.toml ./

# Switch to non-root user
USER syfthub

# Create virtual environment and install ALL dependencies including SDK
# This bakes dependencies into the image at build time
RUN uv venv .venv && \
    uv pip install -e . -e /sdk/python --python .venv/bin/python

# ==============================================================================
# Production stage - fresh slim image without build tools (gcc, git)
# Build with: context: . (repository root)
FROM python:3.12-slim AS production

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    LOG_LEVEL=info \
    MCP_PORT=8002

# Install uv for runtime (no gcc, git, or curl needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN useradd -m -u 1000 syfthub && \
    mkdir -p /app /sdk/python && \
    chown -R syfthub:syfthub /app /sdk

WORKDIR /app

# Copy virtual environment and SDK from builder
COPY --from=builder --chown=syfthub:syfthub /app/.venv /app/.venv
COPY --from=builder --chown=syfthub:syfthub /sdk/python /sdk/python

# Copy source code
COPY --chown=syfthub:syfthub mcp/server.py ./
COPY --chown=syfthub:syfthub mcp/syfthub_client.py ./
COPY --chown=syfthub:syfthub mcp/fastmcp.json ./

# Switch to non-root user
USER syfthub

# Health check (using Python instead of curl to avoid extra dependency)
# RSA_PRIVATE_KEY: Base64-encoded PEM private key for JWT signing (REQUIRED for multi-worker)
# Generate with: python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; import base64; k=rsa.generate_private_key(65537,2048); print(base64.b64encode(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())).decode())"
# RSA_PRIVATE_KEY should be set via docker-compose or orchestrator secrets
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5)" || exit 1

# Expose port
EXPOSE 8002

# Production entrypoint
CMD ["/app/.venv/bin/uvicorn", "server:create_app", \
     "--host", "0.0.0.0", \
     "--port", "8002", \
     "--workers", "1", \
     "--log-level", "info", \
     "--factory"]
