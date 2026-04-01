"""FastAPI WebSocket endpoint for agent sessions.

Orchestrates the full agent session lifecycle:
1. Accept WebSocket connection
2. Wait for session.start message
3. Create transport and session
4. Run bidirectional relays
5. Clean up on disconnect or completion
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aggregator.clients.nats_transport import NATSTransport
from aggregator.schemas.agent import (
    AgentSessionState,
    SessionStartPayload,
)
from aggregator.services.session_manager import (
    AgentSession,
    create_session_id,
    relay_frontend_to_space,
    relay_space_to_frontend,
)
from aggregator.services.session_transport import NATSSessionTransport

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# Shared NATS transport instance (reused across sessions)
_nats_transport: NATSTransport | None = None


def get_nats_transport() -> NATSTransport:
    """Get or create the shared NATS transport."""
    global _nats_transport
    if _nats_transport is None:
        _nats_transport = NATSTransport()
    return _nats_transport


@router.websocket("/agent/session")
async def agent_session_ws(websocket: WebSocket) -> None:
    """WebSocket endpoint for agent sessions.

    Protocol:
    1. Client connects via WebSocket
    2. Client sends session.start with prompt, endpoint, and tokens
    3. Server creates session and sends session.created with session_id
    4. Bidirectional relay runs until session ends
    5. On disconnect, cancel is sent to space
    """
    await websocket.accept()
    start_time = time.monotonic()
    session_transport: NATSSessionTransport | None = None

    try:
        # Wait for session.start message (30s timeout)
        try:
            data = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=30.0,
            )
        except TimeoutError:
            await websocket.send_json(
                {
                    "type": "agent.error",
                    "payload": {
                        "code": "SESSION_START_TIMEOUT",
                        "message": "No session.start message received within 30 seconds",
                        "recoverable": False,
                    },
                }
            )
            await websocket.close(code=1008)
            return

        msg_type = data.get("type", "")
        if msg_type != "session.start":
            await websocket.send_json(
                {
                    "type": "agent.error",
                    "payload": {
                        "code": "INVALID_MESSAGE",
                        "message": f"Expected session.start, got {msg_type}",
                        "recoverable": False,
                    },
                }
            )
            await websocket.close(code=1008)
            return

        # Validate session.start payload
        try:
            payload = SessionStartPayload(**data.get("payload", {}))
        except Exception as e:
            await websocket.send_json(
                {
                    "type": "agent.error",
                    "payload": {
                        "code": "INVALID_PAYLOAD",
                        "message": f"Invalid session.start payload: {e}",
                        "recoverable": False,
                    },
                }
            )
            await websocket.close(code=1008)
            return

        # Create session
        session_id = create_session_id()
        peer_channel = payload.peer_channel or str(uuid.uuid4())

        # Get space encryption key
        nats = get_nats_transport()
        try:
            space_public_key = await nats._get_space_public_key(payload.endpoint.owner)
        except Exception as e:
            await websocket.send_json(
                {
                    "type": "agent.error",
                    "payload": {
                        "code": "SPACE_KEY_ERROR",
                        "message": f"Failed to get space encryption key: {e}",
                        "recoverable": False,
                    },
                }
            )
            await websocket.close(code=1011)
            return

        # Create session transport
        session_transport = NATSSessionTransport(
            nats_transport=nats,
            peer_channel=peer_channel,
            session_id=session_id,
            space_public_key_b64=space_public_key,
            target_username=payload.endpoint.owner,
        )

        # Send session start to space
        session_start_payload = {
            "session_id": session_id,
            "prompt": payload.prompt,
            "endpoint_slug": payload.endpoint.slug,
            "satellite_token": payload.satellite_token,
            "transaction_token": payload.transaction_token,
            "config": payload.config or {},
            "messages": payload.messages or [],
        }
        await session_transport.start_session(session_start_payload)

        # Create session object
        session = AgentSession(
            session_id=session_id,
            websocket=websocket,
            transport=session_transport,
            endpoint_owner=payload.endpoint.owner,
            endpoint_slug=payload.endpoint.slug,
            config=payload.config or {},
        )
        session.state = AgentSessionState.RUNNING

        # Send session.created to frontend
        await websocket.send_json(
            {
                "type": "session.created",
                "session_id": session_id,
                "payload": {
                    "session_id": session_id,
                },
            }
        )

        logger.info(
            "Agent session created",
            extra={
                "session_id": session_id,
                "endpoint": f"{payload.endpoint.owner}/{payload.endpoint.slug}",
            },
        )

        # Run bidirectional relays concurrently
        await asyncio.gather(
            relay_space_to_frontend(session),
            relay_frontend_to_space(session),
            return_exceptions=True,
        )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during agent session")
        if session_transport is not None:
            try:
                await session_transport.send_cancel()
            except Exception:
                logger.debug("Error sending cancel on disconnect", exc_info=True)

    except Exception:
        logger.error("Unexpected error in agent session", exc_info=True)
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "type": "agent.error",
                    "payload": {
                        "code": "INTERNAL_ERROR",
                        "message": "An unexpected error occurred",
                        "recoverable": False,
                    },
                }
            )

    finally:
        if session_transport is not None:
            await session_transport.close()

        duration_s = time.monotonic() - start_time
        logger.info(
            "Agent session ended",
            extra={"duration_s": f"{duration_s:.1f}"},
        )
