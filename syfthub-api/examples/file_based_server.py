#!/usr/bin/env python3
"""
File-Based Endpoint Server Example

This example demonstrates the file-based endpoint configuration mode where
endpoints are defined through folder structures instead of decorators.

Each endpoint is a folder containing:
- README.md: YAML frontmatter with endpoint metadata (slug, type, name, description)
- runner.py: Handler function with signature (messages: list[Message], ctx: RequestContext)
- policy/ (optional): YAML files defining policies for this endpoint

Example folder structure:
    file_endpoints/
    ├── echo-model/
    │   ├── README.md
    │   ├── runner.py
    │   └── policy/
    │       └── rate_limit.yaml
    └── sample-docs/
        ├── README.md
        └── runner.py

The server will:
1. Scan the endpoints directory on startup
2. Load all valid endpoint folders
3. Watch for changes and hot-reload endpoints (if watch_enabled=True)
4. Sync endpoints with SyftHub backend

Required environment variables:
    SYFTHUB_URL      — URL of the SyftHub instance
    SYFTHUB_USERNAME — Your SyftHub username
    SYFTHUB_PASSWORD — Your SyftHub password
    SPACE_URL        — The public URL where this space is reachable

Optional environment variables:
    ENDPOINTS_PATH   — Path to endpoints directory (default: ./file_endpoints)
    WATCH_ENABLED    — Enable hot-reload (default: true)
    WATCH_DEBOUNCE_SECONDS — Debounce delay for file changes (default: 1.0)

Usage:
    export SYFTHUB_URL="http://localhost:8080"
    export SYFTHUB_USERNAME="your-username"
    export SYFTHUB_PASSWORD="your-password"
    export SPACE_URL="http://localhost:8001"
    python examples/file_based_server.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from syfthub_api import SyftAPI


async def main() -> None:
    """Run the file-based endpoint server."""
    # Get the examples/file_endpoints directory
    examples_dir = Path(__file__).parent
    endpoints_path = examples_dir / "file_endpoints"

    print(f"Starting file-based endpoint server...")
    print(f"Endpoints directory: {endpoints_path}")

    # Create SyftAPI with file-based mode enabled
    app = SyftAPI(
        endpoints_path=endpoints_path,
        watch_enabled=True,  # Enable hot-reload
        watch_debounce_seconds=1.0,  # Wait 1s after changes before reloading
    )

    # You can also register decorator-based endpoints alongside file-based ones
    # @app.model(slug="mixed-model", name="Mixed Model", description="Decorator-based")
    # async def mixed_model(messages):
    #     return "This is from a decorator!"

    @app.on_startup
    async def on_startup() -> None:
        print("Server started!")
        print(f"Loaded {len(app.endpoints)} endpoints:")
        for ep in app.endpoints:
            marker = "[file]" if ep.get("_file_mode") else "[decorator]"
            print(f"  {marker} {ep['slug']} ({ep['type'].value})")

    @app.on_shutdown
    async def on_shutdown() -> None:
        print("Server shutting down...")

    # Run the server
    await app.run(host="0.0.0.0", port=8001)


if __name__ == "__main__":
    asyncio.run(main())
