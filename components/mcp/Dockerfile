# SyftHub MCP Server Dockerfile
# Multi-stage build for development and production
#
# Build contexts:
#   - Development: context: ../components/mcp (SDK mounted as volume)
#   - Production:  context: ..                 (SDK included in build, from repository root)

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
# /app/.cache is created with mode 700 to mitigate CVE-2025-69872 (diskcache unsafe pickle
# deserialization): the attack requires write access to the cache directory. Restricting it
# to the syfthub user only prevents other processes from injecting malicious payloads.
RUN useradd -m -u 1000 syfthub && \
    mkdir -p /app /app/.cache /sdk/python && \
    chown -R syfthub:syfthub /app /sdk && \
    chmod 700 /app/.cache

# Set working directory
WORKDIR /app

# ==============================================================================
# Development stage - SDK mounted as volume at runtime
# Build with: context: ../components/mcp (from deploy directory)
FROM base AS development

# Copy dependency files (from mcp context)
COPY --chown=syfthub:syfthub pyproject.toml ./

# Switch to non-root user
USER syfthub

# Create virtual environment with pip (needed for runtime dependency installation)
RUN uv venv .venv && \
    uv pip install pip --python .venv/bin/python

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
# Use pip directly (uv has path normalization restrictions that break mounted volumes)
CMD .venv/bin/pip install -e /sdk/python && \
    .venv/bin/pip install -e . && \
    /app/.venv/bin/uvicorn server:create_app \
    --host 0.0.0.0 \
    --port 8002 \
    --reload \
    --factory

# ==============================================================================
# Production stage - SDK baked into image
# Build with: context: .. (repository root, from components/mcp directory)
FROM base AS production

# Copy SDK from repository root (build context must be repository root)
COPY --chown=syfthub:syfthub sdk/python /sdk/python

# Copy MCP dependency files (from components/mcp subdirectory)
COPY --chown=syfthub:syfthub components/mcp/pyproject.toml ./

# Switch to non-root user
USER syfthub

# Create virtual environment and install ALL dependencies including SDK
# Remove the local SDK source override to avoid path resolution issues in Docker
# Then install the package and SDK from the container paths
RUN uv venv .venv && \
    sed -i '/\[tool.uv.sources\]/,/^$/d' pyproject.toml && \
    uv pip install -e . -e /sdk/python --python .venv/bin/python

# Copy source code
COPY --chown=syfthub:syfthub components/mcp/server.py ./
COPY --chown=syfthub:syfthub components/mcp/syfthub_client.py ./
COPY --chown=syfthub:syfthub components/mcp/fastmcp.json ./

# Environment variables for production
# RSA_PRIVATE_KEY: Base64-encoded PEM private key for JWT signing (REQUIRED for multi-worker)
# Generate with: python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; import base64; k=rsa.generate_private_key(65537,2048); print(base64.b64encode(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())).decode())"
ENV ENVIRONMENT=production \
    LOG_LEVEL=info \
    MCP_PORT=8002
    # RSA_PRIVATE_KEY should be set via docker-compose or orchestrator secrets

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Expose port
EXPOSE 8002

# Production entrypoint
CMD ["/app/.venv/bin/uvicorn", "server:create_app", \
     "--host", "0.0.0.0", \
     "--port", "8002", \
     "--workers", "1", \
     "--log-level", "info", \
     "--factory"]
