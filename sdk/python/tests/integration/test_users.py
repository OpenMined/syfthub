"""Integration tests for user profile management."""

from __future__ import annotations

import pytest

from syfthub_sdk import SyftHubClient, User
from syfthub_sdk.exceptions import AuthenticationError


class TestProfileUpdate:
    """Tests for updating user profile."""

    def test_update_full_name(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test updating full name."""
        new_name = "Updated Full Name"

        user = authenticated_client.users.update(full_name=new_name)

        assert isinstance(user, User)
        assert user.full_name == new_name

    def test_update_avatar_url(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test updating avatar URL."""
        avatar_url = "https://example.com/avatar.png"

        user = authenticated_client.users.update(avatar_url=avatar_url)

        assert isinstance(user, User)
        assert user.avatar_url == avatar_url

    def test_update_multiple_fields(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test updating multiple fields at once."""
        new_name = "New Name"
        avatar_url = "https://example.com/new-avatar.png"

        user = authenticated_client.users.update(
            full_name=new_name,
            avatar_url=avatar_url,
        )

        assert user.full_name == new_name
        assert user.avatar_url == avatar_url

    def test_update_without_auth_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test updating profile without authentication fails."""
        with pytest.raises(AuthenticationError):
            client.users.update(full_name="Should Fail")

    def test_update_persists(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test that updates persist across requests."""
        new_name = "Persisted Name"

        authenticated_client.users.update(full_name=new_name)

        # Fetch user again to verify persistence
        user = authenticated_client.auth.me()
        assert user.full_name == new_name


class TestUsernameAvailability:
    """Tests for checking username availability."""

    def test_available_username(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test checking an available username."""
        username = f"available_user_{unique_id}"

        is_available = client.users.check_username(username)

        assert is_available is True

    def test_taken_username(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test checking a taken username."""
        is_available = client.users.check_username(registered_user["username"])

        assert is_available is False

    def test_check_username_no_auth_required(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test that checking username doesn't require auth."""
        # Client is not authenticated
        assert client.is_authenticated is False

        # But this should still work
        is_available = client.users.check_username(f"noauth_check_{unique_id}")

        assert is_available is True


class TestEmailAvailability:
    """Tests for checking email availability."""

    def test_available_email(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test checking an available email."""
        email = f"available_{unique_id}@example.com"

        is_available = client.users.check_email(email)

        assert is_available is True

    def test_taken_email(
        self,
        client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test checking a taken email."""
        is_available = client.users.check_email(registered_user["email"])

        assert is_available is False

    def test_check_email_no_auth_required(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test that checking email doesn't require auth."""
        # Client is not authenticated
        assert client.is_authenticated is False

        # But this should still work
        is_available = client.users.check_email(f"noauth_{unique_id}@test.com")

        assert is_available is True
