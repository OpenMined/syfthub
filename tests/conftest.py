"""Shared pytest fixtures and configuration."""

import pytest


@pytest.fixture
def example_fixture() -> str:
    """Example fixture that can be used across tests."""
    return "test_value"
