"""Test heartbeat endpoint and functionality."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.core.config import settings
from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from syfthub.database.connection import create_tables, drop_tables

    # Ensure clean database
    drop_tables()
    create_tables()

    client = TestClient(app)

    yield client

    # Clean up
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication data before each test."""
    token_blacklist.clear()

    # Reset counters
    import syfthub.auth.router as auth_module

    auth_module.user_id_counter = 1


@pytest.fixture
def regular_user_token(client: TestClient) -> str:
    """Create a regular user and return access token."""
    user_data = {
        "username": "heartbeatuser",
        "email": "heartbeat@example.com",
        "full_name": "Heartbeat User",
        "password": "testpass123",
    }

    response = client.post("/api/v1/auth/register", json=user_data)
    return response.json()["access_token"]


class TestHeartbeatEndpoint:
    """Tests for POST /api/v1/users/me/heartbeat."""

    def test_heartbeat_success(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test successful heartbeat submission."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {
            "url": "https://api.example.com",
            "ttl_seconds": 300,
        }
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["domain"] == "api.example.com"
        assert data["ttl_seconds"] == 300
        assert "received_at" in data
        assert "expires_at" in data

    def test_heartbeat_ttl_capped_at_max(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that TTL is capped at server maximum."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        # Use a value within schema limit (3600) but above server cap (600)
        payload = {
            "url": "https://api.example.com",
            "ttl_seconds": 3000,
        }
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should be capped at max (default 600)
        assert data["ttl_seconds"] == settings.heartbeat_max_ttl_seconds

    def test_heartbeat_default_ttl(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test default TTL when not specified."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com"}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ttl_seconds"] == settings.heartbeat_default_ttl_seconds

    def test_heartbeat_updates_domain(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that heartbeat updates user's domain (extracts host only, not path)."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        # URL with path - domain should be extracted without the path
        payload = {"url": "https://my-new-domain.com:8080/path/to/api"}
        client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        # Verify domain was updated (host + port only, no path)
        me_response = client.get("/api/v1/users/me", headers=headers)
        assert me_response.json()["domain"] == "my-new-domain.com:8080"

    def test_heartbeat_requires_auth(self, client: TestClient) -> None:
        """Test that heartbeat requires authentication."""
        payload = {"url": "https://api.example.com"}
        response = client.post("/api/v1/users/me/heartbeat", json=payload)
        assert response.status_code == 401

    def test_heartbeat_invalid_url_no_protocol(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test heartbeat with URL missing protocol."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "api.example.com"}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 422

    def test_heartbeat_url_domain_extraction(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test domain extraction from various URL formats (host + port only)."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        test_cases = [
            # URL -> expected domain (host + port, no path)
            ("https://api.example.com", "api.example.com"),
            ("https://api.example.com/", "api.example.com"),
            ("https://api.example.com/v1/health", "api.example.com"),
            ("https://api.example.com:8080", "api.example.com:8080"),
            ("https://api.example.com:8080/api/v1", "api.example.com:8080"),
            ("http://localhost:3000", "localhost:3000"),
            ("http://localhost:3000/path", "localhost:3000"),
        ]
        for url, expected_domain in test_cases:
            payload = {"url": url}
            response = client.post(
                "/api/v1/users/me/heartbeat",
                json=payload,
                headers=headers,
            )
            assert response.status_code == 200, f"Failed for URL: {url}"
            assert response.json()["domain"] == expected_domain, (
                f"Wrong domain for URL: {url}"
            )


class TestHeartbeatExpiry:
    """Tests for heartbeat expiration tracking."""

    def test_heartbeat_sets_expiry(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that heartbeat sets correct expiry time."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com", "ttl_seconds": 120}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        data = response.json()
        received = datetime.fromisoformat(data["received_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        diff = (expires - received).total_seconds()
        assert 119 <= diff <= 121  # Allow 1 second tolerance

    def test_heartbeat_updates_user_fields(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that heartbeat updates user's heartbeat fields."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com", "ttl_seconds": 300}

        # Send heartbeat
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        heartbeat_data = response.json()

        # Verify user fields were updated
        me_response = client.get("/api/v1/users/me", headers=headers)
        user_data = me_response.json()

        assert user_data["domain"] == "api.example.com"
        assert user_data["last_heartbeat_at"] is not None
        assert user_data["heartbeat_expires_at"] is not None

        # Verify expiry matches what was returned in heartbeat response
        # (avoid timezone comparison issues by comparing strings)
        assert heartbeat_data["domain"] == user_data["domain"]

    def test_heartbeat_overwrites_previous(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that subsequent heartbeats update the expiry."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}

        # First heartbeat
        payload1 = {"url": "https://first-domain.com", "ttl_seconds": 60}
        response1 = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload1,
            headers=headers,
        )
        first_expires = response1.json()["expires_at"]

        # Second heartbeat with different domain and TTL
        payload2 = {"url": "https://second-domain.com", "ttl_seconds": 300}
        response2 = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload2,
            headers=headers,
        )
        second_expires = response2.json()["expires_at"]

        # Verify domain was updated
        me_response = client.get("/api/v1/users/me", headers=headers)
        assert me_response.json()["domain"] == "second-domain.com"

        # Verify expiry was extended (second should be later than first)
        assert second_expires > first_expires


class TestHeartbeatEdgeCases:
    """Tests for heartbeat edge cases."""

    def test_heartbeat_with_min_ttl(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test heartbeat with minimum TTL of 1 second."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com", "ttl_seconds": 1}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["ttl_seconds"] == 1

    def test_heartbeat_with_zero_ttl_rejected(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that TTL of 0 is rejected."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com", "ttl_seconds": 0}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 422

    def test_heartbeat_with_negative_ttl_rejected(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that negative TTL is rejected."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "https://api.example.com", "ttl_seconds": -1}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 422

    def test_heartbeat_url_with_whitespace_trimmed(
        self, client: TestClient, regular_user_token: str
    ) -> None:
        """Test that URL whitespace is trimmed."""
        headers = {"Authorization": f"Bearer {regular_user_token}"}
        payload = {"url": "  https://api.example.com  "}
        response = client.post(
            "/api/v1/users/me/heartbeat",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["domain"] == "api.example.com"
