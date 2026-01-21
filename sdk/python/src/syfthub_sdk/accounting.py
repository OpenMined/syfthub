"""Accounting resource for SyftHub SDK.

This module connects to an external accounting/billing service for managing
user balances and transactions. The accounting service is separate from SyftHub
and uses its own authentication (Basic auth with email/password).

Credentials are automatically retrieved from the backend after login.

Example usage:
    from syfthub_sdk import SyftHubClient

    # Login first
    client = SyftHubClient()
    client.auth.login(username="user@example.com", password="password")

    # Accounting credentials are auto-retrieved from backend
    user = client.accounting.get_user()
    print(f"Balance: {user.balance}")

    # Create a transaction
    tx = client.accounting.create_transaction(
        recipient_email="recipient@example.com",
        amount=10.0,
        app_name="syftai-space",
        app_ep_path="alice/my-model"
    )
    print(f"Transaction {tx.id} created: {tx.status}")

    # Confirm the transaction
    tx = client.accounting.confirm_transaction(tx.id)
    print(f"Transaction confirmed: {tx.status}")
"""

from __future__ import annotations

from typing import Any

import httpx

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from syfthub_sdk.models import AccountingUser, Transaction


def _handle_response_error(response: httpx.Response) -> None:
    """Handle HTTP error responses from accounting service.

    Args:
        response: The HTTP response to check

    Raises:
        AuthenticationError: For 401 responses
        AuthorizationError: For 403 responses
        NotFoundError: For 404 responses
        ValidationError: For 422 responses
        APIError: For other error responses
    """
    if response.status_code < 400:
        return

    # Try to extract error detail from response
    try:
        body = response.json()
        detail = body.get("detail", body.get("message", str(body)))
    except Exception:
        detail = response.text or f"HTTP {response.status_code}"

    if response.status_code == 401:
        raise AuthenticationError(f"Authentication failed: {detail}")
    elif response.status_code == 403:
        raise AuthorizationError(f"Permission denied: {detail}")
    elif response.status_code == 404:
        raise NotFoundError(f"Not found: {detail}")
    elif response.status_code == 422:
        raise ValidationError(f"Validation error: {detail}")
    else:
        raise APIError(
            f"Accounting API error: {detail}",
            status_code=response.status_code,
        )


