"""Tests for the passthrough PaymentNegotiator."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from aggregator.clients.payment_negotiator import (
    PAYMENT_REQUIRED_ERROR_CODE,
    PaymentNegotiator,
    _extract_challenge,
    _is_payment_required,
)


def _payment_required_response(
    challenge_id: str = "ch_123",
    amount: str = "100",
    currency: str = "0xUSDC",
    recipient: str = "0xMerchant",
    intent: str = "charge",
    challenge: str = "Tempo realm=...",
) -> dict[str, Any]:
    """Build a tunnel response that signals PAYMENT_REQUIRED."""
    return {
        "status": "error",
        "error": {
            "code": PAYMENT_REQUIRED_ERROR_CODE,
            "message": "payment required",
            "details": {
                "payment_challenge": challenge,
                "payment_amount": amount,
                "payment_currency": currency,
                "payment_recipient": recipient,
                "challenge_id": challenge_id,
                "intent": intent,
            },
        },
    }


def _ok_response(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a normal successful tunnel response."""
    return {"status": "ok", "payload": payload or {"result": "hello"}}


async def _wait_for_pending(
    negotiator: PaymentNegotiator,
    keys: list[tuple[str, str]],
    *,
    max_iterations: int = 200,
    poll_interval: float = 0.005,
) -> None:
    """Spin until every key is registered as a pending negotiation, or fail loudly."""
    for _ in range(max_iterations):
        if all(key in negotiator._pending for key in keys):
            return
        await asyncio.sleep(poll_interval)
    raise AssertionError(f"Pending negotiations not registered within timeout: {keys}")


# --- helpers tested in isolation -------------------------------------------------


def test_is_payment_required_true_for_canonical_response() -> None:
    assert _is_payment_required(_payment_required_response()) is True


@pytest.mark.parametrize(
    "response",
    [
        None,
        "not a dict",
        {},
        {"status": "ok"},
        {"status": "error", "error": "not-a-dict"},
        {"status": "error", "error": {"code": "OTHER"}},
    ],
)
def test_is_payment_required_false_for_non_payment_responses(response: Any) -> None:
    assert _is_payment_required(response) is False


def test_extract_challenge_pulls_all_fields() -> None:
    response = _payment_required_response(
        challenge_id="ch_abc",
        amount="42",
        currency="0xC",
        recipient="0xR",
        intent="charge",
        challenge="Tempo realm=foo",
    )
    challenge = _extract_challenge(response, endpoint_slug="my-slug")
    assert challenge.challenge_id == "ch_abc"
    assert challenge.amount == "42"
    assert challenge.currency == "0xC"
    assert challenge.recipient == "0xR"
    assert challenge.intent == "charge"
    assert challenge.challenge == "Tempo realm=foo"
    assert challenge.endpoint_slug == "my-slug"


def test_extract_challenge_raises_when_challenge_id_missing() -> None:
    bad = {"status": "error", "error": {"code": PAYMENT_REQUIRED_ERROR_CODE, "details": {}}}
    with pytest.raises(ValueError):
        _extract_challenge(bad, endpoint_slug="s")


# --- core negotiator behaviour ---------------------------------------------------


async def test_execute_with_payment_no_payment_required_passes_through() -> None:
    """If the first tunnel call returns a normal response, no event is emitted."""
    negotiator = PaymentNegotiator()
    tunnel_call = AsyncMock(return_value=_ok_response())
    emit_event = AsyncMock()

    result = await negotiator.execute_with_payment(
        chat_session_id="session-1",
        endpoint_slug="slug",
        tunnel_call=tunnel_call,
        emit_event=emit_event,
    )

    assert result == _ok_response()
    tunnel_call.assert_awaited_once_with(None)
    emit_event.assert_not_called()


