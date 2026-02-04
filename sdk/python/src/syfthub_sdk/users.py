"""Users resource for SyftHub SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING

from syfthub_sdk.models import (
    AccountingCredentials,
    HeartbeatResponse,
    NatsCredentials,
    User,
)

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class UsersResource:
    """Handle user profile operations.

    Example usage:
        # Update profile
        user = client.users.update(
            full_name="John D.",
            avatar_url="https://example.com/avatar.png"
        )

        # Check username availability
        if client.users.check_username("newusername"):
            print("Username is available!")

        # Check email availability
        if client.users.check_email("new@example.com"):
            print("Email is available!")
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize users resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def update(
        self,
        *,
        username: str | None = None,
        email: str | None = None,
        full_name: str | None = None,
        avatar_url: str | None = None,
        domain: str | None = None,
    ) -> User:
        """Update the current user's profile.

        Only provided fields will be updated.

        Args:
            username: New username (3-50 chars)
            email: New email address
            full_name: New full name (1-100 chars)
            avatar_url: New avatar URL (max 500 chars)
            domain: Domain for endpoint URL construction (no protocol,
                    e.g., "api.example.com" or "api.example.com:8080")

        Returns:
            Updated User

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If update data is invalid
        """
        # Build update payload with only provided fields
        payload: dict[str, str] = {}
        if username is not None:
            payload["username"] = username
        if email is not None:
            payload["email"] = email
        if full_name is not None:
            payload["full_name"] = full_name
        if avatar_url is not None:
            payload["avatar_url"] = avatar_url
        if domain is not None:
            payload["domain"] = domain

        response = self._http.put("/api/v1/users/me", json=payload)
        data = response if isinstance(response, dict) else {}
        return User.model_validate(data)

    def check_username(self, username: str) -> bool:
        """Check if a username is available.

        Args:
            username: Username to check

        Returns:
            True if username is available, False otherwise
        """
        response = self._http.get(
            f"/api/v1/users/check-username/{username}",
            include_auth=False,
        )
        data = response if isinstance(response, dict) else {}
        return bool(data.get("available", False))

    def check_email(self, email: str) -> bool:
        """Check if an email is available.

        Args:
            email: Email to check

        Returns:
            True if email is available, False otherwise
        """
        response = self._http.get(
            f"/api/v1/users/check-email/{email}",
            include_auth=False,
        )
        data = response if isinstance(response, dict) else {}
        return bool(data.get("available", False))

    def get_accounting_credentials(self) -> AccountingCredentials:
        """Get the current user's accounting service credentials.

        Returns credentials stored in SyftHub for connecting to an external
        accounting service. The email is always the same as the user's SyftHub email.

        Returns:
            AccountingCredentials with url, email, and password.
            url and password may be None if not configured.

        Raises:
            AuthenticationError: If not authenticated

        Example:
            credentials = client.users.get_accounting_credentials()
            if credentials.url and credentials.password:
                # Use credentials to connect to accounting service
                pass
        """
        response = self._http.get("/api/v1/users/me/accounting")
        data = response if isinstance(response, dict) else {}
        return AccountingCredentials.model_validate(data)

    def get_nats_credentials(self) -> NatsCredentials:
        """Get NATS credentials for connecting to the NATS server.

        Fetches the shared NATS auth token from the hub. Spaces call this
        after login to obtain credentials for NATS WebSocket connections.

        Returns:
            NatsCredentials with the NATS auth token.

        Raises:
            AuthenticationError: If not authenticated
            APIError: If NATS is not configured on the hub (503)

        Example:
            creds = client.users.get_nats_credentials()
            # Use creds.nats_auth_token to connect to NATS
        """
        response = self._http.get("/api/v1/nats/credentials")
        data = response if isinstance(response, dict) else {}
        return NatsCredentials.model_validate(data)

    def send_heartbeat(
        self,
        url: str,
        ttl_seconds: int = 300,
    ) -> HeartbeatResponse:
        """Send a heartbeat to indicate this SyftAI Space is alive.

        The heartbeat mechanism allows SyftAI Spaces to signal their availability
        to SyftHub. This should be called periodically (before the TTL expires)
        to maintain the "active" status.

        Args:
            url: Full URL of this space (e.g., "https://myspace.example.com").
                 The server extracts the domain from this URL.
            ttl_seconds: Time-to-live in seconds (1-3600). The server caps this
                        at a maximum of 600 seconds (10 minutes). Default is 300
                        seconds (5 minutes).

        Returns:
            HeartbeatResponse containing:
                - status: "ok" if successful
                - received_at: When the server received the heartbeat
                - expires_at: When the heartbeat will expire
                - domain: Extracted domain from the URL
                - ttl_seconds: Effective TTL (may be capped by server)

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If URL or TTL is invalid

        Example:
            # Send heartbeat with default TTL (300 seconds)
            response = client.users.send_heartbeat(
                url="https://myspace.example.com"
            )
            print(f"Next heartbeat before: {response.expires_at}")

            # Send heartbeat with custom TTL
            response = client.users.send_heartbeat(
                url="https://myspace.example.com",
                ttl_seconds=600  # Maximum allowed
            )
        """
        response = self._http.post(
            "/api/v1/users/me/heartbeat",
            json={"url": url, "ttl_seconds": ttl_seconds},
        )
        data = response if isinstance(response, dict) else {}
        return HeartbeatResponse.model_validate(data)
