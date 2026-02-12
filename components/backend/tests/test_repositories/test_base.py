"""Tests for base repository."""

from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.base import BaseModel
from syfthub.repositories.base import BaseRepository


# Mock model for testing
class MockModel(BaseModel):
    """Mock model for testing."""

    __tablename__ = "mock_table"
    name: str = "test"

    def __init__(self, id=None, name="test"):
        self.id = id
        self.name = name


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return Mock()


@pytest.fixture
def base_repo(mock_session):
    """Create a base repository with mock session and model."""
    return BaseRepository(mock_session, MockModel)


class TestBaseRepositoryBasicOperations:
    """Test basic CRUD operations."""

    def test_get_by_id_success(self, base_repo, mock_session):
        """Test successful get by ID."""
        mock_obj = MockModel(id=1, name="test")
        mock_session.get.return_value = mock_obj

        result = base_repo.get_by_id(1)

        assert result == mock_obj
        mock_session.get.assert_called_once_with(MockModel, 1)

    def test_get_by_id_sql_error(self, base_repo, mock_session):
        """Test get by ID with SQL error."""
        mock_session.get.side_effect = SQLAlchemyError("Database error")

        result = base_repo.get_by_id(1)

        assert result is None

    def test_create_success(self, base_repo, mock_session):
        """Test successful create operation."""
        # Create a working mock object
        mock_obj = MockModel(id=1, name="new_test")

        # Mock the model constructor to return our mock object
        with patch.object(base_repo, "model", return_value=mock_obj):
            base_repo.create(name="new_test")

        # Verify session operations were called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    def test_create_sql_error(self, base_repo, mock_session):
        """Test create operation with SQL error."""
        mock_session.add.side_effect = SQLAlchemyError("Database error")

        result = base_repo.create(name="test")

        assert result is None
        mock_session.rollback.assert_called_once()

    def test_update_success(self, base_repo, mock_session):
        """Test successful update operation."""
        mock_obj = MockModel(id=1, name="old_name")

        with patch.object(base_repo, "get_by_id", return_value=mock_obj):
            base_repo.update(1, name="new_name")

        assert mock_obj.name == "new_name"
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once_with(mock_obj)

    def test_update_not_found(self, base_repo):
        """Test update operation with object not found."""
        with patch.object(base_repo, "get_by_id", return_value=None):
            result = base_repo.update(999, name="new_name")

        assert result is None

    def test_update_sql_error(self, base_repo, mock_session):
        """Test update operation with SQL error."""
        mock_obj = MockModel(id=1, name="old_name")
        mock_session.commit.side_effect = SQLAlchemyError("Database error")

        with patch.object(base_repo, "get_by_id", return_value=mock_obj):
            result = base_repo.update(1, name="new_name")

        assert result is None
        mock_session.rollback.assert_called_once()

    def test_delete_success(self, base_repo, mock_session):
        """Test successful delete operation."""
        mock_obj = MockModel(id=1, name="test")

        with patch.object(base_repo, "get_by_id", return_value=mock_obj):
            result = base_repo.delete(1)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_obj)
        mock_session.commit.assert_called_once()

    def test_delete_not_found(self, base_repo):
        """Test delete operation with object not found."""
        with patch.object(base_repo, "get_by_id", return_value=None):
            result = base_repo.delete(999)

        assert result is False

    def test_delete_sql_error_with_logging(self, base_repo, mock_session):
        """Test delete operation with SQL error and logging."""
        mock_obj = MockModel(id=1, name="test")
        mock_session.delete.side_effect = SQLAlchemyError("Database error")

        with (
            patch.object(base_repo, "get_by_id", return_value=mock_obj),
            patch("logging.getLogger") as mock_get_logger,
        ):
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            result = base_repo.delete(1)

        assert result is False
        mock_session.rollback.assert_called_once()
        mock_logger.error.assert_called_once()


class TestBaseRepositoryQueryOperations:
    """Test query and filter operations."""

    def test_exists_true(self, base_repo, mock_session):
        """Test exists operation returns True."""
        mock_result = Mock()
        mock_result.scalar.return_value = MockModel(id=1)
        mock_session.execute.return_value = mock_result

        result = base_repo.exists(name="test")

        assert result is True

    def test_exists_false(self, base_repo, mock_session):
        """Test exists operation returns False."""
        mock_result = Mock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result

        result = base_repo.exists(name="nonexistent")

        assert result is False

    def test_exists_sql_error(self, base_repo, mock_session):
        """Test exists operation with SQL error."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = base_repo.exists(name="test")

        assert result is False

    def test_count_with_results(self, base_repo, mock_session):
        """Test count operation with results."""
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.all.return_value = [MockModel(id=1), MockModel(id=2)]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = base_repo.count()

        assert result == 2

    def test_count_sql_error(self, base_repo, mock_session):
        """Test count operation with SQL error."""
        mock_session.execute.side_effect = SQLAlchemyError("Database error")

        result = base_repo.count()

        assert result == 0
