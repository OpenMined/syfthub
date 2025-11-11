"""Test main FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Welcome to Syfthub API"
    assert "version" in data
    assert data["docs"] == "/docs"


def test_health_check(client: TestClient) -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_docs_endpoint(client: TestClient) -> None:
    """Test that the docs endpoint is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_endpoint(client: TestClient) -> None:
    """Test that the OpenAPI spec is accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert data["info"]["title"] == "Syfthub API"
