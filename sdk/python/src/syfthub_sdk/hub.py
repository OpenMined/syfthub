"""Hub resource for browsing public endpoints.

This module handles discovery and browsing of public endpoints from other users.
For managing your own endpoints, see the `my_endpoints` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.models import EndpointPublic

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class HubResource:
    """Browse and discover public endpoints from the hub.

    Example usage:
        # Browse all public endpoints
        for endpoint in client.hub.browse():
            print(f"{endpoint.path}: {endpoint.name}")

        # Get trending endpoints
        for endpoint in client.hub.trending(min_stars=10):
            print(f"{endpoint.name} - {endpoint.stars_count} stars")

        # Get a specific endpoint by path
        endpoint = client.hub.get("alice/cool-api")
        print(endpoint.readme)

        # Star an endpoint (requires auth)
        client.hub.star("alice/cool-api")

        # Check if you've starred an endpoint
        if client.hub.is_starred("alice/cool-api"):
            print("You've starred this!")

        # Unstar an endpoint
        client.hub.unstar("alice/cool-api")
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize hub resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

    def browse(self, *, page_size: int = 20) -> PageIterator[EndpointPublic]:
        """Browse all public endpoints.

        Args:
            page_size: Number of items per page (default 20)

        Returns:
            PageIterator that lazily fetches endpoints
        """

        def fetch_fn(skip: int, limit: int) -> list[dict[str, Any]]:
            response = self._http.get(
                "/api/v1/endpoints/public",
                params={"skip": skip, "limit": limit},
                include_auth=False,
            )
            return response if isinstance(response, list) else []

        return PageIterator(fetch_fn, EndpointPublic, page_size=page_size)

    def trending(
        self,
        *,
        min_stars: int | None = None,
        page_size: int = 20,
    ) -> PageIterator[EndpointPublic]:
        """Get trending endpoints sorted by stars.

        Args:
            min_stars: Minimum number of stars (optional filter)
            page_size: Number of items per page (default 20)

        Returns:
            PageIterator that lazily fetches endpoints
        """

        def fetch_fn(skip: int, limit: int) -> list[dict[str, Any]]:
            params: dict[str, Any] = {"skip": skip, "limit": limit}
            if min_stars is not None:
                params["min_stars"] = min_stars
            response = self._http.get(
                "/api/v1/endpoints/trending",
                params=params,
                include_auth=False,
            )
            return response if isinstance(response, list) else []

        return PageIterator(fetch_fn, EndpointPublic, page_size=page_size)

    def get(self, path: str) -> EndpointPublic:
        """Get an endpoint by its path (owner/slug format).

        This method searches the public endpoints API to find the endpoint,
        which works reliably across all deployment configurations.

        Args:
            path: Endpoint path in "owner/slug" format (e.g., "alice/cool-api")

        Returns:
            The EndpointPublic

        Raises:
            NotFoundError: If endpoint not found
            ValueError: If path format is invalid
        """
        from syfthub_sdk.exceptions import NotFoundError

        owner, slug = self._parse_path(path)

        # Search public endpoints to find the matching one
        # This approach works because /api/v1/endpoints/public is reliably
        # served by the backend API, unlike /{owner}/{slug} which may be
        # intercepted by frontend routing in some deployments.
        for endpoint in self.browse(page_size=100):
            if endpoint.owner_username == owner and endpoint.slug == slug:
                return endpoint

        raise NotFoundError(
            message=f"Endpoint not found: '{path}'",
            detail=f"No public endpoint found with owner '{owner}' and slug '{slug}'",
        )

    def star(self, path: str) -> None:
        """Star an endpoint.

        Args:
            path: Endpoint path in "owner/slug" format

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
        """
        endpoint_id = self._resolve_endpoint_id(path)
        self._http.post(f"/api/v1/endpoints/{endpoint_id}/star")

    def unstar(self, path: str) -> None:
        """Unstar an endpoint.

        Args:
            path: Endpoint path in "owner/slug" format

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
        """
        endpoint_id = self._resolve_endpoint_id(path)
        self._http.delete(f"/api/v1/endpoints/{endpoint_id}/star")

    def is_starred(self, path: str) -> bool:
        """Check if you have starred an endpoint.

        Args:
            path: Endpoint path in "owner/slug" format

        Returns:
            True if starred, False otherwise

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
        """
        endpoint_id = self._resolve_endpoint_id(path)
        response = self._http.get(f"/api/v1/endpoints/{endpoint_id}/starred")
        data = response if isinstance(response, dict) else {}
        return bool(data.get("starred", False))

    def _parse_path(self, path: str) -> tuple[str, str]:
        """Parse an endpoint path into owner and slug.

        Args:
            path: Path in "owner/slug" format

        Returns:
            Tuple of (owner, slug)

        Raises:
            ValueError: If path format is invalid
        """
        parts = path.strip("/").split("/")
        if len(parts) != 2:
            raise ValueError(
                f"Invalid endpoint path: '{path}'. Expected format: 'owner/slug'"
            )
        return parts[0], parts[1]

    def _resolve_endpoint_id(self, path: str) -> int:
        """Resolve an endpoint path to its ID.

        This requires authentication to get the full endpoint details.
        Uses the user's own endpoints API to find the ID.

        Args:
            path: Endpoint path in "owner/slug" format

        Returns:
            The endpoint ID

        Raises:
            NotFoundError: If endpoint not found
            AuthenticationError: If not authenticated
        """
        from syfthub_sdk.exceptions import NotFoundError

        owner, slug = self._parse_path(path)

        # Search the user's endpoints to find the ID
        # This uses /api/v1/endpoints which returns full details including ID
        response = self._http.get(
            "/api/v1/endpoints",
            params={"limit": 100},
        )
        endpoints = response if isinstance(response, list) else []

        for ep in endpoints:
            if ep.get("slug") == slug:
                endpoint_id = ep.get("id")
                if endpoint_id is not None:
                    return int(endpoint_id)

        # If not found in user's endpoints, the endpoint might belong to another user
        # In this case, we need to search public endpoints and use a different approach
        raise NotFoundError(
            message=f"Could not resolve endpoint ID for '{path}'",
            detail="Endpoint not found or you don't have access to get its ID. "
            "Star/unstar operations require the endpoint ID which is only "
            "available for endpoints you own.",
        )
