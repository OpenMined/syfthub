"""Test utilities for creating test data."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def get_test_user_data(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Get complete user data for testing.

    Args:
        override: Optional dictionary to override default values

    Returns:
        Dictionary with all required User model fields
    """
    default_data = {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "age": 25,
        "role": "user",
        "password_hash": "hashed_password",
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
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
    default_data = {
        "username": "testuser",
        "email": "test@example.com",
        "full_name": "Test User",
        "age": 25,
        "role": "user",
        "password_hash": "hashed_password",
        "is_active": True,
    }

    if override:
        default_data.update(override)

    return default_data
