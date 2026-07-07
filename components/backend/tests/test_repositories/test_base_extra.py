"""Additional tests for BaseRepository missing branches."""

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.base import BaseModel
from syfthub.repositories.base import BaseRepository


class SimpleModel(BaseModel):
    __tablename__ = "simple_model_table"
    name: str = "default"

    def __init__(self, id=None, name="default"):
        self.id = id
        self.name = name


@pytest.fixture
def mock_session():
    return Mock()


@pytest.fixture
def repo(mock_session):
    return BaseRepository(mock_session, SimpleModel)


class TestGetAllMissingBranches:
    def test_get_all_sql_error(self, repo, mock_session):
        mock_session.execute.side_effect = SQLAlchemyError("DB error")
        result = repo.get_all()
        assert result == []

    def test_get_all_with_nonexistent_field_filter(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = repo.get_all(filters={"nonexistent_field_xyz": "value"})
        assert result == []

    def test_get_all_with_empty_filters(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        result = repo.get_all(filters={})
        assert result == []


class TestUpdateMissingBranches:
    def test_update_with_nonexistent_field_skips(self, repo, mock_session):
        mock_obj = SimpleModel(id=1, name="original")
        mock_session.get.return_value = mock_obj
        repo.update(1, nonexistent_xyz="value")
        assert mock_obj.name == "original"


class TestExistsMissingBranches:
    def test_exists_with_valid_field_filter(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar.return_value = SimpleModel(id=1)
        mock_session.execute.return_value = mock_result
        result = repo.exists(name="test")
        assert result is True

    def test_exists_with_nonexistent_field(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result
        result = repo.exists(nonexistent_xyz="value")
        assert result is False

    def test_exists_no_filters(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar.return_value = SimpleModel(id=1)
        mock_session.execute.return_value = mock_result
        result = repo.exists()
        assert result is True


class TestCountMissingBranches:
    def test_count_with_valid_field_filter(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar_one.return_value = 3
        mock_session.execute.return_value = mock_result
        result = repo.count(filters={"name": "test"})
        assert result == 3

    def test_count_with_nonexistent_field_filter(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result
        result = repo.count(filters={"nonexistent_xyz": "value"})
        assert result == 5

    def test_count_with_empty_filters(self, repo, mock_session):
        mock_result = Mock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result
        result = repo.count(filters={})
        assert result == 0
