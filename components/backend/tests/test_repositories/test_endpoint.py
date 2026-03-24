"""Tests for EndpointRepository.is_archived method."""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from syfthub.models.endpoint import EndpointModel
from syfthub.repositories.endpoint import EndpointRepository
from syfthub.repositories.user import UserRepository


@pytest.fixture
def endpoint_repo(test_session: Session) -> EndpointRepository:
    """Create EndpointRepository instance for testing."""
    return EndpointRepository(test_session)


@pytest.fixture
def test_user(test_session: Session, sample_user_data: dict):
    """Create a test user in the database."""
    user_repo = UserRepository(test_session)
    return user_repo.create(**sample_user_data)


@pytest.fixture
def active_endpoint(test_session: Session, test_user) -> EndpointModel:
    """Create a non-archived, active endpoint in the database."""
    endpoint = EndpointModel(
        user_id=test_user.id,
        name="Active Endpoint",
        slug="active-endpoint",
        description="An active endpoint",
        type="model",
        visibility="public",
        is_active=True,
        archived=False,
        contributors=[],
        version="0.1.0",
        readme="",
        stars_count=0,
        policies=[],
    )
    test_session.add(endpoint)
    test_session.commit()
    test_session.refresh(endpoint)
    return endpoint


@pytest.fixture
def archived_endpoint(test_session: Session, test_user) -> EndpointModel:
    """Create an archived endpoint in the database."""
    endpoint = EndpointModel(
        user_id=test_user.id,
        name="Archived Endpoint",
        slug="archived-endpoint",
        description="An archived endpoint",
        type="model",
        visibility="public",
        is_active=True,
        archived=True,
        contributors=[],
        version="0.1.0",
        readme="",
        stars_count=0,
        policies=[],
    )
    test_session.add(endpoint)
    test_session.commit()
    test_session.refresh(endpoint)
    return endpoint


class TestIsArchived:
    """Tests for EndpointRepository.is_archived method."""

    def test_returns_true_for_archived_endpoint(
        self,
        endpoint_repo: EndpointRepository,
        archived_endpoint: EndpointModel,
    ):
        """is_archived returns True when the endpoint has archived=True."""
        result = endpoint_repo.is_archived(archived_endpoint.id)
        assert result is True

    def test_returns_false_for_non_archived_endpoint(
        self,
        endpoint_repo: EndpointRepository,
        active_endpoint: EndpointModel,
    ):
        """is_archived returns False when the endpoint has archived=False."""
        result = endpoint_repo.is_archived(active_endpoint.id)
        assert result is False

    def test_returns_false_for_nonexistent_endpoint(
        self,
        endpoint_repo: EndpointRepository,
    ):
        """is_archived returns False when the endpoint ID does not exist."""
        result = endpoint_repo.is_archived(999999)
        assert result is False

    def test_queries_only_archived_column(
        self,
        test_session: Session,
        active_endpoint: EndpointModel,
    ):
        """is_archived performs a lightweight query selecting only the archived column.

        This verifies the method uses select(model.archived) rather than loading
        the full model, which is important for guard-check performance.
        """
        # We use a mock session to inspect the SQL statement passed to execute
        mock_session = Mock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = False
        mock_session.execute.return_value = mock_result

        repo = EndpointRepository(mock_session)
        repo.is_archived(active_endpoint.id)

        # Verify execute was called exactly once
        mock_session.execute.assert_called_once()

        # Inspect the compiled SQL statement to confirm it selects only the
        # archived column, not the full row.
        stmt = mock_session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "endpoints.archived" in compiled
        # Should NOT select all columns (no "endpoints.name", etc.)
        assert "endpoints.name" not in compiled

    def test_returns_false_on_sqlalchemy_error(self):
        """is_archived returns False when a SQLAlchemyError occurs."""
        mock_session = Mock()
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        repo = EndpointRepository(mock_session)
        result = repo.is_archived(1)

        assert result is False
