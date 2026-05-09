"""
Tests for the transaction-policy MCP integration (plan unit 15).

Covers:
1. ``chat_stream`` raises :class:`PaymentRequiredError` when the aggregator
   emits a ``payment_required`` SSE event.
2. ``chat_with_syfthub`` translates :class:`PaymentRequiredError` into a
   structured, LLM-friendly tool result.
3. ``discover_syfthub_endpoints`` annotates paid endpoints with
   ``payment_required: True`` and a non-null ``pricing_hint``.
4. Non-paid endpoints round-trip with ``payment_required: False`` and
   ``pricing_hint: None``.

Run from the ``components/mcp`` directory::

    uv run pytest -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

import syfthub_client
from syfthub_client import (
    PaymentRequiredError,
    SyftHubClient,
    _build_payment_required_error,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PAYMENT_EVENT_DATA = {
    "chat_session_id": "sess-abc",
    "endpoint_slug": "alice/paid-model",
    "challenge": "Payment id=ch-1, amount=0.10, currency=PathUSD",
    "amount": "0.10",
    "currency": "PathUSD",
    "recipient": "0xRECIPIENT",
    "challenge_id": "ch-1",
    "intent": "charge",
}


def _sse_bytes(events: list[tuple[str, dict]]) -> bytes:
    """Encode a list of (event_name, data_dict) into raw SSE bytes."""
    parts = []
    for name, data in events:
        parts.append(f"event: {name}\n")
        parts.append(f"data: {json.dumps(data)}\n")
        parts.append("\n")
    return "".join(parts).encode("utf-8")


# ---------------------------------------------------------------------------
# Test 1: chat_stream raises PaymentRequiredError on the SSE event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_raises_payment_required():
    """The first ``payment_required`` SSE event must raise the typed error
    with all metadata fields populated, even if other events follow."""
    body = _sse_bytes(
        [
            ("retrieval_start", {"sources": 1}),
            ("payment_required", PAYMENT_EVENT_DATA),
            # This token event must NOT be observed: the stream stops
            # at the first payment_required event.
            ("token", {"content": "should never see this"}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    client = SyftHubClient(base_url="http://aggregator:8001")

    seen_events: list[dict] = []

    real_async_client = httpx.AsyncClient

    def make_async_client(*_args, **_kwargs):
        return real_async_client(transport=transport)

    with patch.object(syfthub_client.httpx, "AsyncClient", side_effect=make_async_client):
        with pytest.raises(PaymentRequiredError) as excinfo:
            async for ev in client.chat_stream(
                aggregator_url="http://aggregator:8001",
                request_body={"prompt": "hi", "model_ref": "alice/paid-model"},
            ):
                seen_events.append(ev)

    err = excinfo.value
    assert err.endpoint_slug == "alice/paid-model"
    assert err.challenge == PAYMENT_EVENT_DATA["challenge"]
    assert err.amount == "0.10"
    assert err.currency == "PathUSD"
    assert err.recipient == "0xRECIPIENT"
    assert err.challenge_id == "ch-1"
    assert err.intent == "charge"

    # Pre-payment events are still streamed; post-payment ones are not.
    assert seen_events == [{"type": "retrieval_start", "data": {"sources": 1}}]

    # to_dict() carries the full payload + a CLI hint for the LLM.
    payload = err.to_dict()
    assert payload["error"] == "payment_required"
    assert payload["amount"] == "0.10"
    assert "syft" in payload["hint"]


@pytest.mark.asyncio
async def test_chat_stream_raises_on_first_of_multiple_payment_events():
    """Multi-endpoint chats may emit several ``payment_required`` events;
    we only need to surface the first to the LLM."""
    second = dict(PAYMENT_EVENT_DATA)
    second["endpoint_slug"] = "bob/other-paid-endpoint"
    second["challenge_id"] = "ch-2"

    body = _sse_bytes(
        [
            ("payment_required", PAYMENT_EVENT_DATA),
            ("payment_required", second),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    client = SyftHubClient(base_url="http://aggregator:8001")

    real_async_client = httpx.AsyncClient

    def make_async_client(*_args, **_kwargs):
        return real_async_client(transport=transport)

    with patch.object(syfthub_client.httpx, "AsyncClient", side_effect=make_async_client):
        with pytest.raises(PaymentRequiredError) as excinfo:
            async for _ in client.chat_stream(
                aggregator_url="http://aggregator:8001",
                request_body={},
            ):
                pass

    # First event wins.
    assert excinfo.value.challenge_id == "ch-1"
    assert excinfo.value.endpoint_slug == "alice/paid-model"


def test_build_payment_required_error_handles_missing_fields():
    """Defensive defaults: empty strings rather than KeyError."""
    err = _build_payment_required_error({"endpoint_slug": "x/y"})
    assert err.endpoint_slug == "x/y"
    assert err.amount == ""
    assert err.currency == ""
    assert err.challenge_id == ""


# ---------------------------------------------------------------------------
# Test 2: chat_with_syfthub returns the friendly structured error
# ---------------------------------------------------------------------------


def _make_payment_required_error() -> PaymentRequiredError:
    return PaymentRequiredError(
        endpoint_slug="alice/paid-model",
        challenge="Payment id=ch-1, amount=0.10",
        amount="0.10",
        currency="PathUSD",
        recipient="0xRECIPIENT",
        challenge_id="ch-1",
        intent="charge",
    )


def test_chat_with_syfthub_returns_friendly_error(monkeypatch):
    """When the underlying SDK call raises ``PaymentRequiredError``, the
    MCP tool must return a structured dict with the amount, recipient,
    and CLI hint formatted for an LLM caller."""
    import server

    # Stub the auth + SDK client plumbing so we exercise only the catch.
    monkeypatch.setattr(server, "SDK_AVAILABLE", True)
    monkeypatch.setattr(
        server, "get_current_user_email", lambda: "alice@example.com"
    )

    fake_client = MagicMock()
    fake_client.chat.complete.side_effect = _make_payment_required_error()
    monkeypatch.setattr(
        server, "get_sdk_client_for_user", lambda email: fake_client
    )

    result = server.chat_with_syfthub(
        prompt="What is 2+2?",
        model="alice/paid-model",
        data_sources=None,
    )

    assert result["success"] is False
    assert result["ok"] is False
    assert result["error_type"] == "payment_required"
    assert result["amount"] == "0.10"
    assert result["currency"] == "PathUSD"
    assert result["recipient"] == "0xRECIPIENT"
    assert result["challenge_id"] == "ch-1"
    assert result["intent"] == "charge"
    assert "syft wallet init" in result["message"]
    assert "alice/paid-model" in result["message"]
    assert "0.10 PathUSD" in result["message"]
    assert "0xRECIPIENT" in result["message"]


# ---------------------------------------------------------------------------
# Test 3: discover_syfthub_endpoints marks paid endpoints
# ---------------------------------------------------------------------------


def _fake_endpoint(
    *,
    slug: str,
    name: str,
    owner: str,
    endpoint_type,
    policies: list,
    has_url: bool = True,
):
    """Build a minimal endpoint object that quacks like an ``EndpointPublic``."""
    conn_config = {"url": "https://example.com"} if has_url else {}
    return SimpleNamespace(
        path=f"{owner}/{slug}",
        name=name,
        slug=slug,
        owner_username=owner,
        description="desc",
        type=endpoint_type,
        connect=[
            SimpleNamespace(enabled=has_url, config=conn_config),
        ],
        policies=policies,
    )


def test_discover_endpoints_marks_paid(monkeypatch):
    """Endpoints with an enabled ``transaction`` policy must be flagged
    as paid in the discovery response."""
    import server
    from syfthub_sdk.models import EndpointType, Policy

    monkeypatch.setattr(server, "SDK_AVAILABLE", True)
    monkeypatch.setattr(
        server, "get_current_user_email", lambda: "alice@example.com"
    )

    txn_policy = Policy(
        type="transaction",
        config={
            "amount": "0.10",
            "currency": "PathUSD",
            "intent": "charge",
            "recipient": "0xRECIPIENT",
        },
    )

    paid = _fake_endpoint(
        slug="paid-model",
        name="Paid Model",
        owner="alice",
        endpoint_type=EndpointType.MODEL,
        policies=[txn_policy],
    )

    fake_client = MagicMock()
    fake_client.hub.browse.return_value = iter([paid])
    monkeypatch.setattr(
        server, "get_sdk_client_for_user", lambda email: fake_client
    )

    result = server.discover_syfthub_endpoints()

    assert result["success"] is True
    models = result["models"]
    assert len(models) == 1
    entry = models[0]
    assert entry["payment_required"] is True
    assert entry["pricing_hint"] == "0.10 PathUSD per call"
    # And the markdown rendering surfaces it
    assert "0.10 PathUSD per call" in result["formatted_output"]


def test_discover_endpoints_normal_endpoint_unaffected(monkeypatch):
    """Endpoints without a transaction policy must be reported as free."""
    import server
    from syfthub_sdk.models import EndpointType

    monkeypatch.setattr(server, "SDK_AVAILABLE", True)
    monkeypatch.setattr(
        server, "get_current_user_email", lambda: "alice@example.com"
    )

    free = _fake_endpoint(
        slug="free-model",
        name="Free Model",
        owner="bob",
        endpoint_type=EndpointType.MODEL,
        policies=[],
    )

    fake_client = MagicMock()
    fake_client.hub.browse.return_value = iter([free])
    monkeypatch.setattr(
        server, "get_sdk_client_for_user", lambda email: fake_client
    )

    result = server.discover_syfthub_endpoints()

    assert result["success"] is True
    entry = result["models"][0]
    assert entry["payment_required"] is False
    assert entry["pricing_hint"] is None
    assert "Free" in result["formatted_output"]


def test_find_transaction_policy_with_dict_input():
    """The helper accepts plain-dict policies (used by the hub raw payload)."""
    from server import _find_transaction_policy, _format_pricing_hint

    policies = [
        {"type": "rate_limit", "enabled": True, "config": {}},
        {
            "type": "transaction",
            "enabled": True,
            "config": {"amount": "5", "currency": "USDC", "intent": "session"},
        },
    ]
    found = _find_transaction_policy(policies)
    assert found is not None
    assert _format_pricing_hint(found) == "5 USDC per session"


def test_find_transaction_policy_skips_disabled():
    from server import _find_transaction_policy

    policies = [
        {
            "type": "transaction",
            "enabled": False,
            "config": {"amount": "1", "currency": "PathUSD"},
        }
    ]
    assert _find_transaction_policy(policies) is None


def test_find_transaction_policy_handles_none_and_empty():
    from server import _find_transaction_policy

    assert _find_transaction_policy(None) is None
    assert _find_transaction_policy([]) is None


def test_format_pricing_hint_returns_none_without_amount():
    from server import _format_pricing_hint

    assert _format_pricing_hint({"config": {"currency": "USD"}}) is None
