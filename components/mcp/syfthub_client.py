"""
SyftHub API Client for MCP Server Authentication.

This module provides an asynchronous HTTP client for interacting with the SyftHub
authentication API, enabling user authentication via username/password instead of
the deprecated SyftBox OTP flow.

The client handles:
- User authentication (login with email/password)
- User profile retrieval
- Accounting credentials retrieval for paid service access
"""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class SyftHubError(Exception):
    """Base exception for SyftHub client errors."""

    pass


class AuthenticationError(SyftHubError):
    """Raised when authentication fails (invalid credentials)."""

    pass


class ConnectionError(SyftHubError):
    """Raised when connection to SyftHub fails."""

    pass


class SyftHubClient:
    """
    Asynchronous HTTP client for SyftHub API interactions.

    Provides methods for authenticating users against SyftHub's auth system
    and retrieving user profile and accounting credentials.

    Attributes:
        base_url (str): Base URL for the SyftHub API server (e.g., "http://backend:8000")
        api_prefix (str): API version prefix (default: "/api/v1")
        timeout (float): Request timeout in seconds
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_prefix: str = "/api/v1",
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the SyftHub client.

        Args:
            base_url: Base URL for the SyftHub API (default: "http://localhost:8000")
            api_prefix: API version prefix (default: "/api/v1")
            timeout: Request timeout in seconds (default: 30.0)
        """
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix
        self.timeout = timeout
        logger.info(f"SyftHubClient initialized with base_url: {self.base_url}")

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an API endpoint."""
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self.base_url}{self.api_prefix}{endpoint}"

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user with SyftHub using email and password.

        SyftHub accepts either email or username in the 'username' field
        of the OAuth2 password flow.

        Args:
            email: User's email address (or username)
            password: User's password

        Returns:
            Dict containing:
                - access_token: JWT access token
                - refresh_token: JWT refresh token
                - token_type: Token type (typically "bearer")

        Raises:
            AuthenticationError: If credentials are invalid
            ConnectionError: If connection to SyftHub fails
            SyftHubError: For other API errors
        """
        url = self._build_url("/auth/login")
        logger.info(f"Attempting login for user: {email}")

        # SyftHub uses OAuth2PasswordRequestForm which expects form data
        form_data = {"username": email, "password": password}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, data=form_data)

                if response.status_code == 200:
                    tokens = response.json()
                    logger.info(f"Login successful for user: {email}")
                    return tokens

                elif response.status_code == 401:
                    error_detail = "Invalid email or password"
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("detail", error_detail)
                    except Exception:
                        pass
                    logger.warning(f"Login failed for {email}: {error_detail}")
                    raise AuthenticationError(error_detail)

                elif response.status_code == 400:
                    error_detail = "Invalid request"
                    try:
                        error_data = response.json()
                        error_detail = error_data.get("detail", error_detail)
                    except Exception:
                        pass
                    logger.warning(f"Login bad request for {email}: {error_detail}")
                    raise SyftHubError(error_detail)

                else:
                    error_msg = f"Unexpected response: {response.status_code}"
                    logger.error(f"Login error for {email}: {error_msg}")
                    raise SyftHubError(error_msg)

        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to SyftHub at {self.base_url}: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        except httpx.TimeoutException as e:
            error_msg = f"Request to SyftHub timed out: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        except (AuthenticationError, SyftHubError):
            raise

        except Exception as e:
            error_msg = f"Unexpected error during login: {e}"
            logger.error(error_msg)
            raise SyftHubError(error_msg) from e

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get the current user's profile information.

        Args:
            access_token: Valid JWT access token from login

        Returns:
            Dict containing user profile:
                - id: User ID
                - username: Username
                - email: Email address
                - full_name: Full name
                - role: User role (admin, user, guest)
                - is_active: Account status
                - avatar_url: Avatar URL (optional)
                - domain: Custom domain (optional)
                - created_at: Account creation timestamp
                - updated_at: Last update timestamp

        Raises:
            AuthenticationError: If token is invalid or expired
            ConnectionError: If connection to SyftHub fails
            SyftHubError: For other API errors
        """
        url = self._build_url("/auth/me")
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    user_info = response.json()
                    logger.debug(f"Retrieved user info for user ID: {user_info.get('id')}")
                    return user_info

                elif response.status_code == 401:
                    logger.warning("Token invalid or expired when fetching user info")
                    raise AuthenticationError("Invalid or expired token")

                else:
                    error_msg = f"Failed to get user info: {response.status_code}"
                    logger.error(error_msg)
                    raise SyftHubError(error_msg)

        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to SyftHub: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        except (AuthenticationError, SyftHubError):
            raise

        except Exception as e:
            error_msg = f"Unexpected error fetching user info: {e}"
            logger.error(error_msg)
            raise SyftHubError(error_msg) from e

    async def get_accounting_credentials(
        self, access_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the user's accounting service credentials.

        SyftHub automatically creates accounting credentials for users during
        registration. These credentials are used for accessing paid services
        in the distributed network.

        Args:
            access_token: Valid JWT access token from login

        Returns:
            Dict containing accounting credentials if available:
                - accounting_service_url: URL of the accounting service
                - accounting_password: Password for the accounting service
            Returns None if no accounting credentials are configured.

        Raises:
            AuthenticationError: If token is invalid or expired
            ConnectionError: If connection to SyftHub fails
            SyftHubError: For other API errors
        """
        url = self._build_url("/users/me/accounting")
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    credentials = response.json()
                    has_creds = bool(credentials.get("accounting_password"))
                    logger.debug(f"Retrieved accounting credentials: {has_creds}")
                    return credentials

                elif response.status_code == 401:
                    logger.warning("Token invalid when fetching accounting credentials")
                    raise AuthenticationError("Invalid or expired token")

                elif response.status_code == 404:
                    logger.info("No accounting credentials found for user")
                    return None

                else:
                    error_msg = f"Failed to get accounting credentials: {response.status_code}"
                    logger.error(error_msg)
                    raise SyftHubError(error_msg)

        except httpx.ConnectError as e:
            error_msg = f"Failed to connect to SyftHub: {e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg) from e

        except (AuthenticationError, SyftHubError):
            raise

        except Exception as e:
            error_msg = f"Unexpected error fetching accounting credentials: {e}"
            logger.error(error_msg)
            raise SyftHubError(error_msg) from e

    async def check_health(self) -> bool:
        """
        Check if SyftHub is reachable and healthy.

        Returns:
            True if SyftHub is healthy, False otherwise
        """
        # Health endpoint is at root level, not under /api/v1
        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                is_healthy = response.status_code == 200
                logger.debug(f"SyftHub health check: {is_healthy}")
                return is_healthy

        except Exception as e:
            logger.warning(f"SyftHub health check failed: {e}")
            return False
