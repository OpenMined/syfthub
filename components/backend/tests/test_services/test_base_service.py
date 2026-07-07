"""Tests for BaseService."""

from unittest.mock import MagicMock

import pytest

from syfthub.services.base import BaseService


class TestBaseService:
    """Tests for BaseService class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def base_service(self, mock_session):
        """Create BaseService instance with mock session."""
        return BaseService(mock_session)

    def test_init(self, base_service, mock_session):
        """Test BaseService initialization."""
        assert base_service.session == mock_session

    def test_commit(self, base_service, mock_session):
        """Test commit method."""
        base_service.commit()
        mock_session.commit.assert_called_once()

    def test_rollback(self, base_service, mock_session):
        """Test rollback method."""
        base_service.rollback()
        mock_session.rollback.assert_called_once()

    def test_refresh(self, base_service, mock_session):
        """Test refresh method."""
        mock_instance = MagicMock()
        base_service.refresh(mock_instance)
        mock_session.refresh.assert_called_once_with(mock_instance)
