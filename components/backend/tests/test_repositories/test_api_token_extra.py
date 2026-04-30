"""Additional tests for APITokenRepository exception paths."""

from unittest.mock import MagicMock

import pytest

from syfthub.repositories.api_token import APITokenRepository


@pytest.fixture
def repo():
    session = MagicMock()
    return APITokenRepository(session)


class TestAPITokenRepositoryExceptionPaths:
    def test_get_by_hash_returns_none_on_exception(self, repo):
        repo.session.execute.side_effect = Exception("DB error")
        result = repo.get_by_hash("abc123")
        assert result is None

    def test_get_by_id_for_user_returns_none_on_exception(self, repo):
        repo.session.execute.side_effect = Exception("DB error")
        result = repo.get_by_id_for_user(1, 1)
        assert result is None

    def test_get_user_tokens_returns_empty_on_exception(self, repo):
        repo.session.execute.side_effect = Exception("DB error")
        result = repo.get_user_tokens(1)
        assert result == []

    def test_create_token_returns_none_on_exception(self, repo):
        repo.session.add = MagicMock()
        repo.session.commit.side_effect = Exception("DB error")
        result = repo.create_token(
            user_id=1,
            name="test",
            token_prefix="syft_",
            token_hash="hash123",
            scopes=["read"],
        )
        assert result is None
        repo.session.rollback.assert_called_once()

    def test_update_last_used_returns_false_on_exception(self, repo):
        repo.session.get.side_effect = Exception("DB error")
        result = repo.update_last_used(1)
        assert result is False
        repo.session.rollback.assert_called_once()

    def test_update_last_used_returns_false_when_token_not_found(self, repo):
        repo.session.get.return_value = None
        result = repo.update_last_used(999)
        assert result is False

    def test_revoke_returns_false_on_exception(self, repo):
        repo.session.execute.side_effect = Exception("DB error")
        result = repo.revoke(1, 1)
        assert result is False

    def test_delete_token_returns_false_on_exception(self, repo):
        repo.session.execute.side_effect = Exception("DB error")
        result = repo.delete_token(1, 1)
        assert result is False
