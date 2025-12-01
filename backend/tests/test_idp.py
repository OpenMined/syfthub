"""Integration tests for Identity Provider (IdP) endpoints.

Tests the JWKS and token minting endpoints end-to-end,
including authentication and error handling.
"""

from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.auth.keys import RSAKeyManager
from syfthub.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_key_manager():
    """Reset key manager before each test."""
    RSAKeyManager._instance = None
    yield
    RSAKeyManager._instance = None
    # Clear dependency overrides after each test
    app.dependency_overrides.clear()


@pytest.fixture
def configured_key_manager():
    """Create and configure a key manager for tests."""
    RSAKeyManager._instance = None
    manager = RSAKeyManager()
    manager._generate_keypair("test-integration-key")
    return manager


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = 123
    user.username = "testuser"
    user.role = "user"
    user.is_active = True
    return user


@pytest.fixture
def authenticated_client(client, mock_user):
    """Create a test client with authentication overridden."""
    app.dependency_overrides[get_current_active_user] = lambda: mock_user
    yield client
    app.dependency_overrides.clear()


class TestJWKSEndpoint:
    """Tests for the /.well-known/jwks.json endpoint."""

    def test_jwks_publicly_accessible(self, client, configured_key_manager):
        """Test that JWKS endpoint is accessible without authentication."""
        with patch("syfthub.main.key_manager", configured_key_manager):
            response = client.get("/.well-known/jwks.json")
            assert response.status_code == 200

    def test_jwks_response_format(self, client, configured_key_manager):
        """Test that JWKS response matches expected format."""
        with patch("syfthub.main.key_manager", configured_key_manager):
            response = client.get("/.well-known/jwks.json")

            assert response.status_code == 200

            data = response.json()
            assert "keys" in data
            assert len(data["keys"]) >= 1

            key = data["keys"][0]
            assert key["kty"] == "RSA"
            assert key["kid"] == "test-integration-key"
            assert key["use"] == "sig"
            assert key["alg"] == "RS256"
            assert "n" in key
            assert "e" in key

    def test_jwks_cache_headers(self, client, configured_key_manager):
        """Test that JWKS response includes cache headers."""
        with patch("syfthub.main.key_manager", configured_key_manager):
            response = client.get("/.well-known/jwks.json")

            assert response.status_code == 200
            assert "Cache-Control" in response.headers
            assert "max-age" in response.headers["Cache-Control"]

    def test_jwks_not_configured(self, client):
        """Test JWKS returns 503 when keys not configured."""
        unconfigured_manager = RSAKeyManager()
        # Don't initialize - leave unconfigured

        with patch("syfthub.main.key_manager", unconfigured_manager):
            response = client.get("/.well-known/jwks.json")
            assert response.status_code == 503


