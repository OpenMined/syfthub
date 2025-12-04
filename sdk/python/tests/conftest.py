"""Pytest configuration for SyftHub SDK tests.

This file contains shared fixtures and configuration for all tests.
Integration tests have their own conftest.py in tests/integration/.

To run integration tests, start the backend first:
    cd ../backend && uv run uvicorn syfthub.main:app --reload

Then run tests:
    uv run pytest tests/integration/ -v

Or to run all tests (unit + integration):
    uv run pytest tests/ -v
"""

from __future__ import annotations

import pytest


@pytest.fixture
def base_url() -> str:
    """Return test base URL."""
    return "https://test.syfthub.com"


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require running backend)",
    )
