"""Accounting resource for SyftHub SDK.

This module connects to an external accounting/billing service.
Credentials can be provided via environment variables or constructor parameters.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.exceptions import APIError, AuthenticationError, ConfigurationError
from syfthub_sdk.models import AccountingBalance, AccountingTransaction

# Environment variable names
ENV_ACCOUNTING_URL = "SYFTHUB_ACCOUNTING_URL"
ENV_ACCOUNTING_EMAIL = "SYFTHUB_ACCOUNTING_EMAIL"
ENV_ACCOUNTING_PASSWORD = "SYFTHUB_ACCOUNTING_PASSWORD"


class AccountingResource:
    """Handle accounting/billing operations with external service.

    Credentials are loaded from environment variables by default:
    - SYFTHUB_ACCOUNTING_URL: Base URL of the accounting service
    - SYFTHUB_ACCOUNTING_EMAIL: Email for authentication
    - SYFTHUB_ACCOUNTING_PASSWORD: Password for authentication

    Example usage:
        # Using environment variables (default)
        client = SyftHubClient()
        balance = client.accounting.balance()
        print(f"Credits: {balance.credits}")

        # Explicit credentials
        client = SyftHubClient(
            accounting_url="https://accounting.example.com",
            accounting_email="user@example.com",
            accounting_password="secret"
        )

        # List transactions
        for tx in client.accounting.transactions():
            print(f"{tx.created_at}: {tx.amount} - {tx.description}")
    """

    def __init__(
        self,
        url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize accounting resource.

        Args:
            url: Accounting service URL (or from SYFTHUB_ACCOUNTING_URL env)
            email: Auth email (or from SYFTHUB_ACCOUNTING_EMAIL env)
            password: Auth password (or from SYFTHUB_ACCOUNTING_PASSWORD env)
            timeout: Request timeout in seconds
        """
        # Load from env vars if not provided
        self._url = url or os.environ.get(ENV_ACCOUNTING_URL)
        self._email = email or os.environ.get(ENV_ACCOUNTING_EMAIL)
        self._password = password or os.environ.get(ENV_ACCOUNTING_PASSWORD)
        self._timeout = timeout

        # HTTP client and token (lazy initialized)
        self._client: httpx.Client | None = None
        self._token: str | None = None

    @property
    def is_configured(self) -> bool:
        """Check if accounting service is configured."""
        return bool(self._url and self._email and self._password)

    def _ensure_configured(self) -> None:
        """Ensure accounting is configured, raise if not."""
        if not self.is_configured:
            missing = []
            if not self._url:
                missing.append(ENV_ACCOUNTING_URL)
            if not self._email:
                missing.append(ENV_ACCOUNTING_EMAIL)
            if not self._password:
                missing.append(ENV_ACCOUNTING_PASSWORD)
            raise ConfigurationError(
                f"Accounting not configured. Missing: {', '.join(missing)}. "
                f"Set environment variables or pass credentials to SyftHubClient."
            )

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def _authenticate(self) -> None:
        """Authenticate with the accounting service."""
        self._ensure_configured()
        client = self._get_client()

        try:
            response = client.post(
                f"{self._url}/auth/login",
                json={"email": self._email, "password": self._password},
            )
            if response.status_code != 200:
                raise AuthenticationError(
                    f"Accounting authentication failed: {response.text}"
                )
            data = response.json()
            self._token = data.get("access_token") or data.get("token")
            if not self._token:
                raise AuthenticationError("No token in accounting auth response")
        except httpx.RequestError as e:
            raise APIError(f"Failed to connect to accounting service: {e}") from e

    def _ensure_authenticated(self) -> None:
        """Ensure we have a valid token."""
        if self._token is None:
            self._authenticate()

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make an authenticated request to the accounting service."""
        self._ensure_configured()
        self._ensure_authenticated()

        client = self._get_client()
        url = f"{self._url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            response = client.request(method, url, headers=headers, **kwargs)

            # Re-authenticate on 401
            if response.status_code == 401:
                self._authenticate()
                headers = {"Authorization": f"Bearer {self._token}"}
                response = client.request(method, url, headers=headers, **kwargs)

            if response.status_code >= 400:
                raise APIError(
                    f"Accounting API error: {response.text}",
                    status_code=response.status_code,
                )

            if response.status_code == 204:
                return {}

            return response.json()  # type: ignore[no-any-return]

        except httpx.RequestError as e:
            raise APIError(f"Accounting request failed: {e}") from e

    def balance(self) -> AccountingBalance:
        """Get the current account balance.

        Returns:
            AccountingBalance with credits and currency

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails
            APIError: On other errors
        """
        response = self._request("GET", "/balance")
        data = response if isinstance(response, dict) else {}
        return AccountingBalance.model_validate(data)

    def transactions(
        self, *, page_size: int = 20
    ) -> PageIterator[AccountingTransaction]:
        """List account transactions.

        Args:
            page_size: Number of items per page (default 20)

        Returns:
            PageIterator that lazily fetches transactions

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails
        """

        def fetch_fn(skip: int, limit: int) -> list[dict[str, Any]]:
            response = self._request(
                "GET",
                "/transactions",
                params={"skip": skip, "limit": limit},
            )
            return response if isinstance(response, list) else []

        return PageIterator(fetch_fn, AccountingTransaction, page_size=page_size)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._token = None
