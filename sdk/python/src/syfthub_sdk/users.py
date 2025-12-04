"""Users resource for SyftHub SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

from syfthub_sdk.models import User

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class UsersResource:
    """Handle user profile operations.

    Example usage:
        # Update profile
        user = client.users.update(
            full_name="John D.",
            avatar_url="https://example.com/avatar.png"
        )

        # Check username availability
        if client.users.check_username("newusername"):
            print("Username is available!")

        # Check email availability
        if client.users.check_email("new@example.com"):
            print("Email is available!")
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize users resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def update(
        self,
        *,
        username: str | None = None,
        email: str | None = None,
        full_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Update the current user's profile.

        Only provided fields will be updated.

        Args:
            username: New username (3-50 chars)
            email: New email address
            full_name: New full name (1-100 chars)
            avatar_url: New avatar URL (max 500 chars)

        Returns:
            Updated User

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If update data is invalid
        """
        # Build update payload with only provided fields
        payload: dict[str, str] = {}
        if username is not None:
            payload["username"] = username
        if email is not None:
            payload["email"] = email
        if full_name is not None:
            payload["full_name"] = full_name
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url

        response = self._http.put("/api/v1/users/me", json=payload)
        data = response if isinstance(response, dict) else {}
        return User.model_validate(data)

    def check_username(self, username: str) -> bool:
        """Check if a username is available.

        Args:
            username: Username to check

        Returns:
            True if username is available, False otherwise
        """
        response = self._http.get(
            f"/api/v1/users/check-username/{username}",
            include_auth=False,
        )
        data = response if isinstance(response, dict) else {}
        return bool(data.get("available", False))

    def check_email(self, email: str) -> bool:
        """Check if an email is available.

        Args:
            email: Email to check

        Returns:
            True if email is available, False otherwise
        """
        response = self._http.get(
            f"/api/v1/users/check-email/{email}",
            include_auth=False,
        )
        data = response if isinstance(response, dict) else {}
        return bool(data.get("available", False))
