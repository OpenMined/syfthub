"""My Endpoints resource for SyftHub SDK.

This module handles CRUD operations for the user's own endpoints.
For browsing public endpoints from other users, see the `hub` module.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.models import (
    Connection,
    Endpoint,
    EndpointType,
    Policy,
    SyncEndpointsResponse,
    Visibility,
)

if TYPE_CHECKING:
    from syfthub_sdk._http import HTTPClient


class MyEndpointsResource:
    """Handle CRUD operations for user's own endpoints.

    Example usage:
        # List my endpoints (with pagination)
        for endpoint in client.my_endpoints.list():
            print(f"{endpoint.name} ({endpoint.visibility})")

        # Get first page only
        first_page = client.my_endpoints.list().first_page()

        # Create a new endpoint
        endpoint = client.my_endpoints.create(
            name="My API",
            type="model",  # or "data_source"
            visibility="public",
            description="A cool API",
            readme="# My API\\n\\nThis is my API."
        )

        # Get a specific endpoint by path (owner/slug format)
        endpoint = client.my_endpoints.get("alice/my-api")

        # Update an endpoint
        endpoint = client.my_endpoints.update(
            "alice/my-api",
            description="Updated description"
        )

        # Delete an endpoint
        client.my_endpoints.delete("alice/my-api")
    """

    def __init__(self, http: HTTPClient) -> None:
        """Initialize my endpoints resource.

        Args:
            http: HTTP client instance
        """
        self._http = http

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

    def list(
        self,
        *,
        visibility: Visibility | str | None = None,
        page_size: int = 20,
    ) -> PageIterator[Endpoint]:
        """List the current user's endpoints.

        Args:
            visibility: Filter by visibility (public, private, internal)
            page_size: Number of items per page (default 20)

        Returns:
            PageIterator that lazily fetches endpoints

        Raises:
            AuthenticationError: If not authenticated
        """

        def fetch_fn(skip: int, limit: int) -> list[dict[str, Any]]:
            params: dict[str, Any] = {"skip": skip, "limit": limit}
            if visibility is not None:
                vis_value = (
                    visibility.value
                    if isinstance(visibility, Visibility)
                    else visibility
                )
                params["visibility"] = vis_value
            response = self._http.get("/api/v1/endpoints", params=params)
            return response if isinstance(response, list) else []

        return PageIterator(fetch_fn, Endpoint, page_size=page_size)

    def create(
        self,
        *,
        name: str,
        type: EndpointType | str,
        visibility: Visibility | str = Visibility.PUBLIC,
        description: str = "",
        slug: str | None = None,
        version: str = "0.1.0",
        readme: str = "",
        tags: builtins.list[str] | None = None,
        policies: builtins.list[Policy] | builtins.list[dict[str, Any]] | None = None,
        connect: builtins.list[Connection]
        | builtins.list[dict[str, Any]]
        | None = None,
        contributors: builtins.list[int] | None = None,
        organization_id: int | None = None,
    ) -> Endpoint:
        """Create a new endpoint.

        Args:
            name: Display name (1-100 chars)
            type: Endpoint type (model or data_source)
            visibility: Who can access (public, private, internal)
            description: Short description (max 500 chars)
            slug: URL-safe identifier (auto-generated from name if not provided)
            version: Semantic version (default "0.1.0")
            readme: Markdown README content (max 50000 chars)
            tags: List of tags for categorization
            policies: List of policy configurations
            connect: List of connection configurations
            contributors: List of contributor user IDs
            organization_id: ID of organization to create endpoint under (optional).
                            If not provided, endpoint belongs to the authenticated user.

        Returns:
            The created Endpoint

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If data is invalid
        """
        vis_value = (
            visibility.value if isinstance(visibility, Visibility) else visibility
        )
        type_value = type.value if isinstance(type, EndpointType) else type

        payload: dict[str, Any] = {
            "name": name,
            "type": type_value,
            "visibility": vis_value,
            "description": description,
            "version": version,
            "readme": readme,
        }

        if slug is not None:
            payload["slug"] = slug

        if tags is not None:
            payload["tags"] = tags

        if policies is not None:
            payload["policies"] = [
                p.model_dump() if isinstance(p, Policy) else p for p in policies
            ]

        if connect is not None:
            payload["connect"] = [
                c.model_dump() if isinstance(c, Connection) else c for c in connect
            ]

        if contributors is not None:
            payload["contributors"] = contributors

        if organization_id is not None:
            payload["organization_id"] = organization_id

        response = self._http.post("/api/v1/endpoints", json=payload)
        data = response if isinstance(response, dict) else {}
        return Endpoint.model_validate(data)

    def get(self, path: str) -> Endpoint:
        """Get a specific endpoint by path.

        Args:
            path: Endpoint path in "owner/slug" format (e.g., "alice/my-api")

        Returns:
            The Endpoint

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
            AuthorizationError: If not authorized to view
            ValueError: If path format is invalid
        """
        from syfthub_sdk.exceptions import NotFoundError

        owner, slug = self._parse_path(path)

        # Search user's own endpoints by slug
        # /api/v1/endpoints returns EndpointResponse with full details including id
        response = self._http.get("/api/v1/endpoints", params={"limit": 100})
        endpoints = response if isinstance(response, list) else []

        for ep in endpoints:
            if ep.get("slug") == slug:
                return Endpoint.model_validate(ep)

        raise NotFoundError(
            message=f"Endpoint not found: '{path}'",
            detail=f"No endpoint found with slug '{slug}' in your endpoints.",
        )

    def update(
        self,
        path: str,
        *,
        name: str | None = None,
        visibility: Visibility | str | None = None,
        description: str | None = None,
        version: str | None = None,
        readme: str | None = None,
        tags: builtins.list[str] | None = None,
        policies: builtins.list[Policy] | builtins.list[dict[str, Any]] | None = None,
        connect: builtins.list[Connection]
        | builtins.list[dict[str, Any]]
        | None = None,
        contributors: builtins.list[int] | None = None,
    ) -> Endpoint:
        """Update an endpoint.

        Only provided fields will be updated.

        Args:
            path: Endpoint path in "owner/slug" format (e.g., "alice/my-api")
            name: New display name
            visibility: New visibility setting
            description: New description
            version: New version
            readme: New README content
            tags: New tags for categorization
            policies: New policy configurations
            connect: New connection configurations
            contributors: New contributor user IDs

        Returns:
            The updated Endpoint

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
            AuthorizationError: If not owner/admin
            ValueError: If path format is invalid
        """
        _owner, slug = self._parse_path(path)

        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if visibility is not None:
            payload["visibility"] = (
                visibility.value if isinstance(visibility, Visibility) else visibility
            )
        if description is not None:
            payload["description"] = description
        if version is not None:
            payload["version"] = version
        if readme is not None:
            payload["readme"] = readme
        if tags is not None:
            payload["tags"] = tags
        if policies is not None:
            payload["policies"] = [
                p.model_dump() if isinstance(p, Policy) else p for p in policies
            ]
        if connect is not None:
            payload["connect"] = [
                c.model_dump() if isinstance(c, Connection) else c for c in connect
            ]
        if contributors is not None:
            payload["contributors"] = contributors

        # Use slug-based endpoint directly instead of resolving ID
        response = self._http.patch(f"/api/v1/endpoints/slug/{slug}", json=payload)
        data = response if isinstance(response, dict) else {}
        return Endpoint.model_validate(data)

    def delete(self, path: str) -> None:
        """Delete an endpoint.

        Args:
            path: Endpoint path in "owner/slug" format (e.g., "alice/my-api")

        Raises:
            AuthenticationError: If not authenticated
            NotFoundError: If endpoint not found
            AuthorizationError: If not owner/admin
            ValueError: If path format is invalid
        """
        _owner, slug = self._parse_path(path)
        # Use slug-based endpoint directly instead of resolving ID
        self._http.delete(f"/api/v1/endpoints/slug/{slug}")

    def sync(
        self,
        endpoints: builtins.list[dict[str, Any]] | None = None,
    ) -> SyncEndpointsResponse:
        """Synchronize user's endpoints with provided list.

        This is a DESTRUCTIVE operation that:
        1. Deletes ALL existing endpoints owned by the current user
        2. Creates ALL endpoints from the provided list
        3. Is ATOMIC: either all endpoints sync successfully, or none do

        Important Notes:
        - Organization endpoints are NOT affected
        - Stars on existing endpoints will be lost (reset to 0)
        - Endpoint IDs will change (new IDs assigned)
        - Maximum 100 endpoints per sync request

        Args:
            endpoints: List of endpoint specifications to sync. Each dict should contain
                      the same fields as create() (name, type, visibility, etc.).
                      Pass an empty list or None to delete ALL user endpoints.

        Returns:
            SyncEndpointsResponse with synced count, deleted count, and created endpoints

        Raises:
            AuthenticationError: If not authenticated
            ValidationError: If any endpoint fails validation (entire batch rejected)

        Example:
            # Sync with new endpoints
            result = client.my_endpoints.sync([
                {"name": "Model A", "type": "model", "visibility": "public"},
                {"name": "Data Source B", "type": "data_source", "visibility": "private"},
            ])
            print(f"Deleted {result.deleted}, created {result.synced} endpoints")

            # Clear all endpoints
            result = client.my_endpoints.sync([])
            print(f"Deleted {result.deleted} endpoints")
        """
        payload: dict[str, Any] = {"endpoints": endpoints or []}

        response = self._http.post("/api/v1/endpoints/sync", json=payload)
        data = response if isinstance(response, dict) else {}
        return SyncEndpointsResponse.model_validate(data)
