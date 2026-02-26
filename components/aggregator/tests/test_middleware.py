"""Tests for RequestLoggingMiddleware URL, header, and body logging."""

from __future__ import annotations

import json
from typing import Any

import structlog.testing
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from aggregator.observability.constants import REDACTED_VALUE, LogEvents
from aggregator.observability.middleware import RequestLoggingMiddleware


def make_app(
    log_request_headers: bool = False,
    log_request_body: bool = False,
    exclude_paths: set[str] | None = None,
) -> FastAPI:
    """Build a minimal FastAPI app with RequestLoggingMiddleware for testing."""
    test_app = FastAPI()
    test_app.add_middleware(
        RequestLoggingMiddleware,
        log_request_headers=log_request_headers,
        log_request_body=log_request_body,
        exclude_paths=exclude_paths if exclude_paths is not None else {"/health"},
    )

    @test_app.get("/test")
    async def test_get() -> dict[str, Any]:
        return {"ok": True}

    @test_app.post("/test")
    async def test_post(request: Request) -> dict[str, Any]:
        # Read body in the handler to verify stream was not consumed by middleware
        body = await request.body()
        return {"body": body.decode()}

    @test_app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    return test_app


def _get_started_log(logs: list[dict[str, Any]]) -> dict[str, Any]:
    started = [log for log in logs if log.get("event") == LogEvents.REQUEST_STARTED]
    assert len(started) == 1, f"Expected 1 {LogEvents.REQUEST_STARTED!r} entry, got {len(started)}"
    return started[0]


def test_url_field_always_present() -> None:
    client = TestClient(make_app())
    with structlog.testing.capture_logs() as logs:
        client.get("/test")
    log = _get_started_log(logs)
    assert "url" in log
    assert "/test" in log["url"]


def test_url_field_contains_full_url() -> None:
    client = TestClient(make_app())
    with structlog.testing.capture_logs() as logs:
        client.get("/test?foo=bar")
    log = _get_started_log(logs)
    assert "foo=bar" in log["url"]


def test_path_field_preserved_for_backward_compat() -> None:
    client = TestClient(make_app())
    with structlog.testing.capture_logs() as logs:
        client.get("/test")
    log = _get_started_log(logs)
    assert log["path"] == "/test"


def test_headers_logged_when_enabled() -> None:
    client = TestClient(make_app(log_request_headers=True))
    with structlog.testing.capture_logs() as logs:
        client.get("/test", headers={"X-Custom": "myvalue"})
    log = _get_started_log(logs)
    assert "headers" in log
    assert log["headers"].get("x-custom") == "myvalue"


def test_authorization_header_redacted() -> None:
    client = TestClient(make_app(log_request_headers=True))
    with structlog.testing.capture_logs() as logs:
        client.get("/test", headers={"Authorization": "Bearer secret123"})
    log = _get_started_log(logs)
    assert log["headers"]["authorization"] == REDACTED_VALUE


def test_headers_not_logged_when_disabled() -> None:
    client = TestClient(make_app(log_request_headers=False))
    with structlog.testing.capture_logs() as logs:
        client.get("/test", headers={"Authorization": "Bearer secret123"})
    log = _get_started_log(logs)
    assert "headers" not in log


def test_json_body_logged_when_enabled() -> None:
    client = TestClient(make_app(log_request_body=True))
    with structlog.testing.capture_logs() as logs:
        client.post("/test", json={"name": "test"})
    log = _get_started_log(logs)
    assert "body" in log
    assert log["body"] == {"name": "test"}


def test_body_sensitive_fields_sanitized() -> None:
    client = TestClient(make_app(log_request_body=True))
    with structlog.testing.capture_logs() as logs:
        client.post("/test", json={"username": "alice", "password": "secret"})
    log = _get_started_log(logs)
    assert log["body"]["password"] == REDACTED_VALUE
    assert log["body"]["username"] == "alice"


def test_large_body_truncated() -> None:
    client = TestClient(make_app(log_request_body=True))
    long_value = "x" * 1500
    with structlog.testing.capture_logs() as logs:
        client.post("/test", json={"data": long_value})
    log = _get_started_log(logs)
    body_data = log["body"]["data"]
    assert "truncated" in body_data
    assert len(body_data) < len(long_value)


def test_body_not_logged_when_disabled() -> None:
    client = TestClient(make_app(log_request_body=False))
    with structlog.testing.capture_logs() as logs:
        client.post("/test", json={"name": "test"})
    log = _get_started_log(logs)
    assert "body" not in log


def test_body_available_to_downstream_handler() -> None:
    """Reading body in middleware must not consume the stream for downstream handlers."""
    client = TestClient(make_app(log_request_body=True))
    payload = {"message": "hello"}
    response = client.post("/test", json=payload)
    assert response.status_code == 200
    echoed = json.loads(response.json()["body"])
    assert echoed == payload


def test_excluded_path_skips_logging() -> None:
    client = TestClient(make_app())
    with structlog.testing.capture_logs() as logs:
        client.get("/health")
    started = [log for log in logs if log.get("event") == LogEvents.REQUEST_STARTED]
    assert len(started) == 0
