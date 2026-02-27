# syntax=docker/dockerfile:1

# ============================================
# Stage 1: Build dependencies
# ============================================
FROM python:3.12-slim AS builder

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files and README (required by hatchling)
COPY pyproject.toml README.md ./

# Install git (required to fetch git-hosted dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install dependencies
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv pip install --no-cache .

# ============================================
# Stage 2: Development
# ============================================
FROM builder AS development

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    ENVIRONMENT=development \
    LOG_LEVEL=debug

# Create non-root user
# /app/.cache is created with mode 700 to mitigate CVE-2025-69872 (diskcache unsafe pickle
# deserialization): the attack requires write access to the cache directory. Restricting it
# to the appuser only prevents other processes from injecting malicious payloads.
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/.cache && \
    chown -R appuser:appuser /app && \
    chmod 700 /app/.cache

# Reinstall as editable for hot reload (source changes picked up without rebuild)
RUN uv pip install --no-cache -e ".[dev]"

# Copy source code
COPY src/ ./src/

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8001

# Development entrypoint - hot reload enabled
CMD ["uvicorn", "aggregator.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--reload", \
     "--reload-dir", "src"]

# ============================================
# Stage 3: Runtime
# ============================================
FROM python:3.12-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user
# /app/.cache is created with mode 700 to mitigate CVE-2025-69872 (diskcache unsafe pickle
# deserialization): the attack requires write access to the cache directory. Restricting it
# to the appuser only prevents other processes from injecting malicious payloads.
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/.cache && \
    chmod 700 /app/.cache

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH="/app/src"

# Change ownership to non-root user
RUN chown -R appuser:appuser /app /app/.cache

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8001/health', timeout=5).raise_for_status()" || exit 1

# Run the application
CMD ["uvicorn", "aggregator.main:app", "--host", "0.0.0.0", "--port", "8001"]
