"""Tests for tunnel credentials endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.main import app
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user() -> User:
    """Create a mock authenticated user."""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        full_name="Test User",
        age=30,
        role=UserRole.USER,
        password_hash="hash",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def reset_overrides():
    """Clear dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


class TestGetTunnelCredentials:
    """Tests for GET /users/me/tunnel-credentials endpoint."""

    @pytest.fixture(autouse=True)
    def setup_http_client(self):
        """Set up mock http_client on app state."""
        mock_client = AsyncMock()
        app.state.http_client = mock_client
        self._mock_http_client = mock_client
        yield
        if hasattr(app.state, "http_client"):
            del app.state.http_client

    @patch("syfthub.api.endpoints.users.settings")
    def test_success(self, mock_settings, client, mock_user):
        """Test successful tunnel credential creation."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "syfthub.ngrok.app"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "cr_test123",
            "token": "ngrok-token-abc123",
            "uri": "https://api.ngrok.com/credentials/cr_test123",
        }
        self._mock_http_client.post.return_value = mock_response

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 200
        data = response.json()
        assert data["auth_token"] == "ngrok-token-abc123"
        assert data["domain"] == "testuser.syfthub.ngrok.app"

    @patch("syfthub.api.endpoints.users.settings")
    def test_ngrok_not_configured(self, mock_settings, client, mock_user):
        """Test 503 when ngrok API key is not set."""
        mock_settings.ngrok_api_key = None

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    @patch("syfthub.api.endpoints.users.settings")
    def test_ngrok_api_error(self, mock_settings, client, mock_user):
        """Test 502 when ngrok API returns non-201 status."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "syfthub.ngrok.app"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error_code": "ERR_NGROK_218"}
        self._mock_http_client.post.return_value = mock_response

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 502
        assert "returned an error" in response.json()["detail"]

    @patch("syfthub.api.endpoints.users.settings")
    def test_ngrok_network_error(self, mock_settings, client, mock_user):
        """Test 502 when ngrok API is unreachable."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "syfthub.ngrok.app"

        self._mock_http_client.post.side_effect = httpx.ConnectError(
            "Connection refused"
        )

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 502
        assert "Failed to connect" in response.json()["detail"]

    @patch("syfthub.api.endpoints.users.settings")
    def test_ngrok_missing_token_in_response(self, mock_settings, client, mock_user):
        """Test 502 when ngrok API returns 201 but no token field."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "syfthub.ngrok.app"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "cr_test123"}  # No token field
        self._mock_http_client.post.return_value = mock_response

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 502
        assert "Unexpected response" in response.json()["detail"]

    def test_unauthenticated(self, client):
        """Test 401 when no auth token is provided."""
        response = client.get("/api/v1/users/me/tunnel-credentials")
        assert response.status_code in (401, 403)

    @patch("syfthub.api.endpoints.users.settings")
    def test_acl_contains_user_domain(self, mock_settings, client, mock_user):
        """Test that the ngrok credential ACL is scoped to the user's domain."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "syfthub.ngrok.app"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"token": "ngrok-token-xyz"}
        self._mock_http_client.post.return_value = mock_response

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        client.get("/api/v1/users/me/tunnel-credentials")

        # Verify the POST call to ngrok includes the correct ACL
        call_kwargs = self._mock_http_client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["acl"] == ["bind:testuser.syfthub.ngrok.app"]

    @patch("syfthub.api.endpoints.users.settings")
    def test_custom_base_domain(self, mock_settings, client, mock_user):
        """Test that a custom ngrok_base_domain is used correctly."""
        mock_settings.ngrok_api_key = "test-ngrok-key"
        mock_settings.ngrok_base_domain = "custom.ngrok.io"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"token": "ngrok-token-custom"}
        self._mock_http_client.post.return_value = mock_response

        app.dependency_overrides[get_current_active_user] = lambda: mock_user
        response = client.get("/api/v1/users/me/tunnel-credentials")

        assert response.status_code == 200
        data = response.json()
        assert data["domain"] == "testuser.custom.ngrok.io"
