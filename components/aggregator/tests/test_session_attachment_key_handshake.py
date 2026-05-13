"""Verifies session_transport embeds session_attachment_key in agent_session_start."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from aggregator.services.session_transport import NATSSessionTransport


@pytest.mark.asyncio
async def test_session_attachment_key_embedded_when_capability_declared() -> None:
    nats_transport = MagicMock()
    nats_transport._ensure_connected = AsyncMock(
        return_value=MagicMock(
            subscribe=AsyncMock(),
            publish=AsyncMock(),
            flush=AsyncMock(),
        )
    )
    st = NATSSessionTransport(
        nats_transport=nats_transport,
        peer_channel="chan-1",
        session_id="sess-1",
        space_public_key_b64="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",  # placeholder
        target_username="alice",
    )

    captured: dict = {}

    async def fake_publish(msg_type: str, payload: dict) -> None:
        captured["msg_type"] = msg_type
        captured["payload"] = payload

    st._publish_to_space = fake_publish  # type: ignore[assignment]
    nc = MagicMock(subscribe=AsyncMock())
    nats_transport._ensure_connected = AsyncMock(return_value=nc)

    await st.start_session(
        {
            "session_id": "sess-1",
            "prompt": "hi",
            "endpoint_slug": "code-assistant",
            "capabilities": ["attachments"],
        }
    )

    assert captured["msg_type"] == "agent_session_start"
    assert "session_attachment_key" in captured["payload"]
    decoded = base64.b64decode(captured["payload"]["session_attachment_key"])
    assert len(decoded) == 32
    # The transmitted key MUST match the transport's stored key so the HTTP
    # relay (which reads from the transport) and the HOST (which reads from
    # the start payload) end up with the same KEK material.
    assert decoded == st.session_attachment_key


@pytest.mark.asyncio
async def test_session_attachment_key_absent_when_capability_missing() -> None:
    nats_transport = MagicMock()
    st = NATSSessionTransport(
        nats_transport=nats_transport,
        peer_channel="chan-2",
        session_id="sess-2",
        space_public_key_b64="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        target_username="alice",
    )

    captured: dict = {}

    async def fake_publish(msg_type: str, payload: dict) -> None:
        captured["msg_type"] = msg_type
        captured["payload"] = payload

    st._publish_to_space = fake_publish  # type: ignore[assignment]
    nats_transport._ensure_connected = AsyncMock(return_value=MagicMock(subscribe=AsyncMock()))

    await st.start_session(
        {
            "session_id": "sess-2",
            "prompt": "hi",
            "endpoint_slug": "code-assistant",
        }
    )

    assert "session_attachment_key" not in captured["payload"]
