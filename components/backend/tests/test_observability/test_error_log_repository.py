"""Tests for ErrorLogRepository."""

from unittest.mock import MagicMock

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from syfthub.observability.models import ErrorLogModel
from syfthub.observability.repository import ErrorLogRepository


def _make_mock_log(
    event: str = "request.failed", correlation_id: str = "corr-1"
) -> MagicMock:
    """Create a mock ErrorLogModel with minimal required fields."""
    log = MagicMock(spec=ErrorLogModel)
    log.event = event
    log.correlation_id = correlation_id
    return log


def _make_repo() -> tuple[ErrorLogRepository, MagicMock]:
    """Return (repo, mock_session) pair."""
    session = MagicMock(spec=Session)
    return ErrorLogRepository(session), session


class TestErrorLogRepositoryCreate:
    """Tests for ErrorLogRepository.create()."""

    def test_create_success_returns_model(self):
        """Successful create: session.add/commit/refresh called, model returned."""
        repo, session = _make_repo()

        result = repo.create(
            correlation_id="corr-1",
            service="backend",
            level="ERROR",
            event="request.failed",
            message="Something broke",
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result is not None

    def test_create_with_all_optional_fields(self):
        """create() sanitizes and stores optional context/request/response."""
        repo, session = _make_repo()

        result = repo.create(
            correlation_id="corr-2",
            service="backend",
            level="WARNING",
            event="auth.failed",
            message="Bad token",
            user_id=42,
            endpoint="/api/v1/login",
            method="POST",
            error_type="ValueError",
            error_code="E001",
            stack_trace="Traceback ...",
            context={"key": "value", "password": "secret"},
            request_data={"body": "data"},
            response_data={"error": "message"},
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        assert result is not None

    def test_create_sqlalchemy_error_returns_none(self):
        """SQLAlchemyError during commit → rollback, returns None."""
        repo, session = _make_repo()
        session.commit.side_effect = SQLAlchemyError("DB gone")

        result = repo.create(
            correlation_id="corr-3",
            service="backend",
            level="ERROR",
            event="db.error",
        )

        assert result is None
        session.rollback.assert_called_once()


class TestErrorLogRepositoryGetByCorrelationId:
    """Tests for ErrorLogRepository.get_by_correlation_id()."""

    def test_returns_list_of_logs(self):
        """Returns matching logs for the correlation ID."""
        repo, session = _make_repo()
        mock_logs = [_make_mock_log("event.a"), _make_mock_log("event.b")]
        session.execute.return_value.scalars.return_value.all.return_value = mock_logs

        result = repo.get_by_correlation_id("corr-abc")

        assert result == mock_logs
        session.execute.assert_called_once()

    def test_returns_empty_list_when_not_found(self):
        """Returns [] when no logs match."""
        repo, session = _make_repo()
        session.execute.return_value.scalars.return_value.all.return_value = []

        result = repo.get_by_correlation_id("nonexistent")

        assert result == []

    def test_returns_empty_list_on_sqlalchemy_error(self):
        """SQLAlchemyError during query → returns []."""
        repo, session = _make_repo()
        session.execute.side_effect = SQLAlchemyError("query failed")

        result = repo.get_by_correlation_id("corr-xyz")

        assert result == []


class TestErrorLogRepositoryGetRecent:
    """Tests for ErrorLogRepository.get_recent()."""

    def test_returns_recent_logs_no_filters(self):
        """Returns logs without any optional filters."""
        repo, session = _make_repo()
        mock_logs = [_make_mock_log("event.x")]
        session.execute.return_value.scalars.return_value.all.return_value = mock_logs

        result = repo.get_recent()

        assert result == mock_logs
        session.execute.assert_called_once()

    def test_applies_all_filters(self):
        """Applying service, level, event, user_id filters builds a query."""
        repo, session = _make_repo()
        session.execute.return_value.scalars.return_value.all.return_value = []

        result = repo.get_recent(
            limit=50,
            service="backend",
            level="ERROR",
            event="request.failed",
            user_id=7,
            hours=12,
        )

        assert result == []
        session.execute.assert_called_once()

    def test_returns_empty_list_on_sqlalchemy_error(self):
        """SQLAlchemyError during query → returns []."""
        repo, session = _make_repo()
        session.execute.side_effect = SQLAlchemyError("timeout")

        result = repo.get_recent(service="backend")

        assert result == []


class TestErrorLogRepositoryDeleteOldLogs:
    """Tests for ErrorLogRepository.delete_old_logs()."""

    def test_deletes_old_logs_and_returns_count(self):
        """Deletes each old log and commits; returns count."""
        repo, session = _make_repo()
        old_logs = [_make_mock_log("old.event"), _make_mock_log("old.event")]
        session.execute.return_value.scalars.return_value.all.return_value = old_logs

        count = repo.delete_old_logs(retention_days=30)

        assert count == 2
        assert session.delete.call_count == 2
        session.commit.assert_called_once()

    def test_returns_zero_when_no_old_logs(self):
        """Returns 0 and skips commit when nothing to delete."""
        repo, session = _make_repo()
        session.execute.return_value.scalars.return_value.all.return_value = []

        count = repo.delete_old_logs(retention_days=90)

        assert count == 0
        session.commit.assert_called_once()

    def test_returns_zero_on_sqlalchemy_error(self):
        """SQLAlchemyError during cleanup → rollback, returns 0."""
        repo, session = _make_repo()
        session.execute.side_effect = SQLAlchemyError("lock timeout")

        count = repo.delete_old_logs()

        assert count == 0
        session.rollback.assert_called_once()


class TestErrorLogRepositoryCountByEvent:
    """Tests for ErrorLogRepository.count_by_event()."""

    def test_returns_event_counts(self):
        """Groups logs by event and returns counts."""
        repo, session = _make_repo()
        mock_logs = [
            _make_mock_log("auth.failed"),
            _make_mock_log("auth.failed"),
            _make_mock_log("request.error"),
        ]
        session.execute.return_value.scalars.return_value.all.return_value = mock_logs

        result = repo.count_by_event(hours=24)

        assert result == {"auth.failed": 2, "request.error": 1}

    def test_applies_service_filter(self):
        """Passes service filter through to the query."""
        repo, session = _make_repo()
        session.execute.return_value.scalars.return_value.all.return_value = []

        result = repo.count_by_event(hours=6, service="backend")

        assert result == {}
        session.execute.assert_called_once()

    def test_returns_empty_dict_on_sqlalchemy_error(self):
        """SQLAlchemyError → returns {}."""
        repo, session = _make_repo()
        session.execute.side_effect = SQLAlchemyError("conn refused")

        result = repo.count_by_event()

        assert result == {}
