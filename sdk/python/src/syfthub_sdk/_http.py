"""Internal HTTP client for SyftHub SDK."""

from __future__ import annotations

from typing import Any

import httpx

from syfthub_sdk.exceptions import (
    AccountingAccountExistsError,
    AccountingServiceUnavailableError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    InvalidAccountingPasswordError,
    NotFoundError,
    ValidationError,
)
from syfthub_sdk.models import AuthTokens


class HTTPClient:
    """HTTP client with automatic token management."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize HTTP client.

        Args:
            base_url: Base URL for the API (e.g., "https://hub.syft.com")
            timeout: Request timeout in seconds
        """
        # Ensure base_url doesn't end with /
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # Token storage
        self._access_token: str | None = None
        self._refresh_token: str | None = None

        # HTTP client
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @property
    def is_authenticated(self) -> bool:
        """Check if client has tokens set."""
        return self._access_token is not None

    def set_tokens(self, tokens: AuthTokens) -> None:
        """Set authentication tokens.

        Args:
            tokens: AuthTokens with access_token and refresh_token
        """
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token

    def get_tokens(self) -> AuthTokens | None:
        """Get current authentication tokens.

        Returns:
            AuthTokens if authenticated, None otherwise
        """
        if self._access_token and self._refresh_token:
            return AuthTokens(
                access_token=self._access_token,
                refresh_token=self._refresh_token,
            )
        return None

    def clear_tokens(self) -> None:
        """Clear authentication tokens."""
        self._access_token = None
        self._refresh_token = None

    def _get_headers(self, include_auth: bool = True) -> dict[str, str]:
        """Build request headers.

        Args:
            include_auth: Whether to include Authorization header

        Returns:
            Dictionary of headers
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if include_auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _handle_error(self, response: httpx.Response) -> None:
        """Convert HTTP errors to SDK exceptions.

        Args:
            response: HTTP response object

        Raises:
            SyftHubError: Appropriate exception based on status code
        """
        status = response.status_code
        try:
            detail = response.json()
        except Exception:
            detail = response.text

        # Extract message from detail if it's a dict
        # Handle both {"detail": {...}} and {"detail": "string"} formats
        inner_detail = detail.get("detail", detail) if isinstance(detail, dict) else detail

        if isinstance(inner_detail, dict):
            message = inner_detail.get("message", str(inner_detail))
            error_code = inner_detail.get("code")
        else:
            message = str(inner_detail)
            error_code = None

        # Check for accounting-specific errors based on error code
        if isinstance(inner_detail, dict) and error_code:
            if error_code == "ACCOUNTING_ACCOUNT_EXISTS":
                raise AccountingAccountExistsError(message=message, detail=inner_detail)
            elif error_code == "INVALID_ACCOUNTING_PASSWORD":
                raise InvalidAccountingPasswordError(message=message, detail=inner_detail)
            elif error_code == "ACCOUNTING_SERVICE_UNAVAILABLE":
                raise AccountingServiceUnavailableError(message=message, detail=inner_detail)

        # Standard error handling based on status code
        if status == 401:
            raise AuthenticationError(message=message, detail=detail)
        elif status == 403:
            raise AuthorizationError(message=message, detail=detail)
        elif status == 404:
            raise NotFoundError(message=message, detail=detail)
        elif status == 422:
            raise ValidationError(message=message, detail=detail)
        else:
            raise APIError(
                message=message,
                status_code=status,
                detail=detail,
            )

    def _attempt_refresh(self) -> bool:
        """Attempt to refresh the access token.

        Returns:
            True if refresh succeeded, False otherwise
        """
        if not self._refresh_token:
            return False

        try:
            response = self._client.post(
                f"{self.base_url}/api/v1/auth/refresh",
                headers={"Content-Type": "application/json"},
                json={"refresh_token": self._refresh_token},
            )
            if response.status_code == 200:
                data = response.json()
                self._access_token = data["access_token"]
                self._refresh_token = data["refresh_token"]
                return True
        except Exception:
            pass
        return False

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        include_auth: bool = True,
        retry_on_401: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            path: URL path (will be joined with base_url)
            json: JSON body data
            params: Query parameters
            data: Form data (for login endpoint)
            include_auth: Whether to include Authorization header
            retry_on_401: Whether to retry with token refresh on 401

        Returns:
            Parsed JSON response

        Raises:
            SyftHubError: On API errors
        """
        url = f"{self.base_url}{path}"
        headers = self._get_headers(include_auth=include_auth)

        # For form data (OAuth2 login), adjust content type
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        response = self._client.request(
            method=method,
            url=url,
            headers=headers,
            json=json,
            params=params,
            data=data,
        )

        # Handle 401 with token refresh
        if (
            response.status_code == 401
            and retry_on_401
            and include_auth
            and self._attempt_refresh()
        ):
            # Retry with new token
            return self.request(
                method=method,
                path=path,
                json=json,
                params=params,
                data=data,
                include_auth=include_auth,
                retry_on_401=False,  # Don't retry again
            )

        # Handle errors
        if response.status_code >= 400:
            self._handle_error(response)

        # Return parsed JSON (or empty dict for 204 No Content)
        if response.status_code == 204:
            return {}

        return response.json()  # type: ignore[no-any-return]

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request."""
        return self.request("GET", path, params=params, include_auth=include_auth)

    def post(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a POST request."""
        return self.request(
            "POST", path, json=json, data=data, include_auth=include_auth
        )

    def put(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a PUT request."""
        return self.request("PUT", path, json=json, include_auth=include_auth)

    def patch(
        self,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a PATCH request."""
        return self.request("PATCH", path, json=json, include_auth=include_auth)

    def delete(
        self,
        path: str,
        *,
        include_auth: bool = True,
    ) -> dict[str, Any] | list[Any]:
        """Make a DELETE request."""
        return self.request("DELETE", path, include_auth=include_auth)
