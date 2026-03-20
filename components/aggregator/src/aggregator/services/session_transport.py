"""Transport abstraction for aggregator-to-space communication in agent sessions.

Implements NATSSessionTransport for sending encrypted agent messages
to spaces via NATS and receiving encrypted agent events back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Protocol

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from aggregator import crypto
from aggregator.clients.nats_transport import (
    TUNNEL_PROTOCOL_VERSION,
    NATSTransport,
)

logger = logging.getLogger(__name__)


class SessionTransport(Protocol):
    """Protocol for agent session transport."""

    async def send_to_space(self, message: dict[str, Any]) -> None:
        """Send a message to the space."""
        ...

    async def receive_from_space(self) -> AsyncGenerator[dict[str, Any], None]:
        """Receive events from the space as an async generator."""
        ...  # pragma: no cover
        yield {}  # noqa: B027

    async def send_cancel(self) -> None:
        """Send a cancel signal to the space."""
        ...

    async def close(self) -> None:
        """Clean up transport resources."""
        ...


class NATSSessionTransport:
    """NATS-based transport for agent sessions.

    Publishes encrypted agent messages to the space via NATS and
    receives encrypted agent events from the peer channel subscription.
    """

    def __init__(
        self,
        nats_transport: NATSTransport,
        peer_channel: str,
        session_id: str,
        space_public_key_b64: str,
        target_username: str,
    ) -> None:
        self._nats_transport = nats_transport
        self._peer_channel = peer_channel
        self._session_id = session_id
        self._space_public_key_b64 = space_public_key_b64
        self._target_username = target_username
        self._subscription: Any = None
        self._message_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._closed = False
        # Retained ephemeral private key for the session start message
        self._ephemeral_priv: X25519PrivateKey | None = None

    async def start_session(self, payload: dict[str, Any]) -> None:
        """Send agent_session_start to the space and subscribe for responses.

        Args:
            payload: The session start payload (prompt, endpoint, config, etc.)
        """
        nc = await self._nats_transport._ensure_connected()

        # Subscribe to peer channel for responses
        peer_subject = f"syfthub.peer.{self._peer_channel}"
        self._subscription = await nc.subscribe(
            peer_subject,
            cb=self._on_message,
        )
        logger.info(
            "Subscribed to peer channel for agent session",
            extra={"peer_channel": self._peer_channel, "session_id": self._session_id},
        )

        # Build and send the session start message
        await self._publish_to_space(
            msg_type="agent_session_start",
            payload=payload,
        )

    async def send_to_space(self, message: dict[str, Any]) -> None:
        """Send a message to the space (user_message, session_cancel, etc.)."""
        msg_type = message.get("type", "agent_user_message")
        await self._publish_to_space(
            msg_type=msg_type,
            payload=message,
        )

    async def receive_from_space(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield decrypted agent events from the space."""
        while not self._closed:
            try:
                event = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=5.0,
                )
                yield event
            except TimeoutError:
                # No event within 5s — continue waiting
                continue
            except asyncio.CancelledError:
                break

    async def close(self) -> None:
        """Unsubscribe from NATS peer channel and clean up."""
        self._closed = True
        if self._subscription is not None:
            try:
                await self._subscription.unsubscribe()
            except Exception:
                logger.debug("Error unsubscribing from peer channel", exc_info=True)
            self._subscription = None
        logger.info(
            "Agent session transport closed",
            extra={"session_id": self._session_id},
        )

    async def send_cancel(self) -> None:
        """Send agent_session_cancel to the space."""
        await self._publish_to_space(
            msg_type="agent_session_cancel",
            payload={"session_id": self._session_id},
        )

    async def _publish_to_space(self, msg_type: str, payload: dict[str, Any]) -> None:
        """Encrypt and publish a message to the space's NATS subject."""
        nc = await self._nats_transport._ensure_connected()

        correlation_id = str(uuid.uuid4())
        payload_json = json.dumps(payload)

        encryption_info, ephemeral_priv = crypto.encrypt_tunnel_request(
            payload_json=payload_json,
            space_public_key_b64=self._space_public_key_b64,
            correlation_id=correlation_id,
        )

        # Retain ephemeral private key for decrypting responses
        self._ephemeral_priv = ephemeral_priv

        message: dict[str, Any] = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": msg_type,
            "correlation_id": correlation_id,
            "reply_to": self._peer_channel,
            "endpoint": {
                "slug": "",
                "type": "agent",
            },
            "payload": None,
            "timeout_ms": 0,
            "encryption_info": {
                "algorithm": encryption_info["algorithm"],
                "ephemeral_public_key": encryption_info["ephemeral_public_key"],
                "nonce": encryption_info["nonce"],
            },
            "encrypted_payload": encryption_info["encrypted_payload"],
        }

        subject = f"syfthub.spaces.{self._target_username}"
        await nc.publish(subject, json.dumps(message).encode())
        await nc.flush()

        logger.debug(
            "Published %s to space",
            msg_type,
            extra={
                "session_id": self._session_id,
                "subject": subject,
                "correlation_id": correlation_id,
            },
        )

    async def _on_message(self, msg: Any) -> None:
        """Handle incoming NATS messages from the peer channel."""
        try:
            data = json.loads(msg.data)

            # Only process agent_event messages for this session
            msg_type = data.get("type", "")
            if msg_type != "agent_event":
                return

            # Decrypt the response payload
            encrypted_payload = data.get("encrypted_payload", "")
            encryption_info = data.get("encryption_info")
            correlation_id = data.get("correlation_id", "")

            if encrypted_payload and encryption_info and self._ephemeral_priv:
                try:
                    plaintext = crypto.decrypt_tunnel_response(
                        encrypted_payload_b64=encrypted_payload,
                        encryption_info=encryption_info,
                        ephemeral_private_key=self._ephemeral_priv,
                        correlation_id=correlation_id,
                    )
                    event = json.loads(plaintext)
                except Exception:
                    logger.warning(
                        "Failed to decrypt agent event, trying raw payload",
                        exc_info=True,
                    )
                    event = data.get("payload", data)
            else:
                # Fallback to unencrypted payload for development
                event = data.get("payload", data)

            # Filter by session_id
            event_session_id = event.get("session_id", "")
            if event_session_id and event_session_id != self._session_id:
                return

            await self._message_queue.put(event)

        except Exception:
            logger.error("Error processing agent event from NATS", exc_info=True)
