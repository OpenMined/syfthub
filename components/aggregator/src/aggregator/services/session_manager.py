"""Manages the bidirectional relay between frontend WebSocket and space transport.

The session manager coordinates two concurrent coroutines:
- relay_space_to_frontend: reads events from transport, forwards to WebSocket
- relay_frontend_to_space: reads messages from WebSocket, forwards to transport
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

from aggregator.schemas.agent import AgentSessionState

if TYPE_CHECKING:
    from aggregator.services.session_transport import SessionTransport

logger = logging.getLogger(__name__)

# Terminal states where the session is done
_TERMINAL_STATES = {
    AgentSessionState.COMPLETED,
    AgentSessionState.FAILED,
    AgentSessionState.CANCELLED,
    AgentSessionState.TIMED_OUT,
}

# Inactivity timeout in seconds
INACTIVITY_TIMEOUT = 1800.0  # 30 minutes


@dataclass
class AgentSession:
    """Tracks per-session state for the aggregator relay."""

    session_id: str
    websocket: WebSocket
    transport: SessionTransport
    endpoint_owner: str
    endpoint_slug: str
    state: AgentSessionState = AgentSessionState.INITIALIZING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    sequence_counter: int = 0
    config: dict[str, Any] = field(default_factory=dict)


def create_session_id() -> str:
    """Generate a unique session ID."""
    return str(uuid.uuid4())


async def relay_space_to_frontend(session: AgentSession) -> None:
    """Read events from transport and forward to WebSocket.

    Runs as a concurrent coroutine alongside relay_frontend_to_space.
    """
    transport = session.transport
    try:
        async for event in transport.receive_from_space():
            session.last_activity = datetime.now(UTC)
            session.sequence_counter += 1

            event_type = event.get("event_type", "unknown")

            # Build WebSocket envelope
            ws_message = {
                "type": event_type,
                "session_id": session.session_id,
                "sequence": session.sequence_counter,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": event.get("data", event),
            }

            # Update session state based on event type
            if event_type == "agent.request_input":
                session.state = AgentSessionState.AWAITING_INPUT
            elif event_type == "session.completed":
                session.state = AgentSessionState.COMPLETED
            elif event_type == "session.failed":
                session.state = AgentSessionState.FAILED
            elif session.state != AgentSessionState.AWAITING_INPUT:
                session.state = AgentSessionState.RUNNING

            await session.websocket.send_json(ws_message)

            # Break on terminal states
            if session.state in _TERMINAL_STATES:
                break

    except Exception:
        logger.error(
            "Error in space-to-frontend relay",
            extra={"session_id": session.session_id},
            exc_info=True,
        )


async def relay_frontend_to_space(session: AgentSession) -> None:
    """Read messages from WebSocket and forward to transport.

    Runs as a concurrent coroutine alongside relay_space_to_frontend.
    """
    transport = session.transport
    try:
        while session.state not in _TERMINAL_STATES:
            try:
                data = await asyncio.wait_for(
                    session.websocket.receive_json(),
                    timeout=INACTIVITY_TIMEOUT,
                )
            except TimeoutError:
                logger.warning(
                    "Agent session timed out due to inactivity",
                    extra={"session_id": session.session_id},
                )
                session.state = AgentSessionState.TIMED_OUT
                await transport.send_cancel()
                break
            except Exception:
                # WebSocket disconnected or other error
                break

            session.last_activity = datetime.now(UTC)
            msg_type = data.get("type", "")

            if msg_type in ("user.cancel", "session.close"):
                session.state = AgentSessionState.CANCELLED
                await transport.send_cancel()
                break
            elif msg_type in ("user.message", "user.confirm", "user.deny"):
                await transport.send_to_space(data)
            elif msg_type == "ping":
                await session.websocket.send_json({"type": "pong"})
            else:
                logger.debug(
                    "Unknown message type from frontend: %s",
                    msg_type,
                    extra={"session_id": session.session_id},
                )

    except Exception:
        logger.error(
            "Error in frontend-to-space relay",
            extra={"session_id": session.session_id},
            exc_info=True,
        )
