"""
Environment variable loader for file-based endpoints.

This module provides utilities for loading .env files into isolated
dictionaries without polluting os.environ, enabling per-endpoint
environment variable configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

logger = logging.getLogger(__name__)

# Default .env file name
ENV_FILE = ".env"


def load_endpoint_env(
    endpoint_path: Path,
    env_file_name: str = ENV_FILE,
) -> dict[str, str]:
    """
    Load environment variables from an endpoint's .env file.

    Uses dotenv_values() to load variables into an isolated dictionary
    WITHOUT modifying os.environ. This ensures per-endpoint isolation.

    Args:
        endpoint_path: Path to the endpoint folder.
        env_file_name: Name of the .env file (default: ".env").

    Returns:
        Dictionary of environment variables. Empty dict if no .env file exists.

    Example:
        >>> env = load_endpoint_env(Path("/endpoints/my-endpoint"))
        >>> api_key = env.get("OPENAI_API_KEY", "")
    """
    env_file = endpoint_path / env_file_name

    if not env_file.exists():
        logger.debug("No .env file found in %s", endpoint_path.name)
        return {}

    try:
        # Load without touching os.environ
        env_vars = dotenv_values(env_file)

        # Filter out None values and ensure all are strings
        result: dict[str, str] = {
            k: v for k, v in env_vars.items() if v is not None
        }

        logger.debug(
            "Loaded %d environment variables from %s",
            len(result),
            env_file.name,
        )

        return result

    except Exception as e:
        logger.warning(
            "Failed to load .env file from %s: %s",
            endpoint_path.name,
            e,
        )
        return {}


def validate_required_env(
    env_vars: dict[str, str],
    required: list[str],
    endpoint_name: str,
) -> list[str]:
    """
    Validate that required environment variables are present.

    Args:
        env_vars: Loaded environment variables.
        required: List of required variable names.
        endpoint_name: Endpoint name for error messages.

    Returns:
        List of missing variable names (empty if all present).

    Example:
        >>> missing = validate_required_env(
        ...     env_vars={"API_KEY": "xxx"},
        ...     required=["API_KEY", "SECRET"],
        ...     endpoint_name="my-endpoint"
        ... )
        >>> missing
        ['SECRET']
    """
    missing = [var for var in required if var not in env_vars]

    if missing:
        logger.warning(
            "Endpoint '%s' is missing required environment variables: %s. "
            "Add them to the .env file in the endpoint folder.",
            endpoint_name,
            missing,
        )

    return missing


def merge_env_with_inheritance(
    endpoint_env: dict[str, str],
    inherit_vars: list[str],
    parent_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Merge endpoint environment with inherited variables from parent.

    Args:
        endpoint_env: Endpoint-specific environment variables.
        inherit_vars: List of variable names to inherit from parent.
        parent_env: Parent environment (defaults to os.environ if None).

    Returns:
        Merged environment dictionary. Endpoint vars take precedence.

    Example:
        >>> merged = merge_env_with_inheritance(
        ...     endpoint_env={"MY_VAR": "value"},
        ...     inherit_vars=["PATH", "HOME"],
        ...     parent_env={"PATH": "/usr/bin", "HOME": "/root", "OTHER": "x"}
        ... )
        >>> "PATH" in merged and "OTHER" not in merged
        True
    """
    import os

    if parent_env is None:
        parent_env = dict(os.environ)

    # Start with inherited variables
    result: dict[str, str] = {}
    for var in inherit_vars:
        if var in parent_env:
            result[var] = parent_env[var]

    # Overlay endpoint-specific vars (they take precedence)
    result.update(endpoint_env)

    return result