async def test_execute_with_payment_one_round_trip() -> None:
    """First call returns PAYMENT_REQUIRED, event is emitted, credential resumes the call."""
    negotiator = PaymentNegotiator()

    final_response = _ok_response({"result": "paid-and-served"})
    tunnel_call = AsyncMock(side_effect=[_payment_required_response("ch_1"), final_response])
    emit_event = AsyncMock()

    async def submit_after_event() -> None:
        await _wait_for_pending(negotiator, [("session-1", "ch_1")])
        ok = negotiator.submit_credential("session-1", "ch_1", "Payment cred-xyz")
        assert ok is True

    submitter = asyncio.create_task(submit_after_event())
    result = await negotiator.execute_with_payment(
        chat_session_id="session-1",
        endpoint_slug="slug-1",
        tunnel_call=tunnel_call,
        emit_event=emit_event,
        timeout_seconds=2.0,
    )
    await submitter

    assert result == final_response
    # The retry was invoked with the credential.
    assert tunnel_call.await_count == 2
    assert tunnel_call.await_args_list[0].args == (None,)
    assert tunnel_call.await_args_list[1].args == ("Payment cred-xyz",)

    # Event payload contains every required key.
    emit_event.assert_awaited_once()
    call = emit_event.await_args
    assert call is not None
    payload = call.args[0]
    assert payload["event"] == "payment_required"
    data = payload["data"]
    assert data["chat_session_id"] == "session-1"
    assert data["endpoint_slug"] == "slug-1"
    assert data["challenge_id"] == "ch_1"
    assert data["intent"] == "charge"
    for key in ("challenge", "amount", "currency", "recipient"):
        assert key in data


async def test_execute_with_payment_credential_timeout() -> None:
    """If no credential is submitted, asyncio.TimeoutError is raised."""
    negotiator = PaymentNegotiator()
    tunnel_call = AsyncMock(return_value=_payment_required_response("ch_timeout"))
    emit_event = AsyncMock()

    with pytest.raises(asyncio.TimeoutError):
        await negotiator.execute_with_payment(
            chat_session_id="session-t",
            endpoint_slug="slug",
            tunnel_call=tunnel_call,
            emit_event=emit_event,
            timeout_seconds=0.05,
        )

    # The retry was never invoked.
    tunnel_call.assert_awaited_once_with(None)
    # The pending future is cleaned up.
    assert ("session-t", "ch_timeout") not in negotiator._pending


async def test_idempotency_cache_returns_cached_response() -> None:
    """Two execute_with_payment calls with the same challenge_id reuse the cached response."""
    negotiator = PaymentNegotiator()

    final_response = _ok_response({"result": "cached"})
    # First execution: PAYMENT_REQUIRED then success.
    first_tunnel = AsyncMock(side_effect=[_payment_required_response("ch_idem"), final_response])
    emit_event_a = AsyncMock()

    async def submit_for_first() -> None:
        await _wait_for_pending(negotiator, [("session-i", "ch_idem")])
        negotiator.submit_credential("session-i", "ch_idem", "cred")

    submitter = asyncio.create_task(submit_for_first())
    first_result = await negotiator.execute_with_payment(
        chat_session_id="session-i",
        endpoint_slug="slug",
        tunnel_call=first_tunnel,
        emit_event=emit_event_a,
        timeout_seconds=2.0,
    )
    await submitter
    assert first_result == final_response

    # Second execution: same challenge_id, but the cache should short-circuit
    # before any second tunnel call or event emission happens.
    second_tunnel = AsyncMock(return_value=_payment_required_response("ch_idem"))
    emit_event_b = AsyncMock()

    second_result = await negotiator.execute_with_payment(
        chat_session_id="session-i-2",  # different session is fine — cache key is challenge_id
        endpoint_slug="slug",
        tunnel_call=second_tunnel,
        emit_event=emit_event_b,
        timeout_seconds=2.0,
    )

    assert second_result == final_response
    # Second tunnel call was made once (the probe), but never with a credential.
    assert second_tunnel.await_count == 1
    second_tunnel.assert_awaited_once_with(None)
    # No SSE event was emitted on the cached path.
    emit_event_b.assert_not_called()


