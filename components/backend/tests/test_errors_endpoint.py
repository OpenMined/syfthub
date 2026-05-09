"""Tests for error reporting endpoints."""

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app


@pytest.fixture
def client():
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    client = TestClient(app)
    yield client
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth():
    token_blacklist.clear()


@pytest.fixture
def user_token(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "erroruser",
            "email": "erroruser@example.com",
            "full_name": "Error User",
            "password": "testpass123",
        },
    )
    return response.json()["access_token"]


class TestServiceErrorReport:
    def test_report_service_error_success(self, client):
        response = client.post(
            "/api/v1/errors/service-report",
            json={
                "service": "aggregator",
                "event": "model.query.failed",
                "message": "Query timed out",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "correlation_id" in data

    def test_report_service_error_with_all_fields(self, client):
        response = client.post(
            "/api/v1/errors/service-report",
            json={
                "correlation_id": "test-corr-id",
                "service": "mcp",
                "level": "WARNING",
                "event": "mcp.tool.failed",
                "message": "Tool execution failed",
                "endpoint": "https://example.com/endpoint",
                "method": "POST",
                "error_type": "TimeoutError",
                "error_code": "504",
                "stack_trace": "Traceback ...",
                "context": {"key": "value"},
                "request_data": {"req": "data"},
                "response_data": {"resp": "data"},
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["correlation_id"] == "test-corr-id"


class TestFrontendErrorReport:
    def test_report_frontend_error_unauthenticated(self, client):
        response = client.post(
            "/api/v1/errors/report",
            json={
                "event": "frontend.error.unhandled",
                "message": "Something went wrong",
                "error": {
                    "type": "TypeError",
                    "message": "Cannot read property",
                },
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "correlation_id" in data

    def test_report_frontend_error_authenticated(self, client, user_token):
        response = client.post(
            "/api/v1/errors/report",
            json={
                "event": "frontend.error.unhandled",
                "message": "Something went wrong",
                "error": {
                    "type": "TypeError",
                    "message": "null is not an object",
                    "stack_trace": "at Component.render ...",
                    "component_stack": "in Component",
                },
                "context": {
                    "url": "https://app.example.com/browse",
                    "user_agent": "Mozilla/5.0",
                    "app_state": {"page": "browse"},
                },
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 202

    def test_report_frontend_error_with_correlation_id(self, client):
        response = client.post(
            "/api/v1/errors/report",
            json={
                "correlation_id": "my-corr-id",
                "event": "frontend.error.unhandled",
                "message": "Error occurred",
                "error": {"type": "ReferenceError"},
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["correlation_id"] == "my-corr-id"
