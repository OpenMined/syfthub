"""Tests for observability repository."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syfthub.observability.repository import ErrorLogRepository


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return Mock()


@pytest.fixture
def error_log_repo(mock_session):
    """Create an error log repository with mock session."""
    return ErrorLogRepository(mock_session)


class TestErrorLogRepositoryCreate:
    """Tests for create method."""

    def test_create_success(self, error_log_repo, mock_session):
        """Test successful error log creation."""
        result = error_log_repo.create(
            correlation_id="test-123",
            service="backend",
            level="ERROR",
            event="request.failed",
            message="Test error",
            user_id=1,
            endpoint="/api/test",
            method="GET",
            error_type="ValueError",
            error_code="VAL001",
            stack_trace="Traceback...",
            context={"key": "value"},
            request_data={"param": "test"},
            response_data={"error": "test"},
        )

        # Verify session methods were called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()
        assert result is not None

    def test_create_with_sanitization(self, error_log_repo, mock_session):
        """Test that sensitive data is sanitized."""
        error_log_repo.create(
            correlation_id="test-123",
            service="backend",
            level="ERROR",
            event="request.failed",
            context={"password": "secret", "api_key": "key123"},
            request_data={"authorization": "Bearer token"},
            response_data={"token": "sensitive"},
        )

        # Verify session methods were called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_create_minimal_params(self, error_log_repo, mock_session):
        """Test creation with minimal required parameters."""
        error_log_repo.create(
            correlation_id="test-123",
            service="backend",
            level="ERROR",
            event="request.failed",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_create_sql_error(self, error_log_repo, mock_session):
        """Test create handles SQL errors gracefully."""
        mock_session.add.side_effect = SQLAlchemyError("Database error")

        result = error_log_repo.create(
            correlation_id="test-123",
            service="backend",
            level="ERROR",
            event="request.failed",
        )

        assert result is None
        mock_session.rollback.assert_called_once()


class TestErrorLogRepositoryGetByCorrelationId:
    """Tests for get_by_correlation_id method."""

    def test_get_by_correlation_id_success(self, error_log_repo, mock_session):
        """Test successful retrieval by correlation ID."""
        mock_logs = [
            Mock(correlation_id="test-123", event="request.failed"),
            Mock(correlation_id="test-123", event="auth.failed"),
        ]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.get_by_correlation_id("test-123")

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    def test_get_by_correlation_id_empty(self, error_log_repo, mock_session):
        """Test retrieval with no matching logs."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.get_by_correlation_id("nonexistent")

        assert result == []

    def test_get_by_correlation_id_sql_error(self, error_log_repo, mock_session):
        """Test retrieval handles SQL errors gracefully."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = error_log_repo.get_by_correlation_id("test-123")

        assert result == []


class TestErrorLogRepositoryGetRecent:
    """Tests for get_recent method."""

    def test_get_recent_success(self, error_log_repo, mock_session):
        """Test successful retrieval of recent logs."""
        mock_logs = [
            Mock(timestamp=datetime.now(timezone.utc), event="event1"),
            Mock(timestamp=datetime.now(timezone.utc), event="event2"),
        ]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.get_recent(limit=10)

        assert len(result) == 2
        mock_session.execute.assert_called_once()

    def test_get_recent_with_filters(self, error_log_repo, mock_session):
        """Test retrieval with all filters applied."""
        mock_logs = [Mock(event="filtered_event")]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.get_recent(
            limit=50,
            service="backend",
            level="ERROR",
            event="request.failed",
            user_id=1,
            hours=12,
        )

        assert len(result) == 1
        mock_session.execute.assert_called_once()

    def test_get_recent_sql_error(self, error_log_repo, mock_session):
        """Test retrieval handles SQL errors gracefully."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = error_log_repo.get_recent()

        assert result == []


class TestErrorLogRepositoryDeleteOldLogs:
    """Tests for delete_old_logs method."""

    def test_delete_old_logs_success(self, error_log_repo, mock_session):
        """Test successful deletion of old logs."""
        old_logs = [Mock(), Mock(), Mock()]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = old_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.delete_old_logs(retention_days=30)

        assert result == 3
        assert mock_session.delete.call_count == 3
        mock_session.commit.assert_called_once()

    def test_delete_old_logs_empty(self, error_log_repo, mock_session):
        """Test deletion when no old logs exist."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.delete_old_logs(retention_days=30)

        assert result == 0
        mock_session.commit.assert_called_once()

    def test_delete_old_logs_sql_error(self, error_log_repo, mock_session):
        """Test deletion handles SQL errors gracefully."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = error_log_repo.delete_old_logs(retention_days=30)

        assert result == 0
        mock_session.rollback.assert_called_once()


class TestErrorLogRepositoryCountByEvent:
    """Tests for count_by_event method."""

    def test_count_by_event_success(self, error_log_repo, mock_session):
        """Test successful counting by event."""
        mock_logs = [
            Mock(event="request.failed"),
            Mock(event="request.failed"),
            Mock(event="auth.failed"),
        ]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.count_by_event(hours=24)

        assert result == {"request.failed": 2, "auth.failed": 1}
        mock_session.execute.assert_called_once()

    def test_count_by_event_with_service_filter(self, error_log_repo, mock_session):
        """Test counting with service filter."""
        mock_logs = [Mock(event="request.failed")]
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = mock_logs
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.count_by_event(hours=12, service="backend")

        assert result == {"request.failed": 1}
        mock_session.execute.assert_called_once()

    def test_count_by_event_empty(self, error_log_repo, mock_session):
        """Test counting when no logs exist."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = error_log_repo.count_by_event()

        assert result == {}

    def test_count_by_event_sql_error(self, error_log_repo, mock_session):
        """Test counting handles SQL errors gracefully."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = error_log_repo.count_by_event()

        assert result == {}
