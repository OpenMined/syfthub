"""Tests for APITokenRepository."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from syfthub.auth.api_tokens import generate_api_token
from syfthub.repositories.api_token import APITokenRepository
from syfthub.repositories.user import UserRepository


@pytest.fixture
def api_token_repo(test_session: Session) -> APITokenRepository:
    """Create APITokenRepository instance for testing."""
    return APITokenRepository(test_session)


@pytest.fixture
def test_user(test_session: Session, sample_user_data: dict):
    """Create a test user in the database."""
    user_repo = UserRepository(test_session)
    return user_repo.create(sample_user_data)


@pytest.fixture
def sample_token_data():
    """Generate sample token data for testing."""
    full_token, token_hash, token_prefix = generate_api_token()
    return {
        "full_token": full_token,
        "token_hash": token_hash,
        "token_prefix": token_prefix,
        "name": "Test Token",
        "scopes": ["full"],
    }


class TestAPITokenRepositoryCreate:
    """Tests for token creation."""

    def test_create_token_success(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test successful token creation."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        assert token is not None
        assert token.id is not None
        assert token.user_id == test_user.id
        assert token.name == "Test Token"
        assert token.token_prefix == sample_token_data["token_prefix"]
        assert token.token_hash == sample_token_data["token_hash"]
        assert token.scopes == ["full"]
        assert token.is_active is True
        assert token.expires_at is None
        assert token.last_used_at is None

    def test_create_token_with_expiration(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test token creation with expiration date."""
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=["read"],
            expires_at=expires_at,
        )

        assert token is not None
        assert token.expires_at is not None
        assert token.scopes == ["read"]

    def test_create_token_with_multiple_scopes(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test token creation with multiple scopes."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=["read", "write"],
        )

        assert token is not None
        assert token.scopes == ["read", "write"]


