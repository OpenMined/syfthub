"""
Shared test fixtures for syfthub-api tests.

This module provides pytest fixtures that are available to all test modules.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from syfthub_api import Document, Message, SyftAPI, UserContext


# Dummy user returned by the mocked token verification
TEST_USER = UserContext(
    sub="test-user-id",
    email="test@example.com",
    username="testuser",
    role="user",
)


@pytest.fixture(autouse=True)
def set_test_env_vars() -> Generator[None, None, None]:
    """Set required environment variables for all tests."""
    env_vars = {
        "SYFTHUB_URL": "http://test.example.com",
        "SYFTHUB_API_KEY": "syft_pat_test_token",
        "SPACE_URL": "http://localhost:8001",
        "LOG_LEVEL": "DEBUG",
    }
    with patch.dict(os.environ, env_vars):
        yield


@pytest.fixture
def mock_syfthub_client() -> Generator[MagicMock, None, None]:
    """Mock the SyftHubClient for testing without network calls."""
    with patch("syfthub_api.app.SyftHubClient") as mock_client_class:
        mock_client = MagicMock()

        # Mock auth.me to return user (for API token auth)
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_client.auth.me.return_value = mock_user

        # Mock users.update to return updated user
        mock_updated_user = MagicMock()
        mock_updated_user.domain = "http://localhost:8001"
        mock_client.users.update.return_value = mock_updated_user

        # Mock my_endpoints.sync to return sync result
        mock_sync_result = MagicMock()
        mock_sync_result.synced = 2
        mock_sync_result.deleted = 0
        mock_client.my_endpoints.sync.return_value = mock_sync_result

        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def app() -> SyftAPI:
    """Create a SyftAPI instance for testing.

    Token verification is mocked to return TEST_USER, so all
    endpoints can be called with any Bearer token.
    """
    api = SyftAPI()
    api._skip_sync = True  # Don't sync in tests

    # Mock satellite token verification — always returns TEST_USER
    async def _mock_verify_satellite_token(token: str) -> UserContext:
        return TEST_USER

    api._verify_satellite_token = _mock_verify_satellite_token  # type: ignore[assignment]
    return api


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Authorization headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def sample_documents() -> list[Document]:
    """Sample documents for testing."""
    return [
        Document(
            document_id="doc-1",
            content="Test content about machine learning.",
            metadata={"source": "test", "category": "ml"},
            similarity_score=0.95,
        ),
        Document(
            document_id="doc-2",
            content="Another document about data science.",
            metadata={"source": "test", "category": "ds"},
            similarity_score=0.87,
        ),
        Document(
            document_id="doc-3",
            content="Research on neural networks.",
            metadata={"source": "test"},
            similarity_score=0.82,
        ),
    ]


@pytest.fixture
def sample_messages() -> list[Message]:
    """Sample messages for testing model endpoints."""
    return [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="What is machine learning?"),
        Message(role="assistant", content="Machine learning is a subset of AI..."),
        Message(role="user", content="Can you explain neural networks?"),
    ]
