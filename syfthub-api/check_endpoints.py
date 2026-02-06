#!/usr/bin/env python3
"""
Check endpoints registered for a SyftHub user.

This utility script authenticates with a SyftHub backend and lists
all endpoints registered to the authenticated user.

Usage:
    export SYFTHUB_URL="https://syfthub-dev.openmined.org"
    export SYFTHUB_USERNAME="your-username"
    export SYFTHUB_PASSWORD="your-password"
    python check_endpoints.py

Environment Variables:
    SYFTHUB_URL: URL of the SyftHub backend (default: https://syfthub-dev.openmined.org)
    SYFTHUB_USERNAME: Your SyftHub username (required)
    SYFTHUB_PASSWORD: Your SyftHub password (required)
"""

from __future__ import annotations

import asyncio
import os
import sys

from syfthub_sdk import SyftHubClient


async def main() -> int:
    """
    Check and display endpoints for the authenticated user.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Load configuration from environment variables
    base_url = os.environ.get("SYFTHUB_URL", "https://syfthub-dev.openmined.org")
    username = os.environ.get("SYFTHUB_USERNAME")
    password = os.environ.get("SYFTHUB_PASSWORD")

    # Validate required credentials
    if not username or not password:
        print("Error: Missing required environment variables.", file=sys.stderr)
        print("\nRequired environment variables:", file=sys.stderr)
        print("  SYFTHUB_USERNAME: Your SyftHub username", file=sys.stderr)
        print("  SYFTHUB_PASSWORD: Your SyftHub password", file=sys.stderr)
        print("\nOptional environment variables:", file=sys.stderr)
        print("  SYFTHUB_URL: SyftHub backend URL (default: https://syfthub-dev.openmined.org)", file=sys.stderr)
        print("\nExample usage:", file=sys.stderr)
        print('  export SYFTHUB_URL="https://syfthub-dev.openmined.org"', file=sys.stderr)
        print('  export SYFTHUB_USERNAME="your-username"', file=sys.stderr)
        print('  export SYFTHUB_PASSWORD="your-password"', file=sys.stderr)
        print("  python check_endpoints.py", file=sys.stderr)
        return 1

    # Create client and authenticate
    client = SyftHubClient(base_url=base_url)

    try:
        await asyncio.to_thread(
            client.auth.login,
            username=username,
            password=password,
        )
        print(f"Successfully logged in as: {username}")
        print(f"Backend URL: {base_url}")
    except Exception as e:
        print(f"Error: Login failed: {e}", file=sys.stderr)
        return 1

    # Fetch and display endpoints
    try:
        endpoints_iterator = await asyncio.to_thread(client.my_endpoints.list)
        endpoints = list(endpoints_iterator)
    except Exception as e:
        print(f"Error: Failed to fetch endpoints: {e}", file=sys.stderr)
        return 1

    print()
    if not endpoints:
        print("No endpoints found for this user.")
    else:
        print(f"Found {len(endpoints)} endpoint(s):")
        print("-" * 60)
        for ep in endpoints:
            print(f"  Name: {ep.name}")
            print(f"  Slug: {ep.slug}")
            print(f"  Type: {ep.type}")
            print(f"  Visibility: {ep.visibility}")
            if hasattr(ep, "description") and ep.description:
                print(f"  Description: {ep.description[:50]}...")
            print("-" * 60)

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
