"""Resource for managing API tokens."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from syfthub_sdk.models import (
    APIToken,
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenScope,
)

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class APITokensResource:
    """Resource for managing API tokens.

    API tokens provide an alternative to username/password authentication.
    They are ideal for CI/CD pipelines, scripts, and programmatic access.

    Example:
        # Create a new token
        result = client.api_tokens.create(
            name="CI/CD Pipeline",
            scopes=["write"],
        )
        print("Save this token:", result.token)

        # List all tokens
        response = client.api_tokens.list()
        for token in response.tokens:
            print(token.name, token.last_used_at)

        # Revoke a token
        client.api_tokens.revoke(token_id)
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize the API tokens resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def create(
        self,
        *,
        name: str,
        scopes: list[str | APITokenScope] | None = None,
        expires_at: datetime | None = None,
    ) -> APITokenCreateResponse:
        """Create a new API token.

        IMPORTANT: The returned token is only shown ONCE!
        Make sure to save it immediately - it cannot be retrieved later.

        Args:
            name: Descriptive name for the token (e.g., "CI/CD Pipeline")
            scopes: Permission scopes (default: ["full"]).
                    Options: "read", "write", "full"
            expires_at: Optional expiration date

        Returns:
            The created token with the full token value

        Example:
            result = client.api_tokens.create(
                name="CI/CD Pipeline",
                scopes=["write"],
                expires_at=datetime(2025, 12, 31),
            )

            # SAVE THIS TOKEN - it will not be shown again!
            print(result.token)
        """
        payload: dict[str, object] = {"name": name}

        if scopes is not None:
            # Convert enum values to strings if needed
            payload["scopes"] = [
                s.value if isinstance(s, APITokenScope) else s for s in scopes
            ]

        if expires_at is not None:
            payload["expires_at"] = expires_at.isoformat()

        data = self._http.post("/api/v1/auth/tokens", json=payload)
        return APITokenCreateResponse.model_validate(data)

    def list(
        self,
        *,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> APITokenListResponse:
        """List all API tokens for the current user.

        By default, only active tokens are returned.
        Note: The full token value is never returned - only the prefix.

        Args:
            include_inactive: Whether to include revoked tokens
            skip: Number of tokens to skip (for pagination)
            limit: Maximum number of tokens to return

        Returns:
            List of tokens and total count

        Example:
            # List active tokens
            response = client.api_tokens.list()
            for token in response.tokens:
                print(token.name, token.last_used_at)

            # Include revoked tokens
            all_tokens = client.api_tokens.list(include_inactive=True)
        """
        params: dict[str, object] = {
            "skip": skip,
            "limit": limit,
        }
        if include_inactive:
            params["include_inactive"] = True

        data = self._http.get("/api/v1/auth/tokens", params=params)
        return APITokenListResponse.model_validate(data)

    def get(self, token_id: int) -> APIToken:
        """Get a single API token by ID.

        Note: The full token value is never returned - only the prefix.

        Args:
            token_id: The token ID

        Returns:
            The token details

        Example:
            token = client.api_tokens.get(123)
            print(token.name, token.last_used_at)
        """
        data = self._http.get(f"/api/v1/auth/tokens/{token_id}")
        return APIToken.model_validate(data)

    def update(self, token_id: int, *, name: str) -> APIToken:
        """Update an API token's name.

        Only the name can be updated. Scopes and expiration cannot be
        changed after creation.

        Args:
            token_id: The token ID
            name: New name for the token

        Returns:
            The updated token

        Example:
            updated = client.api_tokens.update(123, name="New Name")
        """
        data = self._http.patch(f"/api/v1/auth/tokens/{token_id}", json={"name": name})
        return APIToken.model_validate(data)

    def revoke(self, token_id: int) -> None:
        """Revoke an API token.

        The token becomes immediately unusable. This action cannot be undone.

        Args:
            token_id: The token ID to revoke

        Example:
            client.api_tokens.revoke(123)
        """
        self._http.delete(f"/api/v1/auth/tokens/{token_id}")
