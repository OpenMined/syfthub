"""Shell completion functions for SyftHub CLI."""

from __future__ import annotations

import json
import time
from typing import Any, cast

from syfthub_cli.config import CONFIG_DIR, load_config

# Cache configuration
CACHE_FILE = CONFIG_DIR / ".completion_cache.json"
CACHE_TTL = 300  # 5 minutes


def _get_cached_endpoints() -> list[dict[str, Any]] | None:
    """Get endpoints from cache if valid."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        if time.time() - data.get("timestamp", 0) < CACHE_TTL:
            return cast(list[dict[str, Any]], data.get("endpoints", []))
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def _fetch_and_cache_endpoints() -> list[dict[str, Any]]:
    """Fetch endpoints from API and cache them."""
    try:
        from syfthub_sdk import AuthTokens, SyftHubClient

        config = load_config()
        client = SyftHubClient(base_url=config.hub_url, timeout=10)
        if config.access_token:
            client.set_tokens(
                AuthTokens(
                    access_token=config.access_token,
                    refresh_token=config.refresh_token or "",
                )
            )

        endpoints = []
        with client:
            for i, ep in enumerate(client.hub.browse()):
                endpoints.append(
                    {
                        "owner": ep.owner_username,
                        "name": ep.name,
                        "type": ep.type.value,
                        "description": ep.description or "",
                    }
                )
                if i >= 500:  # Limit for completion performance
                    break

        # Cache the results
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "endpoints": endpoints,
                    "timestamp": time.time(),
                }
            )
        )
        return endpoints
    except Exception:
        # Silently fail - completion should never break the shell
        return []


def _get_endpoints() -> list[dict[str, Any]]:
    """Get endpoints, using cache if available."""
    cached = _get_cached_endpoints()
    if cached is not None:
        return cached
    return _fetch_and_cache_endpoints()


def complete_ls_target(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete target for ls command (username or user/endpoint).

    - If incomplete doesn't contain "/" -> complete usernames
    - If incomplete contains "/" -> complete endpoints for that user
    """
    try:
        endpoints = _get_endpoints()

        if "/" in incomplete:
            # User is typing an endpoint path like "alice/my-"
            user_prefix = incomplete.split("/")[0].lower()
            endpoint_prefix = (
                incomplete.split("/", 1)[1].lower() if "/" in incomplete else ""
            )

            completions = []
            for ep in endpoints:
                if ep["owner"].lower() == user_prefix:
                    full_path = f"{ep['owner']}/{ep['name']}"
                    if ep["name"].lower().startswith(endpoint_prefix):
                        # Return (value, help_text)
                        help_text = (
                            f"{ep['type']}: {ep['description'][:40]}"
                            if ep["description"]
                            else ep["type"]
                        )
                        completions.append((full_path, help_text))
            return completions
        else:
            # User is typing a username
            seen_users: dict[str, int] = {}
            for ep in endpoints:
                owner = ep["owner"]
                if owner.lower().startswith(incomplete.lower()):
                    seen_users[owner] = seen_users.get(owner, 0) + 1

            return [
                (f"{user}/", f"{count} endpoint(s)")
                for user, count in sorted(seen_users.items())
            ]
    except Exception:
        return []


def complete_model_endpoint(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete model endpoint paths (user/endpoint where type=model)."""
    try:
        endpoints = _get_endpoints()
        completions = []

        for ep in endpoints:
            if ep["type"] != "model":
                continue

            full_path = f"{ep['owner']}/{ep['name']}"
            if full_path.lower().startswith(incomplete.lower()):
                help_text = ep["description"][:50] if ep["description"] else "model"
                completions.append((full_path, help_text))

        return completions
    except Exception:
        return []


def complete_data_source(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete data source endpoint paths."""
    try:
        endpoints = _get_endpoints()
        completions = []

        for ep in endpoints:
            if ep["type"] not in ("data_source", "model_data_source"):
                continue

            full_path = f"{ep['owner']}/{ep['name']}"
            if full_path.lower().startswith(incomplete.lower()):
                help_text = ep["description"][:50] if ep["description"] else ep["type"]
                completions.append((full_path, help_text))

        return completions
    except Exception:
        return []


def complete_aggregator_alias(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete aggregator aliases from local config."""
    try:
        config = load_config()
        completions = []

        for alias, agg_config in config.aggregators.items():
            if alias.lower().startswith(incomplete.lower()):
                completions.append((alias, agg_config.url))

        return completions
    except Exception:
        return []


def complete_accounting_alias(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete accounting service aliases from local config."""
    try:
        config = load_config()
        completions = []

        for alias, acc_config in config.accounting_services.items():
            if alias.lower().startswith(incomplete.lower()):
                completions.append((alias, acc_config.url))

        return completions
    except Exception:
        return []


def complete_config_key(
    ctx: Any,  # noqa: ARG001
    incomplete: str,
) -> list[tuple[str, str]]:
    """Complete configuration keys."""
    # Static list of allowed keys with descriptions
    allowed_keys = {
        "default_aggregator": "Default aggregator alias",
        "default_accounting": "Default accounting service alias",
        "timeout": "Request timeout in seconds",
        "hub_url": "SyftHub API URL",
    }

    completions = []
    for key, description in allowed_keys.items():
        if key.lower().startswith(incomplete.lower()):
            completions.append((key, description))

    return completions