def test_submit_credential_unknown_session_returns_false() -> None:
    """submit_credential returns False when no future is awaiting the (session, challenge) pair."""
    negotiator = PaymentNegotiator()
    assert negotiator.submit_credential("nope", "also-nope", "cred") is False


async def test_submit_credential_already_done_returns_false() -> None:
    """submit_credential is idempotent — a second submit on the same key returns False."""
    negotiator = PaymentNegotiator()
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
    negotiator._pending[("s", "c")] = future
    future.set_result("already")
    assert negotiator.submit_credential("s", "c", "second") is False


async def test_concurrent_negotiations_isolated() -> None:
    """Two parallel execute_with_payment calls for different challenge_ids both complete."""
    negotiator = PaymentNegotiator()

    final_a = _ok_response({"r": "a"})
    final_b = _ok_response({"r": "b"})

    tunnel_a = AsyncMock(side_effect=[_payment_required_response("ch_a"), final_a])
    tunnel_b = AsyncMock(side_effect=[_payment_required_response("ch_b"), final_b])
    emit_a = AsyncMock()
    emit_b = AsyncMock()

    async def submit_both() -> None:
        await _wait_for_pending(negotiator, [("session-c", "ch_a"), ("session-c", "ch_b")])
        assert negotiator.submit_credential("session-c", "ch_a", "cred-a") is True
        assert negotiator.submit_credential("session-c", "ch_b", "cred-b") is True

    submitter = asyncio.create_task(submit_both())
    results = await asyncio.gather(
        negotiator.execute_with_payment(
            chat_session_id="session-c",
            endpoint_slug="slug-a",
            tunnel_call=tunnel_a,
            emit_event=emit_a,
            timeout_seconds=2.0,
        ),
        negotiator.execute_with_payment(
            chat_session_id="session-c",
            endpoint_slug="slug-b",
            tunnel_call=tunnel_b,
            emit_event=emit_b,
            timeout_seconds=2.0,
        ),
    )
    await submitter

    result_a, result_b = results
    assert result_a == final_a
    assert result_b == final_b
    # Each side received its own credential.
    assert tunnel_a.await_args_list[1].args == ("cred-a",)
    assert tunnel_b.await_args_list[1].args == ("cred-b",)
    # Each side emitted exactly one event.
    emit_a.assert_awaited_once()
    emit_b.assert_awaited_once()
    call_a = emit_a.await_args
    call_b = emit_b.await_args
    assert call_a is not None and call_b is not None
    assert call_a.args[0]["data"]["challenge_id"] == "ch_a"
    assert call_b.args[0]["data"]["challenge_id"] == "ch_b"


async def test_max_pending_cap_rejects_overflow() -> None:
    """The negotiator refuses new negotiations when the pending-future cap is hit."""
    negotiator = PaymentNegotiator(max_pending=1)

    blocking_tunnel = AsyncMock(return_value=_payment_required_response("ch_block"))
    overflow_tunnel = AsyncMock(return_value=_payment_required_response("ch_over"))
    emit = AsyncMock()

    # Start a long-lived negotiation that will fill the single pending slot.
    blocked = asyncio.create_task(
        negotiator.execute_with_payment(
            chat_session_id="s",
            endpoint_slug="slug",
            tunnel_call=blocking_tunnel,
            emit_event=emit,
            timeout_seconds=5.0,
        )
    )
    await _wait_for_pending(negotiator, [("s", "ch_block")])

    # A second negotiation must be refused immediately.
    with pytest.raises(RuntimeError, match="pending-future cap"):
        await negotiator.execute_with_payment(
            chat_session_id="s",
            endpoint_slug="slug",
            tunnel_call=overflow_tunnel,
            emit_event=emit,
            timeout_seconds=5.0,
        )

    # Cleanup: resolve the first future so the task exits.
    negotiator.submit_credential("s", "ch_block", "cred")
    await blocked
