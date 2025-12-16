"""HTTP client for external accounting service integration.

This module provides a client for communicating with the external accounting
service during user registration and credential validation.

The accounting service API (from OpenMined/accounting-sdk):
- POST /user/create - Create a new user
- GET /user/my-info - Get current user info (validates credentials)

Authentication: HTTP Basic Auth (email:password)
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Result Types
# =============================================================================


@dataclass(frozen=True)
class AccountingUser:
    """User data from the accounting service."""

    id: str
    email: str
    balance: float
    organization: Optional[str] = None


@dataclass(frozen=True)
class AccountingUserResult:
    """Result of an accounting service user operation.

    Attributes:
        success: Whether the operation succeeded
        user: User data if successful
        conflict: True if the operation failed due to email already existing (409)
        error: Error message if the operation failed
    """

    success: bool
    user: Optional[AccountingUser] = None
    conflict: bool = False
    error: Optional[str] = None


# =============================================================================
# Password Generation
# =============================================================================


def generate_accounting_password(length: int = 32) -> str:
    """Generate a secure random password for accounting service.

    Args:
        length: Password length (default 32 characters)

    Returns:
        A secure random password containing letters, digits, and special chars
    """
    # Use a mix of characters for strong passwords
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one of each type
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    # Fill the rest
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    # Shuffle to avoid predictable positions
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    return "".join(password_list)


# =============================================================================
# Accounting Client
# =============================================================================


class AccountingClient:
    """HTTP client for external accounting service.

    This client handles communication with the accounting service for:
    - Creating new user accounts during registration
    - Validating existing credentials when users claim to have an account

    Example:
        client = AccountingClient("https://accounting.example.com")

        # Create a new user
        result = client.create_user("user@example.com", "password123")
        if result.success:
            print(f"Created user: {result.user.email}")
        elif result.conflict:
            print("User already exists")

        # Validate credentials
        if client.validate_credentials("user@example.com", "password123"):
            print("Credentials are valid")
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """Initialize the accounting client.

        Args:
            base_url: Base URL of the accounting service (e.g., "https://accounting.example.com")
            timeout: Request timeout in seconds (default 30)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client (lazy initialization)."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> AccountingClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit - close client."""
        self.close()

    def _parse_user_response(self, data: dict[str, Any]) -> AccountingUser:
        """Parse user data from API response.

        Args:
            data: Response data containing user info

        Returns:
            AccountingUser instance
        """
        # The API returns either {user: {...}} or just {...}
        user_data = data.get("user", data)
        return AccountingUser(
            id=user_data.get("id", ""),
            email=user_data.get("email", ""),
            balance=float(user_data.get("balance", 0.0)),
            organization=user_data.get("organization"),
        )

    def create_user(
        self,
        email: str,
        password: str,
        organization: Optional[str] = None,
    ) -> AccountingUserResult:
        """Create a new user in the accounting service.

        Args:
            email: User's email address
            password: Password for the accounting account
            organization: Optional organization name

        Returns:
            AccountingUserResult with:
            - success=True and user data if created successfully
            - conflict=True if email already exists (409)
            - error message for other failures
        """
        payload = {
            "email": email,
            "password": password,
        }
        if organization:
            payload["organization"] = organization

        try:
            logger.debug(f"Creating accounting user for email: {email}")
            response = self.client.post("/user/create", json=payload)

            if response.status_code == 201:
                data = response.json()
                user = self._parse_user_response(data)
                logger.info(f"Successfully created accounting user: {email}")
                return AccountingUserResult(success=True, user=user)

            if response.status_code == 409:
                logger.info(f"Accounting user already exists: {email}")
                return AccountingUserResult(
                    success=False,
                    conflict=True,
                    error="User with this email already exists in the accounting service",
                )

            # Other error responses
            error_detail = self._extract_error_detail(response)
            logger.warning(
                f"Failed to create accounting user {email}: "
                f"{response.status_code} - {error_detail}"
            )
            return AccountingUserResult(success=False, error=error_detail)

        except httpx.TimeoutException:
            logger.error(f"Timeout creating accounting user: {email}")
            return AccountingUserResult(
                success=False,
                error="Accounting service request timed out",
            )
        except httpx.RequestError as e:
            logger.error(f"Network error creating accounting user {email}: {e}")
            return AccountingUserResult(
                success=False,
                error=f"Failed to connect to accounting service: {e}",
            )
        except Exception as e:
            logger.exception(f"Unexpected error creating accounting user {email}: {e}")
            return AccountingUserResult(
                success=False,
                error=f"Unexpected error: {e}",
            )

    def validate_credentials(self, email: str, password: str) -> bool:
        """Validate existing accounting credentials.

        Uses GET /user/my-info with Basic auth to verify credentials.

        Args:
            email: User's email address
            password: User's accounting password

        Returns:
            True if credentials are valid (200 response), False otherwise
        """
        try:
            logger.debug(f"Validating accounting credentials for: {email}")
            response = self.client.get(
                "/user/my-info",
                auth=(email, password),
            )

            if response.status_code == 200:
                logger.info(f"Accounting credentials valid for: {email}")
                return True

            logger.info(
                f"Accounting credentials invalid for {email}: {response.status_code}"
            )
            return False

        except httpx.TimeoutException:
            logger.error(f"Timeout validating accounting credentials: {email}")
            return False
        except httpx.RequestError as e:
            logger.error(
                f"Network error validating accounting credentials {email}: {e}"
            )
            return False
        except Exception as e:
            logger.exception(
                f"Unexpected error validating accounting credentials {email}: {e}"
            )
            return False

    def get_user(self, email: str, password: str) -> Optional[AccountingUser]:
        """Get user info from the accounting service.

        Args:
            email: User's email address
            password: User's accounting password

        Returns:
            AccountingUser if credentials are valid, None otherwise
        """
        try:
            response = self.client.get(
                "/user/my-info",
                auth=(email, password),
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_user_response(data)

            return None

        except Exception as e:
            logger.error(f"Error getting accounting user {email}: {e}")
            return None

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract error detail from response.

        Args:
            response: HTTP response object

        Returns:
            Error message string
        """
        try:
            data = response.json()
            # Try common error fields
            if isinstance(data, dict):
                return (
                    data.get("detail")
                    or data.get("message")
                    or data.get("error")
                    or str(data)
                )
            return str(data)
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"
