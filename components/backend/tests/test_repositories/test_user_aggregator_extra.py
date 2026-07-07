"""Additional tests for UserAggregatorRepository exception paths."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from syfthub.repositories.user_aggregator import UserAggregatorRepository


@pytest.fixture
def repo():
    return UserAggregatorRepository(MagicMock())


class TestUserAggregatorExceptionPaths:
    def test_get_by_user_id_returns_empty_on_error(self, repo):
        repo.session.execute.side_effect = SQLAlchemyError("DB error")
        result = repo.get_by_user_id(1)
        assert result == []

    def test_get_default_by_user_id_returns_none_on_error(self, repo):
        repo.session.execute.side_effect = SQLAlchemyError("DB error")
        result = repo.get_default_by_user_id(1)
        assert result is None

    def test_create_returns_none_on_error(self, repo):
        repo.session.add = MagicMock()
        repo.session.commit.side_effect = SQLAlchemyError("DB error")
        mock_aggregator = MagicMock()
        result = repo.create(mock_aggregator)
        assert result is None
        repo.session.rollback.assert_called_once()

    def test_update_returns_none_when_not_found(self, repo):
        repo.session.get.return_value = None
        result = repo.update(999, {"name": "new_name"})
        assert result is None

    def test_update_returns_none_on_error(self, repo):
        mock_obj = MagicMock()
        repo.session.get.return_value = mock_obj
        repo.session.commit.side_effect = SQLAlchemyError("DB error")
        result = repo.update(1, {"name": "new_name"})
        assert result is None
        repo.session.rollback.assert_called_once()
