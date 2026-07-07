#!/bin/bash
set -e

echo "[container_runner] Starting SyftHub endpoint container..."

# Install user dependencies if pyproject.toml exists
if [ -f /app/endpoint/pyproject.toml ]; then
    echo "[container_runner] Installing dependencies from pyproject.toml..."
    pip install --cache-dir /app/.cache --quiet -e /app/endpoint 2>&1 || {
        echo "[container_runner] WARNING: pip install failed, continuing without user deps"
    }
elif [ -f /app/endpoint/requirements.txt ]; then
    echo "[container_runner] Installing dependencies from requirements.txt..."
    pip install --cache-dir /app/.cache --quiet -r /app/endpoint/requirements.txt 2>&1 || {
        echo "[container_runner] WARNING: pip install failed, continuing without user deps"
    }
fi

echo "[container_runner] Starting HTTP server..."
exec python -m container_runner --port 8080 --handler /app/endpoint/runner.py "$@"
