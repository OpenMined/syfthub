"""Authentication resource for SyftHub SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

from syfthub_sdk.models import AuthTokens, User

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class AuthResource:
    """Handle authentication operations.

    Example usage:
        # Register a new user
        user = client.auth.register(
            username="john",
            email="john@example.com",
            password="secret123",
            full_name="John Doe"
        )

        # Login
        user = client.auth.login(username="john", password="secret123")

        # Get current user
        me = client.auth.me()

        # Change password
        client.auth.change_password(
            current_password="secret123",
            new_password="newsecret456"
        )

        # Logout
        client.auth.logout()
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize auth resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def register(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str,
        accounting_service_url: str | None = None,
        accounting_password: str | None = None,
    ) -> User:
        """Register a new user.

        Args:
            username: Unique username (3-50 chars)
            email: Valid email address
            password: Password (min 8 chars, must contain letter and digit)
            full_name: User's full name
            accounting_service_url: Optional URL to external accounting service
            accounting_password: Optional password for accounting service

        Returns:
            The created User

        Raises:
            ValidationError: If registration data is invalid
            APIError: If registration fails
        """
        payload: dict[str, str | None] = {
            "username": username,
            "email": email,
            "password": password,
            "full_name": full_name,
        }
        # Only include accounting fields if provided
        if accounting_service_url is not None:
            payload["accounting_service_url"] = accounting_service_url
        if accounting_password is not None:
            payload["accounting_password"] = accounting_password

        response = self._http.post(
            "/api/v1/auth/register",
            json=payload,
            include_auth=False,
        )
        # Response contains user and tokens
        data = response if isinstance(response, dict) else {}
        return User.model_validate(data.get("user", data))

    def login(self, *, username: str, password: str) -> User:
        """Login with username and password.

        Args:
            username: Username or email
            password: User's password

        Returns:
            The authenticated User

        Raises:
            AuthenticationError: If credentials are invalid
        """
        # OAuth2 password flow uses form data
        response = self._http.post(
            "/api/v1/auth/login",
            data={
                "username": username,
                "password": password,
            },
            include_auth=False,
        )

        data = response if isinstance(response, dict) else {}

        # Store tokens
        tokens = AuthTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "bearer"),
        )
        self._http.set_tokens(tokens)

        # Fetch and return user info
        return self.me()

    def logout(self) -> None:
        """Logout and invalidate tokens.

        Raises:
            AuthenticationError: If not authenticated
        """
        self._http.post("/api/v1/auth/logout")
        self._http.clear_tokens()

    def refresh(self) -> None:
        """Manually refresh the access token.

        This is usually handled automatically on 401 responses,
        but can be called explicitly if needed.

        Raises:
            AuthenticationError: If refresh token is invalid/expired
        """
        tokens = self._http.get_tokens()
        if not tokens:
            from syfthub_sdk.exceptions import AuthenticationError

            raise AuthenticationError("No tokens available to refresh")

        response = self._http.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens.refresh_token},
            include_auth=False,
        )

        data = response if isinstance(response, dict) else {}

        # Update stored tokens
        new_tokens = AuthTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "bearer"),
        )
        self._http.set_tokens(new_tokens)

    def me(self) -> User:
        """Get the current authenticated user.

        Returns:
            The current User

        Raises:
            AuthenticationError: If not authenticated
        """
        response = self._http.get("/api/v1/auth/me")
        data = response if isinstance(response, dict) else {}
        return User.model_validate(data)

    def change_password(
        self,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        """Change the current user's password.

        Args:
            current_password: The current password
            new_password: The new password (min 8 chars)

        Raises:
            AuthenticationError: If current password is wrong
            ValidationError: If new password doesn't meet requirements
        """
        self._http.put(
            "/api/v1/auth/me/password",
            json={
                "current_password": current_password,
                "new_password": new_password,
            },
        )
