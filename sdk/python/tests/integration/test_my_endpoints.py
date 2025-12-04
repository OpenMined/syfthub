"""Integration tests for user's own endpoints (CRUD)."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from syfthub_sdk import Endpoint, EndpointType, SyftHubClient, Visibility
from syfthub_sdk.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
)


class TestCreateEndpoint:
    """Tests for creating endpoints."""

    def test_create_minimal_endpoint(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test creating an endpoint with minimal required fields."""
        username = registered_user["username"]
        endpoint = authenticated_client.my_endpoints.create(
            name=f"Minimal Endpoint {unique_id}",
            type=EndpointType.MODEL,
        )

        try:
            assert isinstance(endpoint, Endpoint)
            assert endpoint.name == f"Minimal Endpoint {unique_id}"
            assert endpoint.type == EndpointType.MODEL
            assert endpoint.visibility == Visibility.PUBLIC  # Default
            assert endpoint.version == "0.1.0"  # Default
            assert endpoint.id is not None
            assert endpoint.slug is not None
        finally:
            # Cleanup
            authenticated_client.my_endpoints.delete(f"{username}/{endpoint.slug}")

    def test_create_full_endpoint(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test creating an endpoint with all fields."""
        username = registered_user["username"]
        endpoint = authenticated_client.my_endpoints.create(
            name=f"Full Endpoint {unique_id}",
            type="data_source",
            visibility="private",
            description="A fully configured test endpoint",
            slug=f"full-endpoint-{unique_id}",
            version="2.0.0",
            readme="# Full Endpoint\n\nThis is a test.",
            policies=[{"type": "rate-limit", "config": {"max_requests": 100}}],
            connect=[{"type": "http", "config": {"url": "https://api.example.com"}}],
        )

        try:
            assert endpoint.name == f"Full Endpoint {unique_id}"
            assert endpoint.type == EndpointType.DATA_SOURCE
            assert endpoint.visibility == Visibility.PRIVATE
            assert endpoint.description == "A fully configured test endpoint"
            assert endpoint.slug == f"full-endpoint-{unique_id}"
            assert endpoint.version == "2.0.0"
            assert "# Full Endpoint" in endpoint.readme
            assert len(endpoint.policies) == 1
            assert endpoint.policies[0].type == "rate-limit"
            assert len(endpoint.connect) == 1
            assert endpoint.connect[0].type == "http"
        finally:
            authenticated_client.my_endpoints.delete(f"{username}/{endpoint.slug}")

    def test_create_with_visibility_enum(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test creating endpoint with Visibility enum."""
        username = registered_user["username"]
        endpoint = authenticated_client.my_endpoints.create(
            name=f"Internal Endpoint {unique_id}",
            type=EndpointType.MODEL,
            visibility=Visibility.INTERNAL,
        )

        try:
            assert endpoint.visibility == Visibility.INTERNAL
        finally:
            authenticated_client.my_endpoints.delete(f"{username}/{endpoint.slug}")

    def test_create_with_endpoint_type_enum(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test creating endpoint with EndpointType enum."""
        username = registered_user["username"]
        endpoint = authenticated_client.my_endpoints.create(
            name=f"Data Source Endpoint {unique_id}",
            type=EndpointType.DATA_SOURCE,
        )

        try:
            assert endpoint.type == EndpointType.DATA_SOURCE
        finally:
            authenticated_client.my_endpoints.delete(f"{username}/{endpoint.slug}")

    def test_create_without_auth_fails(
        self,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test creating endpoint without auth fails."""
        with pytest.raises(AuthenticationError):
            client.my_endpoints.create(
                name=f"Should Fail {unique_id}",
                type=EndpointType.MODEL,
            )


class TestListEndpoints:
    """Tests for listing user's endpoints."""

    def test_list_empty(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test listing endpoints when user has none."""
        # Note: This might not be empty if fixtures created endpoints
        endpoints = authenticated_client.my_endpoints.list()

        # Just verify it returns a PageIterator that works
        first_page = endpoints.first_page()
        assert isinstance(first_page, list)

    def test_list_with_created_endpoint(
        self,
        authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test listing includes created endpoint."""
        endpoint = created_endpoint["endpoint"]

        endpoints_list = authenticated_client.my_endpoints.list().all()

        # Find our endpoint in the list
        found = any(ep.id == endpoint.id for ep in endpoints_list)
        assert found, "Created endpoint should be in list"

    def test_list_pagination(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test pagination works correctly."""
        username = registered_user["username"]
        # Create a few endpoints
        created_slugs = []
        try:
            for i in range(3):
                ep = authenticated_client.my_endpoints.create(
                    name=f"Pagination Test {unique_id} #{i}",
                    type=EndpointType.MODEL,
                )
                created_slugs.append(ep.slug)

            # List with small page size
            iterator = authenticated_client.my_endpoints.list(page_size=2)

            # Get first page
            first_page = iterator.first_page()
            assert len(first_page) <= 2

            # Get all using iterator
            all_endpoints = authenticated_client.my_endpoints.list(page_size=2).all()
            assert len(all_endpoints) >= 3

        finally:
            # Cleanup
            for slug in created_slugs:
                with contextlib.suppress(Exception):
                    authenticated_client.my_endpoints.delete(f"{username}/{slug}")

    def test_list_take(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test take() method on pagination."""
        username = registered_user["username"]
        # Create endpoints
        created_slugs = []
        try:
            for i in range(3):
                ep = authenticated_client.my_endpoints.create(
                    name=f"Take Test {unique_id} #{i}",
                    type=EndpointType.MODEL,
                )
                created_slugs.append(ep.slug)

            # Take only 2
            endpoints = authenticated_client.my_endpoints.list().take(2)
            assert len(endpoints) == 2

        finally:
            for slug in created_slugs:
                with contextlib.suppress(Exception):
                    authenticated_client.my_endpoints.delete(f"{username}/{slug}")

    def test_list_filter_by_visibility(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test filtering by visibility."""
        username = registered_user["username"]
        # Create public and private endpoints
        public_ep = authenticated_client.my_endpoints.create(
            name=f"Public Filter Test {unique_id}",
            type=EndpointType.MODEL,
            visibility="public",
        )
        private_ep = authenticated_client.my_endpoints.create(
            name=f"Private Filter Test {unique_id}",
            type=EndpointType.DATA_SOURCE,
            visibility="private",
        )

        try:
            # Filter by public
            public_list = authenticated_client.my_endpoints.list(
                visibility="public"
            ).all()
            public_ids = [ep.id for ep in public_list]
            assert public_ep.id in public_ids

            # Filter by private
            private_list = authenticated_client.my_endpoints.list(
                visibility="private"
            ).all()
            private_ids = [ep.id for ep in private_list]
            assert private_ep.id in private_ids

        finally:
            authenticated_client.my_endpoints.delete(f"{username}/{public_ep.slug}")
            authenticated_client.my_endpoints.delete(f"{username}/{private_ep.slug}")

    def test_list_without_auth_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test listing without auth fails."""
        with pytest.raises(AuthenticationError):
            client.my_endpoints.list().first_page()


class TestGetEndpoint:
    """Tests for getting a specific endpoint."""

    def test_get_own_endpoint(
        self,
        authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test getting own endpoint by path."""
        original = created_endpoint["endpoint"]
        path = created_endpoint["path"]

        endpoint = authenticated_client.my_endpoints.get(path)

        assert endpoint.id == original.id
        assert endpoint.name == original.name
        assert endpoint.slug == original.slug

    def test_get_nonexistent_endpoint_fails(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test getting nonexistent endpoint fails."""
        username = registered_user["username"]
        with pytest.raises(NotFoundError):
            authenticated_client.my_endpoints.get(f"{username}/nonexistent-endpoint")

    def test_get_without_auth_fails(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test getting private endpoint without auth fails."""
        # Note: Public endpoints can be accessed without auth via hub,
        # but my_endpoints.get requires auth since it returns full details
        path = created_endpoint["path"]

        # This should fail because unauthenticated users can't get full endpoint details
        with pytest.raises((AuthenticationError, NotFoundError)):
            client.my_endpoints.get(path)


class TestUpdateEndpoint:
    """Tests for updating endpoints."""

    def test_update_name(
        self,
        authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test updating endpoint name."""
        path = created_endpoint["path"]
        new_name = "Updated Name"

        updated = authenticated_client.my_endpoints.update(
            path,
            name=new_name,
        )

        assert updated.name == new_name

    def test_update_multiple_fields(
        self,
        authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test updating multiple fields."""
        path = created_endpoint["path"]

        updated = authenticated_client.my_endpoints.update(
            path,
            description="Updated description",
            version="3.0.0",
            readme="# Updated README",
        )

        assert updated.description == "Updated description"
        assert updated.version == "3.0.0"
        assert "Updated README" in updated.readme

    def test_update_visibility(
        self,
        authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test changing endpoint visibility."""
        path = created_endpoint["path"]

        updated = authenticated_client.my_endpoints.update(
            path,
            visibility=Visibility.PRIVATE,
        )

        assert updated.visibility == Visibility.PRIVATE

    def test_update_nonexistent_fails(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test updating nonexistent endpoint fails."""
        username = registered_user["username"]
        with pytest.raises(NotFoundError):
            authenticated_client.my_endpoints.update(
                f"{username}/nonexistent-endpoint",
                name="Should Fail",
            )

    def test_update_others_endpoint_fails(
        self,
        second_authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test updating another user's endpoint fails."""
        path = created_endpoint["path"]

        with pytest.raises((AuthorizationError, NotFoundError, ValueError)):
            second_authenticated_client.my_endpoints.update(
                path,
                name="Should Fail",
            )


class TestDeleteEndpoint:
    """Tests for deleting endpoints."""

    def test_delete_own_endpoint(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test deleting own endpoint."""
        username = registered_user["username"]
        # Create endpoint to delete
        endpoint = authenticated_client.my_endpoints.create(
            name=f"To Delete {unique_id}",
            type=EndpointType.MODEL,
        )
        path = f"{username}/{endpoint.slug}"

        # Delete it
        authenticated_client.my_endpoints.delete(path)

        # Verify it's gone
        with pytest.raises(NotFoundError):
            authenticated_client.my_endpoints.get(path)

    def test_delete_nonexistent_fails(
        self,
        authenticated_client: SyftHubClient,
        registered_user: dict[str, str],
    ) -> None:
        """Test deleting nonexistent endpoint fails."""
        username = registered_user["username"]
        with pytest.raises(NotFoundError):
            authenticated_client.my_endpoints.delete(f"{username}/nonexistent-endpoint")

    def test_delete_others_endpoint_fails(
        self,
        second_authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test deleting another user's endpoint fails."""
        path = created_endpoint["path"]

        with pytest.raises((AuthorizationError, NotFoundError, ValueError)):
            second_authenticated_client.my_endpoints.delete(path)
