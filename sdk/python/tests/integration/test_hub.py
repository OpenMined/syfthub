"""Integration tests for hub (public endpoint browsing)."""

from __future__ import annotations

from typing import Any

import pytest

from syfthub_sdk import EndpointPublic, SyftHubClient
from syfthub_sdk.exceptions import AuthenticationError, NotFoundError


class TestBrowse:
    """Tests for browsing public endpoints."""

    def test_browse_returns_public_endpoints(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test browsing returns public endpoints."""
        # created_endpoint fixture ensures there's at least one public endpoint
        _ = created_endpoint  # Ensure endpoint exists
        endpoints = client.hub.browse().first_page()

        assert isinstance(endpoints, list)
        # Each should be an EndpointPublic
        for ep in endpoints:
            assert isinstance(ep, EndpointPublic)

    def test_browse_no_auth_required(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test browsing works without authentication."""
        assert client.is_authenticated is False

        # Should not raise
        endpoints = client.hub.browse().first_page()
        assert isinstance(endpoints, list)

    def test_browse_pagination(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test browse pagination works."""
        # Just verify pagination doesn't error
        iterator = client.hub.browse(page_size=5)

        first_page = iterator.first_page()
        assert len(first_page) <= 5

    def test_browse_includes_created_public_endpoint(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
    ) -> None:
        """Test browsing includes newly created public endpoint."""
        endpoint = created_endpoint["endpoint"]

        # Browse all public endpoints
        all_public = client.hub.browse().all()

        # Our endpoint should be in there (it's public)
        slugs = [ep.slug for ep in all_public]
        assert endpoint.slug in slugs


class TestTrending:
    """Tests for trending endpoints."""

    def test_trending_returns_endpoints(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test trending returns endpoints sorted by stars."""
        endpoints = client.hub.trending().first_page()

        assert isinstance(endpoints, list)
        for ep in endpoints:
            assert isinstance(ep, EndpointPublic)

    def test_trending_no_auth_required(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test trending works without auth."""
        assert client.is_authenticated is False

        endpoints = client.hub.trending().first_page()
        assert isinstance(endpoints, list)

    def test_trending_with_min_stars(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test filtering by minimum stars."""
        # Filter by min_stars (might return empty if no starred endpoints)
        endpoints = client.hub.trending(min_stars=1).first_page()

        # All returned should have at least 1 star
        for ep in endpoints:
            assert ep.stars_count >= 1


class TestGetByPath:
    """Tests for getting endpoint by path."""

    def test_get_by_path(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test getting endpoint by owner/slug path."""
        endpoint = created_endpoint["endpoint"]
        username = registered_user["username"]
        path = f"{username}/{endpoint.slug}"

        result = client.hub.get(path)

        assert isinstance(result, EndpointPublic)
        assert result.slug == endpoint.slug
        assert result.name == endpoint.name

    def test_get_by_path_with_owner_username(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test path resolution includes owner_username."""
        endpoint = created_endpoint["endpoint"]
        username = registered_user["username"]
        path = f"{username}/{endpoint.slug}"

        result = client.hub.get(path)

        assert result.owner_username == username

    def test_get_nonexistent_path_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test getting nonexistent path fails."""
        with pytest.raises(NotFoundError):
            client.hub.get("nonexistent_user/nonexistent_endpoint")

    def test_get_invalid_path_format_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test invalid path format raises error."""
        with pytest.raises(ValueError):
            client.hub.get("invalid-path-without-slash")

        with pytest.raises(ValueError):
            client.hub.get("too/many/slashes")

    def test_get_path_property(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test EndpointPublic.path property."""
        endpoint = created_endpoint["endpoint"]
        username = registered_user["username"]
        path = f"{username}/{endpoint.slug}"

        result = client.hub.get(path)

        assert result.path == path


class TestStarring:
    """Tests for starring endpoints.

    Note: These tests are currently skipped because the backend doesn't expose
    the endpoint ID in the public response, which is required for starring.
    Once the backend is updated to include the ID, these tests can be enabled.
    """

    @pytest.mark.skip(reason="Backend doesn't expose endpoint ID in public response")
    def test_star_endpoint(
        self,
        second_authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test starring an endpoint."""
        endpoint = created_endpoint["endpoint"]
        path = f"{registered_user['username']}/{endpoint.slug}"

        # Second user stars the endpoint
        second_authenticated_client.hub.star(path)

        # Verify is_starred
        assert second_authenticated_client.hub.is_starred(path) is True

    @pytest.mark.skip(reason="Backend doesn't expose endpoint ID in public response")
    def test_unstar_endpoint(
        self,
        second_authenticated_client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test unstarring an endpoint."""
        endpoint = created_endpoint["endpoint"]
        path = f"{registered_user['username']}/{endpoint.slug}"

        # Star first
        second_authenticated_client.hub.star(path)
        assert second_authenticated_client.hub.is_starred(path) is True

        # Unstar
        second_authenticated_client.hub.unstar(path)
        assert second_authenticated_client.hub.is_starred(path) is False

    @pytest.mark.skip(reason="Backend doesn't expose endpoint ID in public response")
    def test_star_without_auth_fails(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test starring without auth fails."""
        endpoint = created_endpoint["endpoint"]
        path = f"{registered_user['username']}/{endpoint.slug}"

        with pytest.raises(AuthenticationError):
            client.hub.star(path)

    @pytest.mark.skip(reason="Backend doesn't expose endpoint ID in public response")
    def test_is_starred_without_auth_fails(
        self,
        client: SyftHubClient,
        created_endpoint: dict[str, Any],
        registered_user: dict[str, str],
    ) -> None:
        """Test checking starred status without auth fails."""
        endpoint = created_endpoint["endpoint"]
        path = f"{registered_user['username']}/{endpoint.slug}"

        with pytest.raises(AuthenticationError):
            client.hub.is_starred(path)

    @pytest.mark.skip(reason="Backend doesn't expose endpoint ID in public response")
    def test_star_nonexistent_endpoint_fails(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test starring nonexistent endpoint fails."""
        with pytest.raises((NotFoundError, ValueError)):
            authenticated_client.hub.star("nonexistent/endpoint")


class TestPrivateEndpoints:
    """Tests for private endpoint visibility in hub."""

    def test_private_endpoint_not_in_browse(
        self,
        authenticated_client: SyftHubClient,
        client: SyftHubClient,
        unique_id: str,
    ) -> None:
        """Test private endpoints don't appear in browse."""
        # Create a private endpoint
        private_ep = authenticated_client.my_endpoints.create(
            name=f"Private Test {unique_id}",
            visibility="private",
        )

        try:
            # Browse as unauthenticated user
            all_public = client.hub.browse().all()
            slugs = [ep.slug for ep in all_public]

            # Private endpoint should NOT be in browse
            assert private_ep.slug not in slugs

        finally:
            authenticated_client.my_endpoints.delete(endpoint_id=private_ep.id)

    def test_private_endpoint_not_accessible_by_path(
        self,
        authenticated_client: SyftHubClient,
        client: SyftHubClient,
        registered_user: dict[str, str],
        unique_id: str,
    ) -> None:
        """Test private endpoints can't be accessed by path by others."""
        # Create a private endpoint
        private_ep = authenticated_client.my_endpoints.create(
            name=f"Private Path Test {unique_id}",
            visibility="private",
        )
        path = f"{registered_user['username']}/{private_ep.slug}"

        try:
            # Try to access as unauthenticated user
            # Backend may return 401 (need auth) or 404 (not found/hidden)
            with pytest.raises((NotFoundError, AuthenticationError)):
                client.hub.get(path)

        finally:
            authenticated_client.my_endpoints.delete(endpoint_id=private_ep.id)
