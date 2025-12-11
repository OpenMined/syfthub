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
    """Test the readiness endpoint returns a status."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    # SyftHub may not be available in tests, so just check structure
    assert "syfthub" in data["checks"]
