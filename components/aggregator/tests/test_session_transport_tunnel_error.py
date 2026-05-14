"""Regression test for the tunnel-error → session.failed translation.

When the HOST denies a session before it can be constructed (policy failure,
auth failure, endpoint not found), it publishes a TunnelResponse with
type="endpoint_response" and status="error" on the peer channel. Without
this translation the message is silently dropped and the client's WebSocket
stalls on the optimistic session.created the aggregator already sent — see
docstring on NATSSessionTransport._on_message.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aggregator.services.session_transport import NATSSessionTransport


def _new_transport(session_id: str = "sess-123") -> NATSSessionTransport:
    return NATSSessionTransport(
        nats_transport=MagicMock(),
        peer_channel="chan-x",
        session_id=session_id,
        space_public_key_b64="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        target_username="alice",
    )


def _nats_msg(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(data=json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_tunnel_error_translates_to_session_failed() -> None:
    st = _new_transport()

    await st._on_message(
        _nats_msg(
            {
                "type": "endpoint_response",
                "status": "error",
                "correlation_id": "corr-1",
                "error": {
                    "code": "EXECUTION_FAILED",
                    "message": 'access denied by policy "access group": '
                    "User 'ionesiojr' is not a member of access group 'access group'",
                    "details": {"policy_name": "access group"},
                },
            }
        )
    )

    queued = await st._message_queue.get()
    assert queued["event_type"] == "session.failed"
    assert queued["session_id"] == "sess-123"
    data = queued["data"]
    assert "access denied" in data["error"]
    assert data["reason"] == "EXECUTION_FAILED"
    assert data["details"] == {"policy_name": "access group"}


@pytest.mark.asyncio
async def test_tunnel_error_without_error_field_still_terminates() -> None:
    """Defensive: even a malformed error response must surface as session.failed."""
    st = _new_transport()

    await st._on_message(
        _nats_msg(
            {
                "type": "endpoint_response",
                "status": "error",
                "correlation_id": "corr-2",
            }
        )
    )

    queued = await st._message_queue.get()
    assert queued["event_type"] == "session.failed"
    assert queued["data"]["error"] == "session failed"
    assert queued["data"]["reason"] == "EXECUTION_FAILED"


@pytest.mark.asyncio
async def test_endpoint_response_with_success_status_is_ignored() -> None:
    """Non-error endpoint_response messages must not be misinterpreted as failures."""
    st = _new_transport()

    await st._on_message(
        _nats_msg(
            {
                "type": "endpoint_response",
                "status": "success",
                "correlation_id": "corr-3",
            }
        )
    )

    assert st._message_queue.empty()


@pytest.mark.asyncio
async def test_unrelated_message_type_is_ignored() -> None:
    """Verify the original agent_event filter still applies to other types."""
    st = _new_transport()

    await st._on_message(_nats_msg({"type": "heartbeat"}))
    assert st._message_queue.empty()