class TestAPITokenRepositoryGetByHash:
    """Tests for get_by_hash method."""

    def test_get_by_hash_found(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test getting token by hash when it exists."""
        created_token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        found_token = api_token_repo.get_by_hash(sample_token_data["token_hash"])

        assert found_token is not None
        assert found_token.id == created_token.id
        assert found_token.user_id == test_user.id

    def test_get_by_hash_not_found(self, api_token_repo: APITokenRepository):
        """Test getting token by non-existent hash."""
        result = api_token_repo.get_by_hash("nonexistent_hash")
        assert result is None


class TestAPITokenRepositoryGetByIdForUser:
    """Tests for get_by_id_for_user method."""

    def test_get_by_id_for_user_found(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test getting token by ID for correct user."""
        created_token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        found_token = api_token_repo.get_by_id_for_user(created_token.id, test_user.id)

        assert found_token is not None
        assert found_token.id == created_token.id

    def test_get_by_id_for_user_wrong_user(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test getting token by ID for wrong user returns None."""
        created_token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        # Try to get with different user ID
        found_token = api_token_repo.get_by_id_for_user(created_token.id, 99999)
        assert found_token is None

    def test_get_by_id_for_user_not_found(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test getting non-existent token by ID."""
        found_token = api_token_repo.get_by_id_for_user(99999, test_user.id)
        assert found_token is None


class TestAPITokenRepositoryGetUserTokens:
    """Tests for get_user_tokens method."""

    def test_get_user_tokens_empty(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test getting tokens when user has none."""
        tokens = api_token_repo.get_user_tokens(test_user.id)
        assert tokens == []

    def test_get_user_tokens_multiple(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test getting multiple tokens for a user."""
        # Create multiple tokens
        for i in range(3):
            _, token_hash, token_prefix = generate_api_token()
            api_token_repo.create_token(
                user_id=test_user.id,
                name=f"Token {i}",
                token_prefix=token_prefix,
                token_hash=token_hash,
                scopes=["full"],
            )

        tokens = api_token_repo.get_user_tokens(test_user.id)
        assert len(tokens) == 3

    def test_get_user_tokens_excludes_inactive(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test that inactive tokens are excluded by default."""
        # Create an active token
        _, hash1, prefix1 = generate_api_token()
        api_token_repo.create_token(
            user_id=test_user.id,
            name="Active Token",
            token_prefix=prefix1,
            token_hash=hash1,
            scopes=["full"],
        )

        # Create and revoke a token
        _, hash2, prefix2 = generate_api_token()
        token2 = api_token_repo.create_token(
            user_id=test_user.id,
            name="Revoked Token",
            token_prefix=prefix2,
            token_hash=hash2,
            scopes=["full"],
        )
        api_token_repo.revoke(token2.id, test_user.id)

        # Should only get active token
        tokens = api_token_repo.get_user_tokens(test_user.id, include_inactive=False)
        assert len(tokens) == 1
        assert tokens[0].name == "Active Token"

    def test_get_user_tokens_includes_inactive(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test getting tokens including inactive ones."""
        # Create an active token
        _, hash1, prefix1 = generate_api_token()
        api_token_repo.create_token(
            user_id=test_user.id,
            name="Active Token",
            token_prefix=prefix1,
            token_hash=hash1,
            scopes=["full"],
        )

        # Create and revoke a token
        _, hash2, prefix2 = generate_api_token()
        token2 = api_token_repo.create_token(
            user_id=test_user.id,
            name="Revoked Token",
            token_prefix=prefix2,
            token_hash=hash2,
            scopes=["full"],
        )
        api_token_repo.revoke(token2.id, test_user.id)

        # Should get both tokens
        tokens = api_token_repo.get_user_tokens(test_user.id, include_inactive=True)
        assert len(tokens) == 2

    def test_get_user_tokens_pagination(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test pagination of user tokens."""
        # Create 5 tokens
        for i in range(5):
            _, token_hash, token_prefix = generate_api_token()
            api_token_repo.create_token(
                user_id=test_user.id,
                name=f"Token {i}",
                token_prefix=token_prefix,
                token_hash=token_hash,
                scopes=["full"],
            )

        # Get first page
        page1 = api_token_repo.get_user_tokens(test_user.id, skip=0, limit=2)
        assert len(page1) == 2

        # Get second page
        page2 = api_token_repo.get_user_tokens(test_user.id, skip=2, limit=2)
        assert len(page2) == 2

        # Get third page
        page3 = api_token_repo.get_user_tokens(test_user.id, skip=4, limit=2)
        assert len(page3) == 1


class TestAPITokenRepositoryUpdateLastUsed:
    """Tests for update_last_used method."""

    def test_update_last_used_success(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test updating last used timestamp."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        assert token.last_used_at is None
        assert token.last_used_ip is None

        result = api_token_repo.update_last_used(token.id, "192.168.1.1")
        assert result is True

        # Refresh the token from DB
        updated_token = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert updated_token.last_used_at is not None
        assert updated_token.last_used_ip == "192.168.1.1"

    def test_update_last_used_without_ip(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test updating last used without IP address."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.update_last_used(token.id)
        assert result is True

        updated_token = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert updated_token.last_used_at is not None
        assert updated_token.last_used_ip is None

    def test_update_last_used_not_found(self, api_token_repo: APITokenRepository):
        """Test updating last used for non-existent token."""
        result = api_token_repo.update_last_used(99999, "192.168.1.1")
        assert result is False


class TestAPITokenRepositoryUpdateName:
    """Tests for update_name method."""

    def test_update_name_success(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test successful name update."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        updated_token = api_token_repo.update_name(token.id, test_user.id, "New Name")

        assert updated_token is not None
        assert updated_token.name == "New Name"

    def test_update_name_wrong_user(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test name update with wrong user returns None."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.update_name(token.id, 99999, "New Name")
        assert result is None

    def test_update_name_not_found(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test name update for non-existent token."""
        result = api_token_repo.update_name(99999, test_user.id, "New Name")
        assert result is None


class TestAPITokenRepositoryRevoke:
    """Tests for revoke method."""

    def test_revoke_success(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test successful token revocation."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.revoke(token.id, test_user.id)
        assert result is True

        # Verify token is inactive
        revoked_token = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert revoked_token.is_active is False

    def test_revoke_wrong_user(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test revoke with wrong user returns False."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.revoke(token.id, 99999)
        assert result is False

        # Token should still be active
        still_active = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert still_active.is_active is True

    def test_revoke_not_found(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test revoke for non-existent token."""
        result = api_token_repo.revoke(99999, test_user.id)
        assert result is False


class TestAPITokenRepositoryDelete:
    """Tests for delete_token method."""

    def test_delete_success(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test successful token deletion."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.delete_token(token.id, test_user.id)
        assert result is True

        # Verify token is gone
        deleted_token = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert deleted_token is None

    def test_delete_wrong_user(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test delete with wrong user returns False."""
        token = api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.delete_token(token.id, 99999)
        assert result is False

        # Token should still exist
        still_exists = api_token_repo.get_by_id_for_user(token.id, test_user.id)
        assert still_exists is not None


class TestAPITokenRepositoryCount:
    """Tests for count_user_tokens method."""

    def test_count_user_tokens_empty(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test counting tokens when user has none."""
        count = api_token_repo.count_user_tokens(test_user.id)
        assert count == 0

    def test_count_user_tokens_multiple(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test counting multiple active tokens."""
        for i in range(3):
            _, token_hash, token_prefix = generate_api_token()
            api_token_repo.create_token(
                user_id=test_user.id,
                name=f"Token {i}",
                token_prefix=token_prefix,
                token_hash=token_hash,
                scopes=["full"],
            )

        count = api_token_repo.count_user_tokens(test_user.id)
        assert count == 3

    def test_count_user_tokens_active_only(
        self,
        api_token_repo: APITokenRepository,
        test_user,
    ):
        """Test counting only active tokens."""
        # Create active token
        _, hash1, prefix1 = generate_api_token()
        api_token_repo.create_token(
            user_id=test_user.id,
            name="Active",
            token_prefix=prefix1,
            token_hash=hash1,
            scopes=["full"],
        )

        # Create and revoke token
        _, hash2, prefix2 = generate_api_token()
        token2 = api_token_repo.create_token(
            user_id=test_user.id,
            name="Revoked",
            token_prefix=prefix2,
            token_hash=hash2,
            scopes=["full"],
        )
        api_token_repo.revoke(token2.id, test_user.id)

        # Active only count
        active_count = api_token_repo.count_user_tokens(test_user.id, active_only=True)
        assert active_count == 1

        # All tokens count
        all_count = api_token_repo.count_user_tokens(test_user.id, active_only=False)
        assert all_count == 2


class TestAPITokenRepositoryHashExists:
    """Tests for hash_exists method."""

    def test_hash_exists_true(
        self,
        api_token_repo: APITokenRepository,
        test_user,
        sample_token_data: dict,
    ):
        """Test hash_exists returns True for existing hash."""
        api_token_repo.create_token(
            user_id=test_user.id,
            name=sample_token_data["name"],
            token_prefix=sample_token_data["token_prefix"],
            token_hash=sample_token_data["token_hash"],
            scopes=sample_token_data["scopes"],
        )

        result = api_token_repo.hash_exists(sample_token_data["token_hash"])
        assert result is True

    def test_hash_exists_false(self, api_token_repo: APITokenRepository):
        """Test hash_exists returns False for non-existent hash."""
        result = api_token_repo.hash_exists("nonexistent_hash")
        assert result is False
