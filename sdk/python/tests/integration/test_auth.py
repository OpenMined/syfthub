"""Integration tests for authentication."""

from __future__ import annotations

import pytest
from syfthub_sdk import SyftHubClient, User
from syfthub_sdk.exceptions import APIError, AuthenticationError, ValidationError


class TestRegistration:
    """Tests for user registration."""

    def test_register_new_user(
        self,
        client: SyftHubClient,
        test_user_credentials: dict[str, str],
    ) -> None:
        """Test registering a new user returns User object."""
        user = client.auth.register(
            username=test_user_credentials["username"],
            email=test_user_credentials["email"],
            password=test_user_credentials["password"],
            full_name=test_user_credentials["full_name"],
        )

        assert isinstance(user, User)
        assert user.username == test_user_credentials["username"]
        assert user.email == test_user_credentials["email"]
        assert user.full_name == test_user_credentials["full_name"]
        assert user.is_active is True

    def test_register_duplicate_username_fails(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test registering with existing username fails."""
        with pytest.raises((ValidationError, AuthenticationError, APIError)):
            client.auth.register(
                username=registered_user["username"],  # Duplicate
                email=f"different_{unique_id}@example.com",
                password="AnotherPass123!",
                full_name="Another User",
            )

    def test_register_duplicate_email_fails(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test registering with existing email fails."""
        with pytest.raises((ValidationError, AuthenticationError, APIError)):
            client.auth.register(
                username=f"different_{unique_id}",
                email=registered_user["email"],  # Duplicate
                password="AnotherPass123!",
                full_name="Another User",
            )

    def test_register_weak_password_fails(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test registering with weak password fails."""
        with pytest.raises(ValidationError):
            client.auth.register(
                username=f"weakpass_{unique_id}",
                email=f"weak_{unique_id}@example.com",
                password="short",  # Too short, no digit
                full_name="Weak User",
            )


class TestLogin:
    """Tests for user login."""

    def test_login_success(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test successful login returns User and stores tokens."""
        user = client.auth.login(
            username=registered_user["username"],
            password=registered_user["password"],
        )

        assert isinstance(user, User)
        assert user.username == registered_user["username"]
        assert client.is_authenticated is True
        assert client.get_tokens() is not None

    def test_login_with_email(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test login with email instead of username."""
        user = client.auth.login(
            username=registered_user["email"],  # Use email as username
            password=registered_user["password"],
        )

        assert isinstance(user, User)
        assert user.email == registered_user["email"]

    def test_login_wrong_password_fails(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test login with wrong password fails."""
        with pytest.raises(AuthenticationError):
            client.auth.login(
                username=registered_user["username"],
                password="WrongPassword123!",
            )

    def test_login_nonexistent_user_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test login with nonexistent user fails."""
        with pytest.raises(AuthenticationError):
            client.auth.login(
                username="nonexistent_user_xyz",
                password="SomePassword123!",
            )


class TestLogout:
    """Tests for user logout."""

    def test_logout_success(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test logout clears tokens."""
        assert authenticated_client.is_authenticated is True

        authenticated_client.auth.logout()

        assert authenticated_client.is_authenticated is False
        assert authenticated_client.get_tokens() is None

    def test_logout_without_auth_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test logout without being authenticated fails."""
        with pytest.raises(AuthenticationError):
            client.auth.logout()


class TestMe:
    """Tests for getting current user."""

    def test_me_returns_current_user(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test me() returns the authenticated user."""
        user = authenticated_client.auth.me()

        assert isinstance(user, User)
        assert user.username == registered_user["username"]
        assert user.email == registered_user["email"]
        assert user.full_name == registered_user["full_name"]

    def test_me_without_auth_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test me() without authentication fails."""
        with pytest.raises(AuthenticationError):
            client.auth.me()


class TestTokenRefresh:
    """Tests for token refresh."""

    def test_manual_refresh(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test manual token refresh works."""
        old_tokens = authenticated_client.get_tokens()
        assert old_tokens is not None

        authenticated_client.auth.refresh()

        new_tokens = authenticated_client.get_tokens()
        assert new_tokens is not None
        # Access token should be different after refresh
        # (Refresh token might stay the same depending on backend implementation)
        assert authenticated_client.is_authenticated is True

    def test_refresh_without_tokens_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test refresh without tokens fails."""
        with pytest.raises(AuthenticationError):
            client.auth.refresh()


class TestChangePassword:
    """Tests for password change."""

    def test_change_password_success(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        backend_url: str,
    ) -> None:
        """Test changing password works."""
        new_password = "NewSecurePass789!"

        authenticated_client.auth.change_password(
            current_password=registered_user["password"],
            new_password=new_password,
        )

        # Verify can login with new password
        with SyftHubClient(base_url=backend_url) as new_client:
            user = new_client.auth.login(
                username=registered_user["username"],
                password=new_password,
            )
            assert user.username == registered_user["username"]

    def test_change_password_wrong_current_fails(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test changing password with wrong current password fails."""
        with pytest.raises((AuthenticationError, APIError)):
            authenticated_client.auth.change_password(
                current_password="WrongCurrentPass123!",
                new_password="NewPass123!",
            )

    def test_change_password_weak_new_fails(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test changing to weak password fails."""
        with pytest.raises(ValidationError):
            authenticated_client.auth.change_password(
                current_password=registered_user["password"],
                new_password="weak",  # Too short
            )


class TestTokenPersistence:
    """Tests for token persistence."""

    def test_set_tokens_restores_session(
        self,
        authenticated_client: SyftHubClient,
        backend_url: str,
    ) -> None:
        """Test that saved tokens can restore a session."""
        # Get tokens from authenticated client
        tokens = authenticated_client.get_tokens()
        assert tokens is not None

        # Create new client and set tokens
        with SyftHubClient(base_url=backend_url) as new_client:
            new_client.set_tokens(tokens)

            # Should be able to access authenticated endpoint
            user = new_client.auth.me()
            assert user is not None
            assert new_client.is_authenticated is True
