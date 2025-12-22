"""URL building utilities for dynamic endpoint URL construction.

This module provides functions to build full URLs from owner domains and
connection path configurations.

DESIGN INTENT:
- Internally (database storage), connection.config.url contains only the PATH portion
  (e.g., "api/v2" or "" for root)
- Externally (API responses), we ALWAYS expose full URLs by combining:
  {protocol}://{owner.domain}/{connection.config.url}

Where:
- protocol is determined by the connection type (rest_api → https, ws → wss, etc.)
- owner.domain is stored on User or Organization (e.g., "api.example.com")
- connection.config.url contains only the path portion (e.g., "v1" or "")

IMPORTANT: All API responses returning endpoints MUST use transform_connection_urls()
to ensure clients always receive full URLs, not paths.
"""

from __future__ import annotations

from typing import Any

# Mapping from connection type to protocol
CONNECTION_PROTOCOL_MAP: dict[str, str] = {
    # HTTP-based protocols
    "rest_api": "https",
    "http": "https",
    "https": "https",
    "graphql": "https",
    # WebSocket protocols
    "websocket": "wss",
    "ws": "ws",
    "wss": "wss",
    # RPC protocols
    "grpc": "https",
    # Storage protocols
    "database": "https",
    "s3": "https",
    "storage": "https",
}


def get_protocol_for_connection_type(connection_type: str) -> str:
    """Get the protocol for a given connection type.

    Args:
        connection_type: The connection type string (e.g., "rest_api", "websocket")

    Returns:
        The protocol string (e.g., "https", "wss")
    """
    return CONNECTION_PROTOCOL_MAP.get(connection_type.lower(), "https")


def build_connection_url(
    domain: str | None,
    connection_type: str,
    path: str | None,
) -> str | None:
    """Build a full URL from domain and path.

    Args:
        domain: The owner's domain (e.g., "api.example.com" or "api.example.com:8080")
        connection_type: The connection type for protocol selection
        path: The path portion of the URL (e.g., "api/v2" or "/api/v2")

    Returns:
        The full URL (e.g., "https://api.example.com/api/v2") or None if no domain
    """
    if not domain:
        return None

    protocol = get_protocol_for_connection_type(connection_type)
    base_url = f"{protocol}://{domain}"

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
        domain: The owner's domain
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