class AccountingResource:
    """Handle accounting/billing operations with external service.

    The accounting service manages user balances and transactions. It uses
    Basic auth (email/password) for authentication, which is separate from
    SyftHub's JWT-based authentication.

    Credentials are automatically retrieved from the backend after login.
    Users don't need to configure accounting credentials manually.

    Transaction Workflow:
    1. Sender creates transaction (status=PENDING)
    2. Either party confirms (status=COMPLETED) or cancels (status=CANCELLED)

    Delegated Transaction Workflow:
    1. Sender creates a transaction token for recipient
    2. Recipient uses token to create delegated transaction
    3. Recipient confirms the transaction
    """

    def __init__(
        self,
        url: str,
        email: str,
        password: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize accounting resource.

        Note: This class is typically instantiated internally by SyftHubClient
        after fetching credentials from the backend. Users don't need to
        create this directly.

        Args:
            url: Accounting service URL
            email: Auth email
            password: Auth password
            timeout: Request timeout in seconds
        """
        self._url = url
        self._email = email
        self._password = password
        self._timeout = timeout

        # HTTP client (lazy initialized)
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client with Basic auth."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self._url,
                auth=(self._email, self._password),
                timeout=self._timeout,
            )
        return self._client

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make an authenticated request to the accounting service.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            path: API path (e.g., "/user", "/transactions")
            json: JSON body for POST/PUT requests
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails
            APIError: On other errors
        """
        client = self._get_client()

        try:
            response = client.request(method, path, json=json, params=params)
            _handle_response_error(response)

            if response.status_code == 204:
                return {}

            return response.json()  # type: ignore[no-any-return]

        except httpx.RequestError as e:
            raise APIError(f"Accounting request failed: {e}") from e

    def _request_with_token(
        self,
        method: str,
        path: str,
        token: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make a request using Bearer token auth (for delegated transactions).

        Args:
            method: HTTP method
            path: API path
            token: Bearer token for authentication
            json: JSON body

        Returns:
            Parsed JSON response
        """
        try:
            # Create a separate client without Basic auth
            with httpx.Client(
                base_url=self._url,
                timeout=self._timeout,
            ) as client:
                response = client.request(
                    method,
                    path,
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
                _handle_response_error(response)

                if response.status_code == 204:
                    return {}

                return response.json()  # type: ignore[no-any-return]

        except httpx.RequestError as e:
            raise APIError(f"Accounting request failed: {e}") from e

    # =========================================================================
    # User Operations
    # =========================================================================

    def get_user(self) -> AccountingUser:
        """Get the current user's account information including balance.

        Returns:
            AccountingUser with id, email, balance, and organization

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            user = client.accounting.get_user()
            print(f"Balance: {user.balance}")
            print(f"Organization: {user.organization}")
        """
        response = self._request("GET", "/user")
        data = response if isinstance(response, dict) else {}
        return AccountingUser.model_validate(data)

    def update_password(
        self,
        current_password: str,
        new_password: str,
    ) -> None:
        """Update the user's password.

        Args:
            current_password: Current password for verification
            new_password: New password to set

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If current password is wrong
            ValidationError: If new password doesn't meet requirements
            APIError: On other errors

        Example:
            client.accounting.update_password(
                current_password="old_secret",
                new_password="new_secret"
            )
        """
        self._request(
            "PUT",
            "/user/password",
            json={
                "oldPassword": current_password,
                "newPassword": new_password,
            },
        )

    def update_organization(self, organization: str) -> None:
        """Update the user's organization.

        Args:
            organization: New organization name

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            client.accounting.update_organization("OpenMined")
        """
        self._request(
            "PUT",
            "/user/organization",
            json={"organization": organization},
        )

    # =========================================================================
    # Transaction Listing
    # =========================================================================

    def get_transactions(
        self,
        *,
        page_size: int = 20,
    ) -> PageIterator[Transaction]:
        """List account transactions with pagination.

        Returns a lazy iterator that fetches pages on demand.

        Args:
            page_size: Number of items per page (default 20)

        Returns:
            PageIterator that yields Transaction objects

        Raises:
            ConfigurationError: If accounting is not configured
            AuthenticationError: If authentication fails

        Example:
            # Iterate through all transactions
            for tx in client.accounting.get_transactions():
                print(f"{tx.created_at}: {tx.amount} from {tx.sender_email}")

            # Get first page only
            first_page = client.accounting.get_transactions().first_page()

            # Get all transactions
            all_txs = client.accounting.get_transactions().all()
        """

        def fetch_fn(skip: int, limit: int) -> list[dict[str, Any]]:
            response = self._request(
                "GET",
                "/transactions",
                params={"skip": skip, "limit": limit},
            )
            return response if isinstance(response, list) else []

        return PageIterator(fetch_fn, Transaction, page_size=page_size)

    def get_transaction(self, transaction_id: str) -> Transaction:
        """Get a specific transaction by ID.

        Args:
            transaction_id: The transaction ID

        Returns:
            Transaction object

        Raises:
            NotFoundError: If transaction not found
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            tx = client.accounting.get_transaction("tx_123")
            print(f"Status: {tx.status}")
        """
        response = self._request("GET", f"/transactions/{transaction_id}")
        data = response if isinstance(response, dict) else {}
        return Transaction.model_validate(data)

    # =========================================================================
    # Direct Transaction Operations
    # =========================================================================

    def create_transaction(
        self,
        recipient_email: str,
        amount: float,
        app_name: str | None = None,
        app_ep_path: str | None = None,
    ) -> Transaction:
        """Create a new transaction (direct transfer).

        Creates a PENDING transaction that must be confirmed or cancelled.
        The transaction is created by the sender (current user).

        Args:
            recipient_email: Email of the recipient
            amount: Amount to transfer (must be > 0)
            app_name: Optional app name for context (e.g., "syftai-space")
            app_ep_path: Optional endpoint path for context (e.g., "alice/model")

        Returns:
            Transaction in PENDING status

        Raises:
            ValidationError: If amount <= 0 or insufficient balance
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            tx = client.accounting.create_transaction(
                recipient_email="bob@example.com",
                amount=10.0,
                app_name="syftai-space",
                app_ep_path="alice/my-model"
            )
            print(f"Created transaction {tx.id}: {tx.status}")

            # Later, confirm or cancel
            tx = client.accounting.confirm_transaction(tx.id)
        """
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        payload: dict[str, Any] = {
            "recipientEmail": recipient_email,
            "amount": amount,
        }
        if app_name:
            payload["appName"] = app_name
        if app_ep_path:
            payload["appEpPath"] = app_ep_path

        response = self._request("POST", "/transactions", json=payload)
        data = response if isinstance(response, dict) else {}
        return Transaction.model_validate(data)

    def confirm_transaction(self, transaction_id: str) -> Transaction:
        """Confirm a pending transaction.

        Confirms the transaction, transferring funds from sender to recipient.
        Can be called by either the sender or recipient.

        Args:
            transaction_id: The transaction ID to confirm

        Returns:
            Transaction in COMPLETED status

        Raises:
            NotFoundError: If transaction not found
            ValidationError: If transaction is not in PENDING status
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            tx = client.accounting.confirm_transaction("tx_123")
            print(f"Confirmed: {tx.status}")  # "completed"
        """
        response = self._request("POST", f"/transactions/{transaction_id}/confirm")
        data = response if isinstance(response, dict) else {}
        return Transaction.model_validate(data)

    def cancel_transaction(self, transaction_id: str) -> Transaction:
        """Cancel a pending transaction.

        Cancels the transaction without transferring funds.
        Can be called by either the sender or recipient.

        Args:
            transaction_id: The transaction ID to cancel

        Returns:
            Transaction in CANCELLED status

        Raises:
            NotFoundError: If transaction not found
            ValidationError: If transaction is not in PENDING status
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            tx = client.accounting.cancel_transaction("tx_123")
            print(f"Cancelled: {tx.status}")  # "cancelled"
        """
        response = self._request("POST", f"/transactions/{transaction_id}/cancel")
        data = response if isinstance(response, dict) else {}
        return Transaction.model_validate(data)

    # =========================================================================
    # Delegated Transaction Operations
    # =========================================================================

    def create_transaction_token(self, recipient_email: str) -> str:
        """Create a transaction token for delegated transfers.

        Creates a JWT token that authorizes the recipient to create a
        transaction on behalf of the sender (current user). The token
        is short-lived (typically ~5 minutes).

        Use this when you want to pre-authorize a payment that will be
        initiated by the recipient (e.g., a service charging for usage).

        Args:
            recipient_email: Email of the authorized recipient

        Returns:
            JWT token string to share with recipient

        Raises:
            AuthenticationError: If authentication fails
            APIError: On other errors

        Example:
            # Sender creates token
            token = client.accounting.create_transaction_token("service@example.com")

            # Share token with recipient out-of-band
            # Recipient uses token to create delegated transaction
        """
        response = self._request(
            "POST",
            "/token/create",
            json={"recipientEmail": recipient_email},
        )
        data = response if isinstance(response, dict) else {}
        return str(data.get("token", ""))

    def create_delegated_transaction(
        self,
        sender_email: str,
        amount: float,
        token: str,
    ) -> Transaction:
        """Create a delegated transaction using a pre-authorized token.

        Creates a transaction on behalf of the sender using their token.
        This is typically used by services to charge users for usage.

        The token authenticates the request instead of Basic auth.

        Args:
            sender_email: Email of the sender who created the token
            amount: Amount to transfer (must be > 0)
            token: JWT token from sender's create_transaction_token()

        Returns:
            Transaction in PENDING status (created_by=RECIPIENT)

        Raises:
            AuthenticationError: If token is invalid or expired
            ValidationError: If amount <= 0
            APIError: On other errors

        Example:
            # Recipient creates transaction using sender's token
            tx = client.accounting.create_delegated_transaction(
                sender_email="alice@example.com",
                amount=5.0,
                token=alice_token
            )

            # Recipient confirms the transaction
            tx = client.accounting.confirm_transaction(tx.id)
        """
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        response = self._request_with_token(
            "POST",
            "/transactions",
            token,
            json={
                "senderEmail": sender_email,
                "amount": amount,
            },
        )
        data = response if isinstance(response, dict) else {}
        return Transaction.model_validate(data)

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None
