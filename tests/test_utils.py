"""Test utilities for creating test data with Ed25519 keys."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from syfthub.auth.security import generate_ed25519_key_pair


def get_dummy_ed25519_keys() -> dict[str, str]:
    """Generate dummy Ed25519 keys for testing.

    Returns a consistent set of dummy keys that can be used across tests.
    """
    # Use a fixed key pair for consistency in tests
    return {
        "private_key": "YmFzZTY0X3ByaXZhdGVfa2V5X2Zvcl90ZXN0aW5nXzMyX2J5dGVz",
        "public_key": "YmFzZTY0X3B1YmxpY19rZXlfZm9yX3Rlc3RpbmdfMzJfYnl0ZXM=",
    }


def get_test_user_data(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get complete user data for testing including Ed25519 keys.

    Args:
        override: Optional dictionary to override default values

    Returns:
        Dictionary with all required User model fields
    """
    keys = get_dummy_ed25519_keys()

    default_data = {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "age": 25,
        "role": "user",
        "password_hash": "hashed_password",
        "public_key": keys["public_key"],
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "key_created_at": datetime.now(timezone.utc),
    }

    if override:
        default_data.update(override)

    return default_data


def get_test_user_model_data(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get user data for creating UserModel database instances.

    Args:
        override: Optional dictionary to override default values

    Returns:
        Dictionary with required UserModel fields (excluding id for creation)
    """
    keys = get_dummy_ed25519_keys()

    default_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "age": 25,
        "role": "user",
        "password_hash": "hashed_password",
        "public_key": keys["public_key"],
        "is_active": True,
    }

    if override:
        default_data.update(override)

    return default_data


def generate_unique_test_keys() -> dict[str, str]:
    """Generate unique Ed25519 keys for tests that need different keys.

    Returns:
        Dictionary with newly generated private_key and public_key
    """
    key_pair = generate_ed25519_key_pair()
    return {
        "private_key": key_pair.private_key,
        "public_key": key_pair.public_key,
    }
