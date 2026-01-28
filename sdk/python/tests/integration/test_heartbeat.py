"""Integration tests for heartbeat functionality."""

from __future__ import annotations

from datetime import datetime

import pytest

from syfthub_sdk import HeartbeatResponse, SyftHubClient
from syfthub_sdk.exceptions import AuthenticationError, ValidationError


class TestHeartbeat:
    """Tests for heartbeat endpoint."""

    def test_send_heartbeat_success(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test sending a heartbeat with valid URL."""
        response = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=300,
        )

        assert isinstance(response, HeartbeatResponse)
        assert response.status == "ok"
        assert response.domain == "myspace.example.com"
        assert response.ttl_seconds <= 600  # Server caps at 600
        assert isinstance(response.received_at, datetime)
        assert isinstance(response.expires_at, datetime)
        assert response.expires_at > response.received_at

    def test_send_heartbeat_with_port(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test sending a heartbeat with URL containing port."""
        response = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com:8080/api/health",
            ttl_seconds=300,
        )

        assert isinstance(response, HeartbeatResponse)
        assert response.status == "ok"
        # Domain should include port but not path
        assert response.domain == "myspace.example.com:8080"

    def test_send_heartbeat_default_ttl(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test sending a heartbeat with default TTL."""
        response = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
        )

        assert isinstance(response, HeartbeatResponse)
        assert response.status == "ok"
        # Default TTL is 300, effective should be <= 600
        assert response.ttl_seconds <= 600

    def test_send_heartbeat_ttl_capped(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test that TTL is capped at server maximum (600 seconds)."""
        response = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=3600,  # Request 1 hour
        )

        assert isinstance(response, HeartbeatResponse)
        # Server should cap at 600 seconds
        assert response.ttl_seconds <= 600

    def test_send_heartbeat_minimum_ttl(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test sending a heartbeat with minimum TTL."""
        response = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=1,
        )

        assert isinstance(response, HeartbeatResponse)
        assert response.ttl_seconds >= 1

    def test_send_heartbeat_without_auth_fails(
        self,
        client: SyftHubClient,
    ) -> None:
        """Test that heartbeat requires authentication."""
        with pytest.raises(AuthenticationError):
            client.users.send_heartbeat(
                url="https://myspace.example.com",
                ttl_seconds=300,
            )

    def test_send_heartbeat_invalid_url(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test that invalid URL is rejected."""
        with pytest.raises(ValidationError):
            authenticated_client.users.send_heartbeat(
                url="not-a-valid-url",
                ttl_seconds=300,
            )

    def test_send_heartbeat_updates_expiry(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test that subsequent heartbeats update the expiry time."""
        # Send first heartbeat
        response1 = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=60,
        )

        # Send second heartbeat
        response2 = authenticated_client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=60,
        )

        assert isinstance(response1, HeartbeatResponse)
        assert isinstance(response2, HeartbeatResponse)
        # Second heartbeat should have a later or equal expiry
        assert response2.expires_at >= response1.expires_at

    def test_send_heartbeat_http_url(
        self,
        authenticated_client: SyftHubClient,
    ) -> None:
        """Test sending a heartbeat with HTTP URL (not HTTPS)."""
        response = authenticated_client.users.send_heartbeat(
            url="http://localhost:8080",
            ttl_seconds=300,
        )

        assert isinstance(response, HeartbeatResponse)
        assert response.status == "ok"
        assert response.domain == "localhost:8080"
