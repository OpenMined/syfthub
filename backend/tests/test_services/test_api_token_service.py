"""Tests for APITokenService."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from syfthub.schemas.api_token import APITokenCreate, APITokenScope, APITokenUpdate
from syfthub.schemas.user import User
from syfthub.services.api_token_service import MAX_TOKENS_PER_USER, APITokenService


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def api_token_service(mock_session):
    """Create APITokenService with mock session."""
    return APITokenService(mock_session)


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        role="user",
        is_active=True,
        created_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2023-01-01T00:00:00"),
        age=25,
        password_hash="hashed_pass",
    )


@pytest.fixture
def mock_token_model():
    """Create a mock token model returned from repository."""
    model = MagicMock()
    model.id = 1
    model.name = "Test Token"
    model.token_prefix = "syft_pat_aB3dE5f"
    model.token_hash = "abcdef123456"
    model.scopes = ["full"]
    model.expires_at = None
    model.last_used_at = None
    model.last_used_ip = None
    model.is_active = True
    model.created_at = datetime.now(timezone.utc)
    model.updated_at = datetime.now(timezone.utc)
    return model


class TestAPITokenServiceCreate:
    """Tests for token creation."""

    def test_create_token_success(
        self,
        api_token_service: APITokenService,
        mock_user: User,
        mock_token_model,
    ):
        """Test successful token creation."""
        create_data = APITokenCreate(name="CI/CD Pipeline", scopes=[APITokenScope.FULL])

        with (
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "hash_exists",
                return_value=False,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "create_token",
                return_value=mock_token_model,
            ),
        ):
            result = api_token_service.create_token(mock_user, create_data)

            assert result.id == 1
            assert result.name == "Test Token"
            assert result.token is not None
            assert result.token.startswith("syft_pat_")

    def test_create_token_max_limit_reached(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test token creation when user has reached max limit."""
        create_data = APITokenCreate(name="Another Token", scopes=[APITokenScope.FULL])

        with patch.object(
            api_token_service.api_token_repository,
            "count_user_tokens",
            return_value=MAX_TOKENS_PER_USER,
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.create_token(mock_user, create_data)

            assert exc_info.value.status_code == 400
            assert "Maximum number of API tokens" in exc_info.value.detail

    def test_create_token_hash_collision_retry(
        self,
        api_token_service: APITokenService,
        mock_user: User,
        mock_token_model,
    ):
        """Test token creation retries on hash collision."""
        create_data = APITokenCreate(name="Token", scopes=[APITokenScope.FULL])

        # First call returns True (collision), second returns False
        hash_exists_results = [True, False]

        with (
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "hash_exists",
                side_effect=hash_exists_results,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "create_token",
                return_value=mock_token_model,
            ),
        ):
            result = api_token_service.create_token(mock_user, create_data)
            assert result is not None

    def test_create_token_hash_collision_max_retries(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test token creation fails after max hash collision retries."""
        create_data = APITokenCreate(name="Token", scopes=[APITokenScope.FULL])

        with (
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
            patch.object(
                api_token_service.api_token_repository, "hash_exists", return_value=True
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.create_token(mock_user, create_data)

            assert exc_info.value.status_code == 500
            assert "Failed to generate unique token" in exc_info.value.detail

    def test_create_token_repository_failure(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test token creation fails when repository returns None."""
        create_data = APITokenCreate(name="Token", scopes=[APITokenScope.FULL])

        with (
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "hash_exists",
                return_value=False,
            ),
            patch.object(
                api_token_service.api_token_repository,
                "create_token",
                return_value=None,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.create_token(mock_user, create_data)

            assert exc_info.value.status_code == 500
            assert "Failed to create API token" in exc_info.value.detail


class TestAPITokenServiceList:
    """Tests for token listing."""

    def test_list_tokens_empty(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test listing tokens when user has none."""
        with (
            patch.object(
                api_token_service.api_token_repository,
                "get_user_tokens",
                return_value=[],
            ),
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
        ):
            result = api_token_service.list_tokens(mock_user)

            assert result.tokens == []
            assert result.total == 0

    def test_list_tokens_with_results(
        self,
        api_token_service: APITokenService,
        mock_user: User,
        mock_token_model,
    ):
        """Test listing tokens returns correct data."""
        with (
            patch.object(
                api_token_service.api_token_repository,
                "get_user_tokens",
                return_value=[mock_token_model],
            ),
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=1,
            ),
        ):
            result = api_token_service.list_tokens(mock_user)

            assert len(result.tokens) == 1
            assert result.total == 1
            assert result.tokens[0].name == "Test Token"

    def test_list_tokens_pagination(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test listing tokens with pagination parameters."""
        with (
            patch.object(
                api_token_service.api_token_repository,
                "get_user_tokens",
                return_value=[],
            ) as mock_get,
            patch.object(
                api_token_service.api_token_repository,
                "count_user_tokens",
                return_value=0,
            ),
        ):
            api_token_service.list_tokens(mock_user, skip=10, limit=20)

            mock_get.assert_called_once_with(
                user_id=mock_user.id,
                include_inactive=False,
                skip=10,
                limit=20,
            )


class TestAPITokenServiceGet:
    """Tests for getting a single token."""

    def test_get_token_success(
        self,
        api_token_service: APITokenService,
        mock_user: User,
        mock_token_model,
    ):
        """Test getting a token by ID."""
        with patch.object(
            api_token_service.api_token_repository,
            "get_by_id_for_user",
            return_value=mock_token_model,
        ):
            result = api_token_service.get_token(mock_user, 1)

            assert result.id == 1
            assert result.name == "Test Token"

    def test_get_token_not_found(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test getting a non-existent token raises 404."""
        with patch.object(
            api_token_service.api_token_repository,
            "get_by_id_for_user",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.get_token(mock_user, 999)

            assert exc_info.value.status_code == 404
            assert "API token not found" in exc_info.value.detail


class TestAPITokenServiceUpdate:
    """Tests for updating a token."""

    def test_update_token_success(
        self,
        api_token_service: APITokenService,
        mock_user: User,
        mock_token_model,
    ):
        """Test successful token name update."""
        mock_token_model.name = "Updated Name"
        update_data = APITokenUpdate(name="Updated Name")

        with patch.object(
            api_token_service.api_token_repository,
            "update_name",
            return_value=mock_token_model,
        ):
            result = api_token_service.update_token(mock_user, 1, update_data)

            assert result.name == "Updated Name"

    def test_update_token_not_found(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test updating non-existent token raises 404."""
        update_data = APITokenUpdate(name="New Name")

        with patch.object(
            api_token_service.api_token_repository, "update_name", return_value=None
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.update_token(mock_user, 999, update_data)

            assert exc_info.value.status_code == 404


class TestAPITokenServiceRevoke:
    """Tests for revoking a token."""

    def test_revoke_token_success(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test successful token revocation."""
        with patch.object(
            api_token_service.api_token_repository, "revoke", return_value=True
        ):
            # Should not raise
            api_token_service.revoke_token(mock_user, 1)

    def test_revoke_token_not_found(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test revoking non-existent token raises 404."""
        with patch.object(
            api_token_service.api_token_repository, "revoke", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.revoke_token(mock_user, 999)

            assert exc_info.value.status_code == 404


class TestAPITokenServiceDelete:
    """Tests for deleting a token."""

    def test_delete_token_success(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test successful token deletion."""
        with patch.object(
            api_token_service.api_token_repository, "delete_token", return_value=True
        ):
            # Should not raise
            api_token_service.delete_token(mock_user, 1)

    def test_delete_token_not_found(
        self,
        api_token_service: APITokenService,
        mock_user: User,
    ):
        """Test deleting non-existent token raises 404."""
        with patch.object(
            api_token_service.api_token_repository, "delete_token", return_value=False
        ):
            with pytest.raises(HTTPException) as exc_info:
                api_token_service.delete_token(mock_user, 999)

            assert exc_info.value.status_code == 404
