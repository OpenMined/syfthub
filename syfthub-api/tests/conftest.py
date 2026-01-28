"""
Shared test fixtures for syfthub-api tests.

This module provides pytest fixtures that are available to all test modules.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest

from syfthub_api import Document, Message, SyftAPI


@pytest.fixture(autouse=True)
def set_test_env_vars() -> Generator[None, None, None]:
    """Set required environment variables for all tests."""
    env_vars = {
        "SYFTHUB_URL": "http://test.example.com",
        "SYFTHUB_USERNAME": "testuser",
        "SYFTHUB_PASSWORD": "testpassword",
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

        # Mock auth.login to return a user-like object
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_client.auth.login.return_value = mock_user

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
    """Create a SyftAPI instance for testing."""
    api = SyftAPI()
    api._skip_sync = True  # Don't sync in tests
    return api


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
