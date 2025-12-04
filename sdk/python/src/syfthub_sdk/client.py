"""Main SyftHub client."""

from __future__ import annotations

import os
import sys
from types import TracebackType

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from syfthub_sdk._http import HTTPClient
from syfthub_sdk.accounting import AccountingResource
from syfthub_sdk.auth import AuthResource
from syfthub_sdk.exceptions import ConfigurationError
from syfthub_sdk.hub import HubResource
from syfthub_sdk.models import AuthTokens, User
from syfthub_sdk.my_endpoints import MyEndpointsResource
from syfthub_sdk.users import UsersResource

# Environment variable for SyftHub URL
ENV_SYFTHUB_URL = "SYFTHUB_URL"


class SyftHubClient:
    """Main client for interacting with SyftHub API.

    Example usage:
        # Initialize with environment variable
        # (set SYFTHUB_URL=https://hub.syft.com)
        client = SyftHubClient()

        # Or with explicit URL
        client = SyftHubClient(base_url="https://hub.syft.com")

        # Login
        client.auth.login(username="john", password="secret123")

        # Use resources
        for endpoint in client.my_endpoints.list():
            print(endpoint.name)

        for public_ep in client.hub.browse():
            print(public_ep.path)

        # With accounting (credentials from env or explicit)
        balance = client.accounting.balance()

        # Context manager for cleanup
        with SyftHubClient() as client:
            client.auth.login(...)
            ...

        # Token persistence
        tokens = client.get_tokens()
        # ... save tokens to file/db ...
        # Later:
        client.set_tokens(tokens)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
        # Accounting credentials (optional)
        accounting_url: str | None = None,
        accounting_email: str | None = None,
        accounting_password: str | None = None,
    ) -> None:
        """Initialize the SyftHub client.

        Args:
            base_url: SyftHub API URL (or from SYFTHUB_URL env var)
            timeout: Request timeout in seconds (default 30)
            accounting_url: Accounting service URL (or from env)
            accounting_email: Accounting auth email (or from env)
            accounting_password: Accounting auth password (or from env)

        Raises:
            ConfigurationError: If base_url is not provided and
                SYFTHUB_URL env var is not set
        """
        # Resolve base URL
        self._base_url = base_url or os.environ.get(ENV_SYFTHUB_URL)
        if not self._base_url:
            raise ConfigurationError(
                f"SyftHub URL not configured. Either pass base_url parameter "
                f"or set {ENV_SYFTHUB_URL} environment variable."
            )

        # Create HTTP client
        self._http = HTTPClient(base_url=self._base_url, timeout=timeout)

        # Create resource instances
        self._auth = AuthResource(self._http)
        self._users = UsersResource(self._http)
        self._my_endpoints = MyEndpointsResource(self._http)
        self._hub = HubResource(self._http)

        # Create accounting resource (with optional explicit credentials)
        self._accounting = AccountingResource(
            url=accounting_url,
            email=accounting_email,
            password=accounting_password,
            timeout=timeout,
        )

    @property
    def auth(self) -> AuthResource:
        """Authentication operations (login, register, logout, etc.)."""
        return self._auth

    @property
    def users(self) -> UsersResource:
        """User profile operations (update, check availability)."""
        return self._users

    @property
    def my_endpoints(self) -> MyEndpointsResource:
        """Manage your own endpoints (create, update, delete, list)."""
        return self._my_endpoints

    @property
    def hub(self) -> HubResource:
        """Browse and discover public endpoints from others."""
        return self._hub

    @property
    def accounting(self) -> AccountingResource:
        """Accounting/billing operations (balance, transactions)."""
        return self._accounting

    @property
    def is_authenticated(self) -> bool:
        """Check if the client has authentication tokens."""
        return self._http.is_authenticated

    def get_tokens(self) -> AuthTokens | None:
        """Get current authentication tokens for persistence.

        Returns:
            AuthTokens if authenticated, None otherwise
        """
        return self._http.get_tokens()

    def set_tokens(self, tokens: AuthTokens) -> None:
        """Set authentication tokens (e.g., from saved session).

        Args:
            tokens: AuthTokens with access_token and refresh_token
        """
        self._http.set_tokens(tokens)

    def close(self) -> None:
        """Close the client and release resources."""
        self._http.close()
        self._accounting.close()

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager and cleanup."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        auth_status = "authenticated" if self.is_authenticated else "not authenticated"
        return f"SyftHubClient(base_url={self._base_url!r}, {auth_status})"

    # -------------------------------------------------------------------------
    # Auth method aliases for convenience
    # -------------------------------------------------------------------------

    def register(
        self,
        *,
        username: str,
        email: str,
        password: str,
        full_name: str,
    ) -> User:
        """Register a new user. Alias for client.auth.register()."""
        return self._auth.register(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
        )

    def login(self, *, username: str, password: str) -> User:
        """Login with username and password. Alias for client.auth.login()."""
        return self._auth.login(username=username, password=password)

    def logout(self) -> None:
        """Logout and invalidate tokens. Alias for client.auth.logout()."""
        self._auth.logout()

    def me(self) -> User:
        """Get the current authenticated user. Alias for client.auth.me()."""
        return self._auth.me()

    def refresh(self) -> None:
        """Manually refresh the access token. Alias for client.auth.refresh()."""
        self._auth.refresh()

    def change_password(self, *, current_password: str, new_password: str) -> None:
        """Change the current user's password. Alias for client.auth.change_password()."""
        self._auth.change_password(
            current_password=current_password,
            new_password=new_password,
        )
