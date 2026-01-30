"""URL building utilities for dynamic endpoint URL construction.

This module provides functions to build full URLs from owner domains and
connection path configurations.

DESIGN INTENT:
- The owner's domain field stores a full origin with protocol
  (e.g., "https://api.example.com" or "http://192.168.1.1:8080")
- Internally (database storage), connection.config.url contains only the PATH portion
  (e.g., "api/v2" or "" for root)
- Externally (API responses), we expose full URLs by combining:
  {owner.domain}/{connection.config.url}

Where:
- owner.domain includes the protocol (e.g., "https://api.example.com")
- connection.config.url contains only the path portion (e.g., "v1" or "")

For WebSocket connection types, the protocol is automatically upgraded
(http → ws, https → wss).

IMPORTANT: All API responses returning endpoints MUST use transform_connection_urls()
to ensure clients always receive full URLs, not paths.
"""

from __future__ import annotations

from typing import Any

# WebSocket connection types that need protocol upgrade
_WEBSOCKET_TYPES = {"websocket", "ws", "wss"}


def normalize_domain(domain: str) -> str:
    """Normalize a domain by stripping whitespace and trailing slashes.

    Args:
        domain: The domain string with protocol (e.g., "https://api.example.com/")

    Returns:
        The normalized domain without trailing slashes
    """
    return domain.strip().rstrip("/")


def build_connection_url(
    domain: str | None,
    connection_type: str,
    path: str | None,
) -> str | None:
    """Build a full URL from domain and path.

    The domain is expected to include the protocol (e.g., "https://api.example.com").
    For WebSocket connection types, the protocol is automatically upgraded
    (http → ws, https → wss).

    Args:
        domain: The owner's domain with protocol
            (e.g., "https://api.example.com" or "http://api.example.com:8080")
        connection_type: The connection type (e.g., "rest_api", "websocket").
            Used only for WebSocket protocol upgrades.
        path: The path portion of the URL (e.g., "api/v2" or "/api/v2")

    Returns:
        The full URL (e.g., "https://api.example.com/api/v2") or None if no domain
    """
    if not domain:
        return None

    base_url = normalize_domain(domain)
    if not base_url:
        return None

    # For WebSocket connection types, upgrade protocol
    if connection_type.lower() in _WEBSOCKET_TYPES:
        base_url = base_url.replace("https://", "wss://", 1).replace(
            "http://", "ws://", 1
        )

    if path:
        # Normalize path - remove leading slashes
        normalized_path = path.lstrip("/")
        if normalized_path:
            return f"{base_url}/{normalized_path}"

    return base_url


def transform_connection_urls(
    domain: str | None,
    connections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transform connection configs to include full URLs.

    Takes a list of connection configurations where config.url contains only
    the path, and returns a new list with full URLs built from the domain.

    Args:
        domain: The owner's domain with protocol
        connections: List of connection dictionaries with config.url as path

    Returns:
        New list of connection dictionaries with full URLs in config.url
    """
    if not domain:
        # If no domain, return connections as-is (path-only fallback)
        return connections

    transformed = []
    for conn in connections:
        # Create a copy to avoid mutating the original
        new_conn = dict(conn)
        new_config = dict(conn.get("config", {}))

        # Get the path from config.url
        path = new_config.get("url", "")

        # Build full URL
        connection_type = conn.get("type", "rest_api")
        full_url = build_connection_url(domain, connection_type, path)

        if full_url:
            new_config["url"] = full_url

        new_conn["config"] = new_config
        transformed.append(new_conn)

    return transformed


def get_first_enabled_connection(
    connections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Get the first enabled connection from a list.

    Args:
        connections: List of connection dictionaries

    Returns:
        The first enabled connection, or the first connection if none enabled,
        or None if the list is empty
    """
    if not connections:
        return None

    # Find first enabled connection
    for conn in connections:
        if conn.get("enabled", True):
            return conn

    # Fallback to first connection
    return connections[0]
