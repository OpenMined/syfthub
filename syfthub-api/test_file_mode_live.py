#!/usr/bin/env python3
"""
Live test for file-based endpoint mode with NATS tunneling.

This script tests:
1. Loading endpoints from file_endpoints folder
2. Authenticating with SyftHub
3. Syncing endpoints via NATS tunneling mode
"""

import asyncio
import os
import sys
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent / "src"))

from syfthub_api import SyftAPI


async def main() -> None:
    """Run file-based endpoint test."""
    # Get the examples/file_endpoints directory
    examples_dir = Path(__file__).parent / "examples"
    endpoints_path = examples_dir / "file_endpoints"

    print("=" * 60)
    print("File-Based Endpoint Mode - Live Test")
    print("=" * 60)
    print()
    print(f"SyftHub URL: {os.environ.get('SYFTHUB_URL')}")
    print(f"Username: {os.environ.get('SYFTHUB_USERNAME')}")
    print(f"Space URL: {os.environ.get('SPACE_URL')}")
    print(f"Endpoints Path: {endpoints_path}")
    print()

    # List endpoint folders
    print("Endpoint folders found:")
    for folder in sorted(endpoints_path.iterdir()):
        if folder.is_dir() and not folder.name.startswith(("_", ".")):
            readme = folder / "README.md"
            if readme.exists():
                print(f"  - {folder.name}/")

    print()
    print("Creating SyftAPI with file-based mode...")

    # Create SyftAPI with file-based mode enabled
    app = SyftAPI(
        endpoints_path=endpoints_path,
        watch_enabled=True,  # Enable hot-reload watching
    )

    @app.on_startup
    async def on_startup() -> None:
        print()
        print("=" * 60)
        print("Server started successfully!")
        print("=" * 60)
        print()
        print(f"Loaded {len(app.endpoints)} endpoints:")
        for ep in app.endpoints:
            marker = "[file]" if ep.get("_file_mode") else "[decorator]"
            policies = len(ep.get("policies", []))
            print(f"  {marker} {ep['slug']} ({ep['type'].value}) - {policies} policies")
        print()
        print("Listening for requests via NATS tunneling...")
        print("Press Ctrl+C to stop")

    @app.on_shutdown
    async def on_shutdown() -> None:
        print()
        print("Server shutting down...")

    # Run the server
    try:
        await app.run(host="0.0.0.0", port=8001)
    except KeyboardInterrupt:
        print("\nInterrupted by user")


if __name__ == "__main__":
    asyncio.run(main())