class TestTokenEndpoint:
    """Tests for the /api/v1/token endpoint."""

    def test_token_requires_authentication(self, client, configured_key_manager):
        """Test that token endpoint requires Hub session token."""
        with patch("syfthub.api.endpoints.token.key_manager", configured_key_manager):
            response = client.get("/api/v1/token?aud=syftai-space")
            # Should return 401 without auth
            assert response.status_code == 401

    def test_token_requires_aud_parameter(
        self, authenticated_client, configured_key_manager
    ):
        """Test that token endpoint requires aud parameter."""
        with patch("syfthub.api.endpoints.token.key_manager", configured_key_manager):
            response = authenticated_client.get("/api/v1/token")
            # Should return 422 (validation error) for missing required param
            assert response.status_code == 422

    def test_token_rejects_invalid_audience(
        self, authenticated_client, configured_key_manager
    ):
        """Test that token endpoint rejects unknown audience (FR-06)."""
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.api.endpoints.token.validate_audience", return_value=False),
            patch(
                "syfthub.api.endpoints.token.get_allowed_audiences",
                return_value={"syftai-space"},
            ),
        ):
            response = authenticated_client.get("/api/v1/token?aud=unknown-service")
            assert response.status_code == 400
            data = response.json()
            assert "invalid_audience" in str(data)

    def test_token_endpoint_success(
        self, authenticated_client, configured_key_manager, mock_user
    ):
        """Test successful token generation."""
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.api.endpoints.token.validate_audience", return_value=True),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            response = authenticated_client.get("/api/v1/token?aud=syftai-space")

            assert response.status_code == 200
            data = response.json()
            assert "target_token" in data
            assert len(data["target_token"]) > 0

    def test_token_is_valid_jwt(
        self, authenticated_client, configured_key_manager, mock_user
    ):
        """Test that returned token is a valid JWT."""
        mock_user.id = 456
        mock_user.role = "admin"

        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.api.endpoints.token.validate_audience", return_value=True),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            response = authenticated_client.get("/api/v1/token?aud=syftai-space")

            assert response.status_code == 200
            token = response.json()["target_token"]

            # Verify it's a valid JWT structure
            parts = token.split(".")
            assert len(parts) == 3

            # Decode without verification to check structure
            payload = jwt.decode(token, options={"verify_signature": False})
            assert payload["sub"] == "456"
            assert payload["aud"] == "syftai-space"
            assert payload["role"] == "admin"
            assert "exp" in payload

    def test_token_verifiable_with_public_key(
        self, authenticated_client, configured_key_manager, mock_user
    ):
        """Test that token can be verified using the public key."""
        mock_user.id = 789

        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.api.endpoints.token.validate_audience", return_value=True),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            response = authenticated_client.get("/api/v1/token?aud=syftai-space")
            assert response.status_code == 200
            token = response.json()["target_token"]

            # Verify with public key
            public_key = configured_key_manager.get_public_key("test-integration-key")
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience="syftai-space",
                issuer="https://hub.syft.com",
            )

            assert payload["sub"] == "789"
            assert payload["aud"] == "syftai-space"


class TestTokenAudiencesEndpoint:
    """Tests for the /api/v1/token/audiences endpoint."""

    def test_audiences_requires_auth(self, client, configured_key_manager):
        """Test that audiences endpoint requires authentication."""
        with patch("syfthub.api.endpoints.token.key_manager", configured_key_manager):
            response = client.get("/api/v1/token/audiences")
            assert response.status_code == 401

    def test_audiences_returns_list(self, authenticated_client, configured_key_manager):
        """Test that audiences endpoint returns allowed audiences."""
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch(
                "syfthub.api.endpoints.token.get_allowed_audiences",
                return_value={"syftai-space", "syft-billing"},
            ),
        ):
            response = authenticated_client.get("/api/v1/token/audiences")

            assert response.status_code == 200
            data = response.json()
            assert "allowed_audiences" in data
            assert "idp_configured" in data


