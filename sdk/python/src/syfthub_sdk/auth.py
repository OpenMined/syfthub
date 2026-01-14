"""Authentication resource for SyftHub SDK."""

from __future__ import annotations

import concurrent.futures
from typing import TYPE_CHECKING

from syfthub_sdk.models import AuthTokens, SatelliteTokenResponse, User

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

        If an accounting service URL is configured (via `accounting_service_url` or
        server default), the backend handles accounting integration using a
        "try-create-first" approach:

        **Accounting Password Behavior:**
        - **Not provided**: A secure password is auto-generated and a new
          accounting account is created.
        - **Provided (new user)**: The account is created with your chosen password.
        - **Provided (existing user)**: Your password is validated and accounts
          are linked.

        This means you can set your own accounting password during registration
        even if you're a new user - you don't need an existing accounting account.

        Args:
            username: Unique username (3-50 chars)
            email: Valid email address
            password: Password (min 8 chars, must contain letter and digit)
            full_name: User's full name
            accounting_service_url: Optional URL to external accounting service
            accounting_password: Optional password for accounting service. Can be:
                - A new password to create an account with (for new users)
                - An existing password to validate (for existing users)
                - None to auto-generate a password (for new users)

        Returns:
            The created User

        Raises:
            ValidationError: If registration data is invalid
            UserAlreadyExistsError: If username or email already exists in SyftHub
            AccountingAccountExistsError: If email exists in accounting service
                and no accounting_password was provided
            InvalidAccountingPasswordError: If the provided accounting password
                doesn't match an existing accounting account
            AccountingServiceUnavailableError: If the accounting service is unreachable

        Example:
            # Basic registration (auto-generated accounting password)
            user = client.auth.register(
                username="alice",
                email="alice@example.com",
                password="SecurePass123!",
                full_name="Alice",
            )

            # Registration with custom accounting password (NEW user)
            user = client.auth.register(
                username="bob",
                email="bob@example.com",
                password="SecurePass123!",
                full_name="Bob",
                accounting_password="MyChosenAccountingPass!",
            )

            # Handle existing accounting account
            try:
                user = client.auth.register(...)
            except AccountingAccountExistsError:
                # Prompt user for their existing accounting password
                accounting_password = input("Enter your existing accounting password: ")
                user = client.auth.register(..., accounting_password=accounting_password)
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

    def get_satellite_token(self, audience: str) -> SatelliteTokenResponse:
        """Get a satellite token for a specific audience (target service).

        Satellite tokens are short-lived, RS256-signed JWTs that allow satellite
        services (like SyftAI-Space) to verify user identity without calling
        SyftHub for every request.

        Args:
            audience: Target service identifier (username of the service owner)

        Returns:
            SatelliteTokenResponse with token and expiry

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If audience is invalid or inactive

        Example:
            # Get a token for querying alice's SyftAI-Space endpoints
            token_response = client.auth.get_satellite_token("alice")
            print(f"Token expires in {token_response.expires_in} seconds")
        """
        response = self._http.get("/api/v1/token", params={"aud": audience})
        data = response if isinstance(response, dict) else {}
        return SatelliteTokenResponse.model_validate(data)

    def get_satellite_tokens(self, audiences: list[str]) -> dict[str, str]:
        """Get satellite tokens for multiple audiences in parallel.

        This is useful when making requests to endpoints owned by different users.
        Tokens are cached and reused where possible.

        Args:
            audiences: List of audience identifiers (usernames)

        Returns:
            Dict mapping audience to satellite token

        Raises:
            AuthenticationError: If not authenticated

        Example:
            # Get tokens for multiple endpoint owners
            tokens = client.auth.get_satellite_tokens(["alice", "bob"])
            print(f"Got {len(tokens)} tokens")
        """
        unique_audiences = list(set(audiences))
        token_map: dict[str, str] = {}

        if not unique_audiences:
            return token_map

        def fetch_token(aud: str) -> tuple[str, str | None]:
            """Fetch a single token, returning None on failure."""
            try:
                response = self.get_satellite_token(aud)
                return (aud, response.target_token)
            except Exception:
                # Failed tokens are silently skipped - the aggregator will handle missing tokens
                return (aud, None)

        # Fetch tokens in parallel using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(unique_audiences), 10)) as executor:
            results = list(executor.map(fetch_token, unique_audiences))

        # Collect successful results
        for aud, token in results:
            if token is not None:
                token_map[aud] = token

        return token_map
