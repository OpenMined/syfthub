"""NATS transport for tunneling SyftAI Spaces.

When a SyftAI Space registers with a `tunneling:<username>` domain,
it can connect to NATS pub/sub to receive requests from the aggregator
and send responses back via peer channels.

Subject namespace:
- `syfthub.spaces.{username}` — this space subscribes here for incoming requests
- `syfthub.peer.{peer_channel}` — responses are published here (from reply_to field)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import nats
from nats.aio.client import Client as NATSClient

logger = logging.getLogger(__name__)


class NATSSpaceTransport:
    """NATS transport for a tunneling SyftAI Space.

    Subscribes to the space's NATS channel and dispatches incoming
    tunnel requests to the appropriate endpoint handlers. Responses
    are published back to the peer channel specified in each request.
    """

    def __init__(
        self,
        username: str,
        nats_url: str,
        nats_auth_token: str,
    ):
        self._username = username
        self._nats_url = nats_url
        self._nats_auth_token = nats_auth_token
        self._nc: NATSClient | None = None
        self._sub: Any = None
        self._message_handler: Callable[
            [dict[str, Any], str], Coroutine[Any, Any, None]
        ] | None = None
        self._shutdown = False

    @property
    def subject(self) -> str:
        """NATS subject this space subscribes to."""
        return f"syfthub.spaces.{self._username}"

    async def connect(self) -> None:
        """Connect to NATS server."""
        logger.info(f"Connecting to NATS at {self._nats_url} as {self._username}")
        self._nc = await nats.connect(
            self._nats_url,
            token=self._nats_auth_token,
            name=f"syfthub-space-{self._username}",
        )
        logger.info(f"Connected to NATS, subscribing to {self.subject}")

    async def subscribe(
        self,
        message_handler: Callable[[dict[str, Any], str], Coroutine[Any, Any, None]],
    ) -> None:
        """Subscribe to the space's channel and process incoming messages.

        Args:
            message_handler: Async callback that receives (parsed_data, from_info).
                The handler is responsible for processing the request and
                calling publish_response() with the result.
        """
        if self._nc is None:
            raise RuntimeError("Not connected to NATS")

        self._message_handler = message_handler

        async def _on_message(msg: Any) -> None:
            try:
                data = json.loads(msg.data.decode())
                # Pass the data and subject info to the handler
                await message_handler(data, msg.subject)
            except json.JSONDecodeError:
                logger.warning("Non-JSON message received on %s, ignoring", msg.subject)
            except Exception as e:
                logger.exception("Error processing NATS message: %s", e)

        self._sub = await self._nc.subscribe(self.subject, cb=_on_message)
        logger.info(f"Subscribed to {self.subject}")

    async def publish_response(
        self, peer_channel: str, response: dict[str, Any]
    ) -> None:
        """Publish a tunnel response to a peer channel.

        Args:
            peer_channel: The peer channel identifier (from reply_to field).
            response: The TunnelResponse dict to publish.
        """
        if self._nc is None:
            raise RuntimeError("Not connected to NATS")

        reply_subject = f"syfthub.peer.{peer_channel}"
        await self._nc.publish(reply_subject, json.dumps(response).encode())
        await self._nc.flush()
        logger.debug(f"Published response to {reply_subject}")

    async def run_forever(self) -> None:
        """Block until shutdown is requested."""
        while not self._shutdown:
            await asyncio.sleep(1)

    async def close(self) -> None:
        """Close the NATS connection and unsubscribe."""
        self._shutdown = True
        if self._sub is not None:
            await self._sub.unsubscribe()
            self._sub = None
        if self._nc is not None and self._nc.is_connected:
            await self._nc.close()
            self._nc = None
        logger.info("NATS transport closed")
