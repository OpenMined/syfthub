"""Shared pytest fixtures and configuration."""

import os

# Disable accounting integration for tests - must be set before syfthub imports
# This environment variable is read by Settings() during initialization
os.environ["DEFAULT_ACCOUNTING_URL"] = ""

import pytest


@pytest.fixture(autouse=True)
def disable_accounting_integration(monkeypatch):
    """Disable accounting service integration for all tests.

    This fixture ensures no external accounting service calls are made during tests.
    It sets the default_accounting_url to empty string, which causes the
    auth service to skip accounting integration entirely.

    The auth_service._handle_accounting_registration() checks:
        if not effective_url:
            return (None, None)  # Skip accounting

    Empty string evaluates to False, so accounting is skipped.
    """
    monkeypatch.setattr(
        "syfthub.core.config.settings.default_accounting_url",
        "",
    )
    yield


@pytest.fixture
def example_fixture() -> str:
    """Example fixture that can be used across tests."""
    return "test_value"
