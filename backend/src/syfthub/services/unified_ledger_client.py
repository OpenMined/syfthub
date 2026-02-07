"""HTTP client for Unified Global Ledger integration.

This module provides a client for communicating with the Unified Global Ledger
service for account management, balance queries, and transfer operations.

The Unified Global Ledger API:
- POST /v1/accounts - Create a new account
- GET /v1/accounts/:id - Get account details
- GET /v1/accounts/:id/balance - Get account balance
- POST /v1/transfers - Create a transfer (with optional confirmation flow)
- POST /v1/transfers/confirm - Confirm a pending transfer
- POST /v1/transfers/:id/cancel - Cancel a pending transfer

Authentication: Bearer token (API tokens with at_ prefix)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from syfthub.observability import get_correlation_id, get_logger
from syfthub.observability.constants import CORRELATION_ID_HEADER

logger = get_logger(__name__)


# =============================================================================
# Result Types
# =============================================================================


@dataclass(frozen=True)
class LedgerAccount:
    """Account data from the Unified Global Ledger."""

    id: str
    type: str
    status: str
    balance: str
    available_balance: str
    currency: str
    metadata: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass(frozen=True)
class LedgerBalance:
    """Balance data from the Unified Global Ledger."""

    account_id: str
    balance: str
    available_balance: str
    currency: str


@dataclass(frozen=True)
class LedgerTransfer:
    """Transfer data from the Unified Global Ledger."""

    id: str
    source_account_id: str
    destination_account_id: str
    amount: str
    currency: str
    status: str
    confirmation_token: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass(frozen=True)
class LedgerResult:
    """Result of a ledger operation.

    Attributes:
        success: Whether the operation succeeded
        data: Response data if successful (type varies by operation)
        error: Error message if the operation failed
        status_code: HTTP status code from the response
    """

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


# =============================================================================
# Idempotency Key Generation
# =============================================================================


def generate_idempotency_key() -> str:
    """Generate a unique idempotency key for mutations.

    Returns:
        A UUID v4 string for use as an Idempotency-Key header
    """
    return str(uuid.uuid4())


# =============================================================================
# Unified Ledger Client
# =============================================================================


class UnifiedLedgerClient:
    """HTTP client for Unified Global Ledger.

    This client handles communication with the Unified Global Ledger for:
    - Account creation and balance queries
    - P2P transfers with optional confirmation flow
    - Transfer confirmation/cancellation

    Example:
        client = UnifiedLedgerClient(
            base_url="https://ledger.example.com",
            api_token="at_abc12345_xxxxx"
        )

        # Get balance
        result = client.get_balance("acc_123")
        if result.success:
            print(f"Balance: {result.data.balance}")

        # Create transfer with confirmation token
        result = client.create_transfer(
            source_account_id="acc_123",
            destination_account_id="acc_456",
            amount="1000",
            require_confirmation=True
        )
        if result.success:
            print(f"Confirmation token: {result.data.confirmation_token}")
    """

    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0):
        """Initialize the Unified Ledger client.

        Args:
            base_url: Base URL of the ledger service (e.g., "https://ledger.example.com")
            api_token: API token for authentication (at_* format)
            timeout: Request timeout in seconds (default 30)
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client (lazy initialization)."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    def _get_headers(self, idempotency_key: Optional[str] = None) -> dict[str, str]:
        """Get headers for API requests.

        Args:
            idempotency_key: Optional idempotency key for mutations

        Returns:
            Headers dict with authorization and optional idempotency key
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}",
        }

        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        correlation_id = get_correlation_id()
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id

        return headers

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> UnifiedLedgerClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit - close client."""
        self.close()

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract error detail from response.

        Handles RFC 9457 Problem Details format.

        Args:
            response: HTTP response object

        Returns:
            Error message string
        """
        try:
            data = response.json()
            if isinstance(data, dict):
                # RFC 9457 Problem Details
                return (
                    data.get("detail")
                    or data.get("title")
                    or data.get("message")
                    or data.get("error")
                    or str(data)
                )
            return str(data)
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    # =========================================================================
    # Account Operations
    # =========================================================================

    def create_account(
        self,
        account_type: str = "user",
        metadata: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> LedgerResult:
        """Create a new account in the ledger.

        Args:
            account_type: Account type (default "user")
            metadata: Optional metadata for the account
            idempotency_key: Idempotency key (auto-generated if not provided)

        Returns:
            LedgerResult with LedgerAccount data if successful
        """
        if idempotency_key is None:
            idempotency_key = generate_idempotency_key()

        payload: dict[str, Any] = {"type": account_type}
        if metadata:
            payload["metadata"] = metadata

        try:
            logger.debug("ledger.account.create.started", account_type=account_type)
            response = self.client.post(
                "/v1/accounts",
                json=payload,
                headers=self._get_headers(idempotency_key),
            )

            if response.status_code == 201:
                data = response.json()
                account = LedgerAccount(
                    id=data.get("id", ""),
                    type=data.get("type", ""),
                    status=data.get("status", ""),
                    balance=data.get("balance", "0"),
                    available_balance=data.get("available_balance", "0"),
                    currency=data.get("currency", "CREDIT"),
                    metadata=data.get("metadata"),
                    created_at=data.get("created_at"),
                    updated_at=data.get("updated_at"),
                )
                logger.info("ledger.account.create.success", account_id=account.id)
                return LedgerResult(success=True, data=account, status_code=201)

            error_detail = self._extract_error_detail(response)
            logger.warning(
                "ledger.account.create.failed",
                status_code=response.status_code,
                error=error_detail,
            )
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            logger.error("ledger.account.create.timeout")
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            logger.error("ledger.account.create.network_error", error=str(e))
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.account.create.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    def get_account(self, account_id: str) -> LedgerResult:
        """Get account details.

        Args:
            account_id: UUID of the account

        Returns:
            LedgerResult with LedgerAccount data if successful
        """
        try:
            logger.debug("ledger.account.get.started", account_id=account_id)
            response = self.client.get(
                f"/v1/accounts/{account_id}",
                headers=self._get_headers(),
            )

            if response.status_code == 200:
                data = response.json()
                account = LedgerAccount(
                    id=data.get("id", ""),
                    type=data.get("type", ""),
                    status=data.get("status", ""),
                    balance=data.get("balance", "0"),
                    available_balance=data.get("available_balance", "0"),
                    currency=data.get("currency", "CREDIT"),
                    metadata=data.get("metadata"),
                    created_at=data.get("created_at"),
                    updated_at=data.get("updated_at"),
                )
                return LedgerResult(success=True, data=account, status_code=200)

            error_detail = self._extract_error_detail(response)
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.account.get.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    def get_balance(self, account_id: str) -> LedgerResult:
        """Get account balance.

        Args:
            account_id: UUID of the account

        Returns:
            LedgerResult with LedgerBalance data if successful
        """
        try:
            logger.debug("ledger.balance.get.started", account_id=account_id)
            response = self.client.get(
                f"/v1/accounts/{account_id}/balance",
                headers=self._get_headers(),
            )

            if response.status_code == 200:
                data = response.json()
                balance = LedgerBalance(
                    account_id=account_id,
                    balance=data.get("balance", "0"),
                    available_balance=data.get("available_balance", "0"),
                    currency=data.get("currency", "CREDIT"),
                )
                return LedgerResult(success=True, data=balance, status_code=200)

            error_detail = self._extract_error_detail(response)
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.balance.get.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    # =========================================================================
    # Transfer Operations
    # =========================================================================

    def create_transfer(
        self,
        source_account_id: str,
        destination_account_id: str,
        amount: str,
        currency: str = "CREDIT",
        description: Optional[str] = None,
        require_confirmation: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> LedgerResult:
        """Create a transfer between accounts.

        Args:
            source_account_id: UUID of the source account (sender)
            destination_account_id: UUID of the destination account (recipient)
            amount: Amount to transfer as string (e.g., "1000")
            currency: Currency code (default "CREDIT")
            description: Optional description for the transfer
            require_confirmation: If True, returns confirmation token for later completion
            idempotency_key: Idempotency key (auto-generated if not provided)

        Returns:
            LedgerResult with LedgerTransfer data if successful.
            If require_confirmation=True, the transfer will have status="pending"
            and include a confirmation_token.
        """
        if idempotency_key is None:
            idempotency_key = generate_idempotency_key()

        payload: dict[str, Any] = {
            "source_account_id": source_account_id,
            "destination_account_id": destination_account_id,
            "amount": {"amount": amount, "currency": currency},
        }
        if description:
            payload["description"] = description
        if require_confirmation:
            payload["require_confirmation"] = True

        try:
            logger.debug(
                "ledger.transfer.create.started",
                source=source_account_id,
                destination=destination_account_id,
                amount=amount,
            )
            response = self.client.post(
                "/v1/transfers",
                json=payload,
                headers=self._get_headers(idempotency_key),
            )

            if response.status_code in (201, 202):
                data = response.json()
                transfer = LedgerTransfer(
                    id=data.get("id", ""),
                    source_account_id=data.get("source_account_id", ""),
                    destination_account_id=data.get("destination_account_id", ""),
                    amount=data.get("amount", {}).get("amount", "0"),
                    currency=data.get("amount", {}).get("currency", "CREDIT"),
                    status=data.get("status", ""),
                    confirmation_token=data.get("confirmation_token"),
                    description=data.get("description"),
                    created_at=data.get("created_at"),
                    completed_at=data.get("completed_at"),
                )
                logger.info(
                    "ledger.transfer.create.success",
                    transfer_id=transfer.id,
                    status=transfer.status,
                )
                return LedgerResult(
                    success=True, data=transfer, status_code=response.status_code
                )

            error_detail = self._extract_error_detail(response)
            logger.warning(
                "ledger.transfer.create.failed",
                status_code=response.status_code,
                error=error_detail,
            )
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            logger.error("ledger.transfer.create.timeout")
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            logger.error("ledger.transfer.create.network_error", error=str(e))
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.transfer.create.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    def confirm_transfer(
        self,
        confirmation_token: str,
        idempotency_key: Optional[str] = None,
    ) -> LedgerResult:
        """Confirm a pending transfer using its confirmation token.

        Args:
            confirmation_token: The confirmation token from create_transfer
            idempotency_key: Idempotency key (auto-generated if not provided)

        Returns:
            LedgerResult with LedgerTransfer data if successful
        """
        if idempotency_key is None:
            idempotency_key = generate_idempotency_key()

        try:
            logger.debug("ledger.transfer.confirm.started")
            response = self.client.post(
                "/v1/transfers/confirm",
                json={"confirmation_token": confirmation_token},
                headers=self._get_headers(idempotency_key),
            )

            if response.status_code == 200:
                data = response.json()
                transfer = LedgerTransfer(
                    id=data.get("id", ""),
                    source_account_id=data.get("source_account_id", ""),
                    destination_account_id=data.get("destination_account_id", ""),
                    amount=data.get("amount", {}).get("amount", "0"),
                    currency=data.get("amount", {}).get("currency", "CREDIT"),
                    status=data.get("status", ""),
                    description=data.get("description"),
                    created_at=data.get("created_at"),
                    completed_at=data.get("completed_at"),
                )
                logger.info("ledger.transfer.confirm.success", transfer_id=transfer.id)
                return LedgerResult(success=True, data=transfer, status_code=200)

            error_detail = self._extract_error_detail(response)
            logger.warning(
                "ledger.transfer.confirm.failed",
                status_code=response.status_code,
                error=error_detail,
            )
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            logger.error("ledger.transfer.confirm.timeout")
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            logger.error("ledger.transfer.confirm.network_error", error=str(e))
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.transfer.confirm.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    def cancel_transfer(
        self,
        transfer_id: str,
        idempotency_key: Optional[str] = None,
    ) -> LedgerResult:
        """Cancel a pending transfer.

        Args:
            transfer_id: UUID of the transfer to cancel
            idempotency_key: Idempotency key (auto-generated if not provided)

        Returns:
            LedgerResult with LedgerTransfer data if successful
        """
        if idempotency_key is None:
            idempotency_key = generate_idempotency_key()

        try:
            logger.debug("ledger.transfer.cancel.started", transfer_id=transfer_id)
            response = self.client.post(
                f"/v1/transfers/{transfer_id}/cancel",
                headers=self._get_headers(idempotency_key),
            )

            if response.status_code == 200:
                data = response.json()
                transfer = LedgerTransfer(
                    id=data.get("id", ""),
                    source_account_id=data.get("source_account_id", ""),
                    destination_account_id=data.get("destination_account_id", ""),
                    amount=data.get("amount", {}).get("amount", "0"),
                    currency=data.get("amount", {}).get("currency", "CREDIT"),
                    status=data.get("status", ""),
                    description=data.get("description"),
                    created_at=data.get("created_at"),
                    completed_at=data.get("completed_at"),
                )
                logger.info("ledger.transfer.cancel.success", transfer_id=transfer.id)
                return LedgerResult(success=True, data=transfer, status_code=200)

            error_detail = self._extract_error_detail(response)
            logger.warning(
                "ledger.transfer.cancel.failed",
                status_code=response.status_code,
                error=error_detail,
            )
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            logger.error("ledger.transfer.cancel.timeout")
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            logger.error("ledger.transfer.cancel.network_error", error=str(e))
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.transfer.cancel.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")

    def validate_token(self) -> LedgerResult:
        """Validate the API token by making a simple API call.

        This method attempts to access the API to verify the token is valid.
        Used during user registration/setup to validate provided credentials.

        Returns:
            LedgerResult with success=True if token is valid
        """
        try:
            # Try to list accounts - this validates the token
            response = self.client.get(
                "/v1/accounts",
                headers=self._get_headers(),
                params={"limit": 1},
            )

            if response.status_code == 200:
                return LedgerResult(success=True, status_code=200)

            if response.status_code == 401:
                return LedgerResult(
                    success=False,
                    error="Invalid or expired API token",
                    status_code=401,
                )

            error_detail = self._extract_error_detail(response)
            return LedgerResult(
                success=False,
                error=error_detail,
                status_code=response.status_code,
            )

        except httpx.TimeoutException:
            return LedgerResult(success=False, error="Ledger request timed out")
        except httpx.RequestError as e:
            return LedgerResult(
                success=False,
                error=f"Failed to connect to ledger: {e}",
            )
        except Exception as e:
            logger.exception("ledger.validate_token.unexpected_error", error=str(e))
            return LedgerResult(success=False, error=f"Unexpected error: {e}")
