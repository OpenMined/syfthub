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
from syfthub_sdk.chat import ChatResource
from syfthub_sdk.exceptions import ConfigurationError
from syfthub_sdk.hub import HubResource
from syfthub_sdk.models import AuthTokens, User
from syfthub_sdk.my_endpoints import MyEndpointsResource
from syfthub_sdk.syftai import SyftAIResource
from syfthub_sdk.users import UsersResource

# Environment variable for SyftHub URL
ENV_SYFTHUB_URL = "SYFTHUB_URL"
ENV_AGGREGATOR_URL = "SYFTHUB_AGGREGATOR_URL"


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

        # Accounting (auto-retrieved from backend after login)
        user = client.accounting.get_user()

        # Context manager for cleanup
        with SyftHubClient() as client:
            client.auth.login(...)
            ...

        # Token persistence
        tokens = client.get_tokens()
        # ... save tokens to file/db ...
        # Later:
        client.set_tokens(tokens)

        # Chat with RAG via aggregator
        response = client.chat.complete(
            prompt="What is machine learning?",
            model="alice/gpt-model",
            data_sources=["bob/ml-docs"],
        )

        # Direct SyftAI-Space queries
        docs = client.syftai.query_data_source(endpoint_ref, query, user_email)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
        # Aggregator URL (optional)
        aggregator_url: str | None = None,
    ) -> None:
        """Initialize the SyftHub client.

        Args:
            base_url: SyftHub API URL (or from SYFTHUB_URL env var)
            timeout: Request timeout in seconds (default 30)
            aggregator_url: Aggregator service URL (optional, defaults to
                {base_url}/aggregator/api/v1 or from SYFTHUB_AGGREGATOR_URL env var)

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

        # Resolve aggregator URL (default to {base_url}/aggregator/api/v1)
        self._aggregator_url = (
            aggregator_url
            or os.environ.get(ENV_AGGREGATOR_URL)
            or f"{self._base_url.rstrip('/')}/aggregator/api/v1"
        )

        # Store timeout for lazy-initialized resources
        self._timeout = timeout

        # Create HTTP client
        self._http = HTTPClient(base_url=self._base_url, timeout=timeout)

        # Create resource instances
        self._auth = AuthResource(self._http)
        self._users = UsersResource(self._http)
        self._my_endpoints = MyEndpointsResource(self._http)
        self._hub = HubResource(self._http)

        # Lazy-initialized resources
        self._chat: ChatResource | None = None
        self._syftai: SyftAIResource | None = None
        self._accounting: AccountingResource | None = None

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
        """Accounting/billing operations (balance, transactions).

        Credentials are automatically retrieved from the backend after login.
        You must be authenticated to use accounting.

        Raises:
            AuthenticationError: If not logged in
            ConfigurationError: If user has no accounting service configured
        """
        if self._accounting is None:
            self._accounting = self._init_accounting()
        return self._accounting

    def _init_accounting(self) -> AccountingResource:
        """Initialize accounting resource by fetching credentials from backend.

        Returns:
            Configured AccountingResource

        Raises:
            AuthenticationError: If not authenticated
            ConfigurationError: If user has no accounting configured in backend
        """
        from syfthub_sdk.exceptions import AuthenticationError

        if not self.is_authenticated:
            raise AuthenticationError(
                "Must be logged in to use accounting. Call client.auth.login() first."
            )

        # Fetch credentials from backend
        creds = self.users.get_accounting_credentials()

        if not creds.url:
            raise ConfigurationError(
                "No accounting service configured for this user. "
                "Contact your administrator to set up accounting."
            )

        if not creds.password:
            raise ConfigurationError(
                "Accounting password not available. "
                "This may indicate an issue with your account setup."
            )

        return AccountingResource(
            url=creds.url,
            email=creds.email,
            password=creds.password,
            timeout=self._timeout,
        )

    @property
    def chat(self) -> ChatResource:
        """Chat operations via the Aggregator (RAG-augmented conversations).

        This resource provides high-level chat functionality that integrates
        with the SyftHub Aggregator service for RAG workflows.

        Example:
            # Simple chat completion
            response = client.chat.complete(
                prompt="What is machine learning?",
                model="alice/gpt-model",
                data_sources=["bob/ml-docs"],
            )
            print(response.response)

            # Streaming chat
            for event in client.chat.stream(prompt="...", model="..."):
                if event.type == "token":
                    print(event.content, end="")

            # Get available endpoints
            models = list(client.chat.get_available_models())
            sources = list(client.chat.get_available_data_sources())
        """
        if self._chat is None:
            self._chat = ChatResource(
                hub=self._hub,
                auth=self._auth,
                aggregator_url=self._aggregator_url,
            )
        return self._chat

    @property
    def syftai(self) -> SyftAIResource:
        """Direct SyftAI-Space endpoint queries (low-level API).

        This resource provides direct access to SyftAI-Space endpoints without
        going through the aggregator. Use this when you need custom RAG pipelines
        or fine-grained control over queries.

        For most use cases, prefer the higher-level `client.chat` API instead.

        Example:
            # Query a data source directly
            docs = client.syftai.query_data_source(
                endpoint=EndpointRef(url="http://syftai:8080", slug="docs"),
                query="What is Python?",
                user_email="alice@example.com",
            )

            # Query a model directly
            response = client.syftai.query_model(
                endpoint=model_ref,
                messages=[Message(role="user", content="Hello!")],
                user_email="alice@example.com",
            )
        """
        if self._syftai is None:
            self._syftai = SyftAIResource(http=self._http)
        return self._syftai

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
        if self._accounting is not None:
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
