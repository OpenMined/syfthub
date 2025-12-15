"""Tests for health endpoints."""

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    """Test the basic health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "syfthub-aggregator"


def test_ready_endpoint_returns_status(client: TestClient) -> None:
    """Test the readiness endpoint returns a status.

    The aggregator is stateless and always ready since all connection
    information (URLs, slugs, tenant names) comes from the request.
    """
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "checks" in data
    # Aggregator is stateless - no external dependencies to check
    assert data["checks"] == {}
