"""Tests for DataSourceClient retry behavior on transient upstream failures.

A hybrid (model_data_source) endpoint runs an LLM generation step as part of
its own /query handling. When that step hits a transient failure (e.g. a
rate-limited provider), the endpoint returns a 5xx — previously this was
reported straight through as "0 documents retrieved" with no retry, unlike
ModelClient which already retried transient 5xx responses. These tests lock
in retry parity between the two clients.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from aggregator.clients import data_source as data_source_module
from aggregator.clients.data_source import DataSourceClient


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real exponential-backoff delays slowing down the test suite."""

    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(data_source_module.asyncio, "sleep", _instant_sleep)


def _make_client(handler: Any) -> DataSourceClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return DataSourceClient(http_client=http_client)


@pytest.mark.asyncio
async def test_retries_transient_500_then_succeeds() -> None:
    """A 500 on the first attempt (e.g. hybrid LLM step rate-limited) is retried."""
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={"detail": "upstream provider rate-limited"})
        return httpx.Response(
            200,
            json={
                "summary": {"model": "gpt-x", "message": {"content": "generated answer"}},
                "references": None,
            },
        )

    client = _make_client(handler)
    result = await client.query(
        url="http://space.example",
        slug="hybrid-endpoint",
        endpoint_path="alice/hybrid-endpoint",
        query="what is the support package?",
    )

    assert calls["count"] == 2
    assert result.status == "success"
    assert len(result.documents) == 1
    assert result.documents[0].content == "generated answer"


@pytest.mark.asyncio
async def test_exhausts_retries_and_reports_error() -> None:
    """A persistently-failing 503 retries MAX_RETRIES times, then reports 'error'."""
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"detail": "service unavailable"})

    client = _make_client(handler)
    result = await client.query(
        url="http://space.example",
        slug="hybrid-endpoint",
        endpoint_path="alice/hybrid-endpoint",
        query="what is the support package?",
    )

    assert calls["count"] == 1 + data_source_module.MAX_RETRIES
    assert result.status == "error"
    assert result.documents == []


@pytest.mark.asyncio
async def test_non_retryable_status_is_not_retried() -> None:
    """A 404 (not in RETRYABLE_STATUS_CODES) fails immediately, no retry."""
    calls = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, json={"detail": "not found"})

    client = _make_client(handler)
    result = await client.query(
        url="http://space.example",
        slug="missing-endpoint",
        endpoint_path="alice/missing-endpoint",
        query="what is the support package?",
    )

    assert calls["count"] == 1
    assert result.status == "error"