class TestTokenVerifyEndpoint:
    """Tests for the /api/v1/verify endpoint."""

    @pytest.fixture
    def mock_service_user(self):
        """Create a mock service user (satellite service account)."""
        service = MagicMock()
        service.id = 999
        service.username = "syftai-space"  # Service username = audience
        service.email = "service@om.org"
        service.role = "service"
        service.is_active = True
        return service

    @pytest.fixture
    def mock_target_user(self):
        """Create a mock user whose token is being verified."""
        user = MagicMock()
        user.id = 123
        user.username = "alice"
        user.email = "alice@om.org"
        user.role = "admin"
        user.is_active = True
        return user

    @pytest.fixture
    def service_authenticated_client(self, client, mock_service_user):
        """Create a test client authenticated as a service."""
        app.dependency_overrides[get_current_active_user] = lambda: mock_service_user
        yield client
        app.dependency_overrides.clear()

    def test_verify_requires_authentication(self, client, configured_key_manager):
        """Test that verify endpoint requires authentication."""
        with patch("syfthub.api.endpoints.token.key_manager", configured_key_manager):
            response = client.post("/api/v1/verify", json={"token": "some-token"})
            assert response.status_code == 401

    def test_verify_success(
        self,
        service_authenticated_client,
        configured_key_manager,
        mock_service_user,
        mock_target_user,
    ):
        """Test successful token verification returns user context."""
        # Create a valid token for the target user
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            from syfthub.auth.satellite_tokens import create_satellite_token

            target_token = create_satellite_token(
                user=mock_target_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

        # Now verify the token
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.issuer_url = "https://hub.syft.com"

            # Mock the user repository
            mock_user_repo = MagicMock()
            mock_user_repo.get_by_id.return_value = mock_target_user

            from syfthub.database.dependencies import get_user_repository

            app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

            response = service_authenticated_client.post(
                "/api/v1/verify", json={"token": target_token}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["sub"] == "123"
            assert data["email"] == "alice@om.org"
            assert data["username"] == "alice"
            assert data["role"] == "admin"
            assert data["aud"] == "syftai-space"
            assert "exp" in data
            assert "iat" in data

        app.dependency_overrides.clear()

    def test_verify_expired_token(
        self,
        service_authenticated_client,
        configured_key_manager,
        mock_service_user,
        mock_target_user,
    ):
        """Test that expired tokens are rejected."""
        # Create a token that's already expired
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = -10  # Already expired

            from syfthub.auth.satellite_tokens import create_satellite_token

            expired_token = create_satellite_token(
                user=mock_target_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

        # Try to verify the expired token
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.issuer_url = "https://hub.syft.com"

            response = service_authenticated_client.post(
                "/api/v1/verify", json={"token": expired_token}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["error"] == "token_expired"

    def test_verify_audience_mismatch(
        self,
        service_authenticated_client,
        configured_key_manager,
        mock_service_user,
        mock_target_user,
    ):
        """Test that tokens for different audiences are rejected."""
        # Create a token for a DIFFERENT audience
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"other-service"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            from syfthub.auth.satellite_tokens import create_satellite_token

            other_audience_token = create_satellite_token(
                user=mock_target_user,
                audience="other-service",
                key_manager=configured_key_manager,
            )

        # Service "syftai-space" tries to verify a token for "other-service"
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.issuer_url = "https://hub.syft.com"

            response = service_authenticated_client.post(
                "/api/v1/verify", json={"token": other_audience_token}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["error"] == "audience_mismatch"
            assert "other-service" in data["message"]
            assert "syftai-space" in data["message"]

    def test_verify_invalid_token_format(
        self,
        service_authenticated_client,
        configured_key_manager,
    ):
        """Test that malformed tokens are rejected."""
        with patch("syfthub.api.endpoints.token.key_manager", configured_key_manager):
            response = service_authenticated_client.post(
                "/api/v1/verify", json={"token": "not-a-valid-jwt"}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["error"] == "invalid_token_format"

    def test_verify_user_not_found(
        self,
        service_authenticated_client,
        configured_key_manager,
        mock_service_user,
        mock_target_user,
    ):
        """Test verification when user no longer exists."""
        # Create a valid token
        with patch("syfthub.auth.satellite_tokens.settings") as mock_settings:
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60

            from syfthub.auth.satellite_tokens import create_satellite_token

            target_token = create_satellite_token(
                user=mock_target_user,
                audience="syftai-space",
                key_manager=configured_key_manager,
            )

        # Mock user repo to return None (user deleted)
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
        ):
            mock_settings.issuer_url = "https://hub.syft.com"

            mock_user_repo = MagicMock()
            mock_user_repo.get_by_id.return_value = None  # User not found

            from syfthub.database.dependencies import get_user_repository

            app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

            response = service_authenticated_client.post(
                "/api/v1/verify", json={"token": target_token}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is False
            assert data["error"] == "user_not_found"

        app.dependency_overrides.clear()

    def test_verify_returns_expires_in(
        self, authenticated_client, configured_key_manager, mock_user
    ):
        """Test that token endpoint now returns expires_in."""
        with (
            patch("syfthub.api.endpoints.token.key_manager", configured_key_manager),
            patch("syfthub.api.endpoints.token.validate_audience", return_value=True),
            patch("syfthub.auth.satellite_tokens.settings") as mock_settings,
            patch("syfthub.api.endpoints.token.settings") as endpoint_settings,
        ):
            mock_settings.allowed_audiences = {"syftai-space"}
            mock_settings.issuer_url = "https://hub.syft.com"
            mock_settings.satellite_token_expire_seconds = 60
            endpoint_settings.satellite_token_expire_seconds = 60

            response = authenticated_client.get("/api/v1/token?aud=syftai-space")

            assert response.status_code == 200
            data = response.json()
            assert "target_token" in data
            assert "expires_in" in data
            assert data["expires_in"] == 60
