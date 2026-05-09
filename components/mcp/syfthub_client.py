"""
SyftHub API Client for MCP Server Authentication.

This module provides an asynchronous HTTP client for interacting with the SyftHub
authentication API, enabling user authentication via username/password instead of
the deprecated SyftBox OTP flow.

The client handles:
- User authentication (login with email/password)
- User profile retrieval
- Accounting credentials retrieval for paid service access
- Aggregator chat streaming with payment-required event detection

# MCP and paid endpoints
#
# MCP tool callers (Claude, ChatGPT, IDE assistants) do not have wallets
# and cannot sign Tempo transactions. When a paid endpoint is invoked
# through MCP, the chat_with_syfthub tool returns a structured error
# explaining that the user must pay via the syft CLI or desktop app.
#
# This is a known v1 limitation. v2 may introduce a paired-wallet flow
# where the MCP server proxies challenges to a long-lived CLI wallet
# daemon, but that is out of scope for now.
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

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


class PaymentRequiredError(Exception):
    """Raised when an aggregator chat call requires payment that the MCP
    layer cannot provide (no wallet)."""

    def __init__(
        self,
        *,
        endpoint_slug: str,
        challenge: str,
        amount: str,
        currency: str,
        recipient: str,
        challenge_id: str,
        intent: str,
    ):
        self.endpoint_slug = endpoint_slug
        self.challenge = challenge
        self.amount = amount
        self.currency = currency
        self.recipient = recipient
        self.challenge_id = challenge_id
        self.intent = intent
        super().__init__(
            f"Endpoint {endpoint_slug} requires payment of {amount} "
            f"{currency} to {recipient}; MCP cannot complete this payment."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": "payment_required",
            "endpoint_slug": self.endpoint_slug,
            "amount": self.amount,
            "currency": self.currency,
            "recipient": self.recipient,
            "challenge_id": self.challenge_id,
            "intent": self.intent,
            "hint": (
                "Use the syft CLI ('syft wallet' + 'syft query') or the "
                "SyftHub desktop app to pay this endpoint."
            ),
        }


def _build_payment_required_error(data: Dict[str, Any]) -> "PaymentRequiredError":
    """Construct a :class:`PaymentRequiredError` from an SSE event payload.

    The aggregator emits (per plan unit 10)::

        event: payment_required
        data: {chat_session_id, endpoint_slug, challenge, amount, currency,
               recipient, challenge_id, intent}

    Missing fields default to empty strings so the error is always raisable
    even if the aggregator omits a field; callers can still inspect what
    was present.
    """
    return PaymentRequiredError(
        endpoint_slug=str(data.get("endpoint_slug", "")),
        challenge=str(data.get("challenge", "")),
        amount=str(data.get("amount", "")),
        currency=str(data.get("currency", "")),
        recipient=str(data.get("recipient", "")),
        challenge_id=str(data.get("challenge_id", "")),
        intent=str(data.get("intent", "")),
    )


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

    async def chat_stream(
        self,
        *,
        aggregator_url: str,
        request_body: Dict[str, Any],
        access_token: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream chat events from the aggregator's SSE endpoint, detecting
        ``payment_required`` events.

        This is a thin wrapper around the aggregator's ``POST /chat/stream``
        SSE endpoint. It does its own SSE parsing so it can recognise the
        ``payment_required`` event added by the transaction-policy work
        (plan unit 10) and raise :class:`PaymentRequiredError` on the
        FIRST such event — even if multiple endpoints in the same chat
        require payment, the LLM caller only needs to know one is required.

        All other events are yielded verbatim as ``{"type": str, "data": dict}``
        for callers that want to consume the stream (e.g. accumulating tokens
        for a non-streaming response).

        Args:
            aggregator_url: Base aggregator URL (e.g. ``http://aggregator:8001``).
                The ``/chat/stream`` path is appended.
            request_body: Aggregator request body (already shaped by the SDK
                or caller — model_ref, ds_refs, tokens, etc.).
            access_token: Optional bearer token for the aggregator request.

        Yields:
            Dicts with ``type`` (event name) and ``data`` (parsed JSON payload).

        Raises:
            PaymentRequiredError: If a ``payment_required`` SSE event is seen.
            ConnectionError: If the aggregator cannot be reached.
            SyftHubError: For other aggregator errors.
        """
        url = f"{aggregator_url.rstrip('/')}/chat/stream"
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", url, json=request_body, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise SyftHubError(
                            f"Aggregator returned {response.status_code}: "
                            f"{body.decode('utf-8', errors='replace')[:500]}"
                        )

                    current_event: Optional[str] = None
                    current_data: str = ""

                    async for line in response.aiter_lines():
                        line = line.strip()

                        if not line:
                            if current_event and current_data:
                                try:
                                    data = json.loads(current_data)
                                except json.JSONDecodeError as exc:
                                    logger.warning(
                                        f"Failed to parse SSE data for "
                                        f"event={current_event}: {exc}"
                                    )
                                    current_event = None
                                    current_data = ""
                                    continue

                                if current_event == "payment_required":
                                    raise _build_payment_required_error(data)

                                yield {"type": current_event, "data": data}

                            current_event = None
                            current_data = ""
                            continue

                        if line.startswith("event:"):
                            current_event = line[len("event:") :].strip()
                        elif line.startswith("data:"):
                            current_data = line[len("data:") :].strip()

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Failed to connect to aggregator at {url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Aggregator request timed out: {e}") from e
        except (PaymentRequiredError, SyftHubError, ConnectionError):
            raise
        except Exception as e:
            raise SyftHubError(f"Unexpected error during chat stream: {e}") from e

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
