"""Tests for archived endpoint behaviour on the proxy route.

Covers:
- POST /{owner}/{slug} returns 403 when endpoint is archived
- POST /{owner}/{slug} proceeds normally when endpoint is NOT archived
- GET /{owner}/{slug} still works for archived endpoints (browse is allowed)
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.main import app
from syfthub.schemas.auth import UserRole
from syfthub.schemas.endpoint import Endpoint, EndpointType, EndpointVisibility
from syfthub.schemas.user import User


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Create a test user with a domain configured."""
    return User(
        id=1,
        username="testowner",
        email="owner@example.com",
        full_name="Test Owner",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        domain="https://syftai-space:8080",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_endpoint(*, archived: bool = False, **overrides) -> Endpoint:
    """Build an Endpoint with sensible defaults; override any field via kwargs."""
    now = datetime.now(timezone.utc)
    defaults = {
        "id": 101,
        "user_id": 1,
        "name": "Test Model",
        "slug": "test-model",
        "description": "A test model endpoint",
        "type": EndpointType.MODEL,
        "visibility": EndpointVisibility.PUBLIC,
        "is_active": True,
        "archived": archived,
        "contributors": [],
        "version": "1.0.0",
        "readme": "",
        "tags": [],
        "stars_count": 0,
        "policies": [],
        "connect": [
            {
                "type": "http",
                "enabled": True,
                "description": "HTTP connection",
                "config": {"url": ""},
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Endpoint(**defaults)


class TestInvokeArchivedEndpoint:
    """Tests for the archived guard on POST /{owner_slug}/{endpoint_slug}."""

    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_archived_endpoint_returns_403(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        client,
        mock_user,
    ):
        """POST to an archived endpoint returns 403 Forbidden."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = _make_endpoint(archived=True)

        response = client.post(
            "/testowner/test-model",
            json={"user_email": "test@example.com"},
        )

        assert response.status_code == 403

    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_archived_endpoint_detail_message(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        client,
        mock_user,
    ):
        """403 response detail explains the endpoint is archived."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = _make_endpoint(archived=True)

        response = client.post(
            "/testowner/test-model",
            json={"user_email": "test@example.com"},
        )

        detail = response.json()["detail"]
        assert "archived" in detail.lower()
        assert "cannot be invoked" in detail.lower()

    @patch("syfthub.main.validate_domain_for_ssrf")
    @patch("syfthub.main.httpx.AsyncClient")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_invoke_non_archived_endpoint_passes_archived_check(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_async_client,
        mock_ssrf_check,
        client,
        mock_user,
    ):
        """POST to a non-archived endpoint is not blocked by the archived guard.

        The request should proceed past the archived check and reach downstream
        logic (here simulated via a successful proxy response).
        """
        from unittest.mock import AsyncMock

        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = _make_endpoint(archived=False)

        # Setup a successful proxy response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        response = client.post(
            "/testowner/test-model",
            json={"user_email": "test@example.com"},
        )

        # Should NOT be 403; the request passes the archived check
        assert response.status_code != 403


class TestGetArchivedEndpoint:
    """Verify GET /{owner_slug}/{endpoint_slug} still works for archived endpoints.

    Archived endpoints are only blocked from invocation (POST). Browsing (GET)
    must continue to work so users can read the README, see the description, etc.
    """

    @patch("syfthub.main.can_access_endpoint_with_org")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_get_archived_endpoint_returns_200(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_can_access,
        client,
        mock_user,
    ):
        """GET on an archived endpoint returns 200 (not blocked)."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = _make_endpoint(archived=True)
        mock_can_access.return_value = True

        response = client.get(
            "/testowner/test-model",
            headers={"Accept": "application/json"},
        )

        # The response should succeed (200), proving archived does not block GET
        assert response.status_code == 200

    @patch("syfthub.main.can_access_endpoint_with_org")
    @patch("syfthub.main.get_endpoint_by_owner_and_slug")
    @patch("syfthub.main.resolve_owner")
    @patch("syfthub.main.get_optional_current_user")
    def test_get_archived_endpoint_includes_archived_field(
        self,
        mock_get_user,
        mock_resolve,
        mock_get_endpoint,
        mock_can_access,
        client,
        mock_user,
    ):
        """GET response for an archived endpoint includes archived=True."""
        mock_get_user.return_value = None
        mock_resolve.return_value = (mock_user, "user")
        mock_get_endpoint.return_value = _make_endpoint(archived=True)
        mock_can_access.return_value = True

        response = client.get(
            "/testowner/test-model",
            headers={"Accept": "application/json"},
        )

        data = response.json()
        assert data["archived"] is True
