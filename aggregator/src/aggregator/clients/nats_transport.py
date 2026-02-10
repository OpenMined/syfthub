"""NATS transport for communicating with tunneling SyftAI Spaces.

When a SyftAI Space registers with a `tunneling:<username>` domain,
it connects to the platform via NATS pub/sub instead of HTTP. This
transport sends requests to those spaces and collects responses.

Subject namespace:
- `syfthub.spaces.{username}` — space listens here for incoming requests
- `syfthub.peer.{peer_channel}` — aggregator subscribes here for replies

Message format: syfthub-tunnel/v1 protocol (see syfthub-api schemas)
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

import nats
from nats.aio.client import Client as NATSClient

from aggregator.core.config import get_settings
from aggregator.schemas.internal import GenerationResult, RetrievalResult
from aggregator.schemas.responses import Document

logger = logging.getLogger(__name__)

TUNNEL_PROTOCOL_VERSION = "syfthub-tunnel/v1"
TUNNELING_PREFIX = "tunneling:"


def is_tunneling_url(url: str) -> bool:
    """Check if a URL is a tunneling URL."""
    return url.startswith(TUNNELING_PREFIX)


def extract_tunnel_username(url: str) -> str:
    """Extract the username from a tunneling URL."""
    return url[len(TUNNELING_PREFIX) :]


class NATSTransportError(Exception):
    """Error during NATS transport communication."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


class NATSTransport:
    """Transport for sending requests to tunneling spaces via NATS.

    This client connects to NATS and implements the syfthub-tunnel/v1
    protocol for request/response communication with tunneling spaces.
    """

    def __init__(
        self,
        nats_url: str | None = None,
        nats_auth_token: str | None = None,
        default_timeout: float = 30.0,
    ):
        settings = get_settings()
        self._nats_url = nats_url or settings.nats_url
        self._nats_auth_token = nats_auth_token or settings.nats_auth_token
        self._default_timeout = default_timeout
        self._nc: NATSClient | None = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> NATSClient:
        """Ensure we have an active NATS connection."""
        if self._nc is not None and self._nc.is_connected:
            return self._nc

        async with self._lock:
            # Double-check after acquiring lock
            if self._nc is not None and self._nc.is_connected:
                return self._nc

            logger.info(f"Connecting to NATS at {self._nats_url}")
            self._nc = await nats.connect(
                self._nats_url,
                token=self._nats_auth_token,
                name="syfthub-aggregator",
            )
            return self._nc

    async def close(self) -> None:
        """Close the NATS connection."""
        if self._nc is not None and self._nc.is_connected:
            await self._nc.close()
            self._nc = None

    def _build_tunnel_request(
        self,
        slug: str,
        endpoint_type: str,
        payload: dict[str, Any],
        peer_channel: str,
        timeout_ms: int = 30000,
        satellite_token: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Build a syfthub-tunnel/v1 request message.

        Returns:
            Tuple of (correlation_id, message_dict)
        """
        correlation_id = str(uuid.uuid4())
        message = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": peer_channel,
            "endpoint": {
                "slug": slug,
                "type": endpoint_type,
            },
            "payload": payload,
            "timeout_ms": timeout_ms,
        }
        if satellite_token:
            message["satellite_token"] = satellite_token
        return correlation_id, message

    async def _send_and_receive(
        self,
        target_username: str,
        peer_channel: str,
        slug: str,
        endpoint_type: str,
        payload: dict[str, Any],
        timeout: float | None = None,
        satellite_token: str | None = None,
    ) -> dict[str, Any]:
        """Send a tunnel request and wait for the response.

        Args:
            target_username: Username of the tunneling space.
            peer_channel: Unique peer channel for receiving the reply.
            slug: Endpoint slug.
            endpoint_type: "model" or "data_source".
            payload: Request payload matching HTTP request body.
            timeout: Timeout in seconds (defaults to self._default_timeout).
            satellite_token: Optional satellite token for authenticated endpoints.

        Returns:
            The parsed TunnelResponse dict.

        Raises:
            NATSTransportError: On timeout, connection failure, or error response.
        """
        timeout = timeout or self._default_timeout
        timeout_ms = int(timeout * 1000)

        nc = await self._ensure_connected()

        # Build the request message
        correlation_id, request_msg = self._build_tunnel_request(
            slug=slug,
            endpoint_type=endpoint_type,
            payload=payload,
            peer_channel=peer_channel,
            timeout_ms=timeout_ms,
            satellite_token=satellite_token,
        )

        # Subscribe to reply channel before publishing
        reply_subject = f"syfthub.peer.{peer_channel}"
        response_future: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()

        async def message_handler(msg: Any) -> None:
            try:
                data = json.loads(msg.data.decode())
                # Match by correlation_id
                if data.get("correlation_id") == correlation_id and not response_future.done():
                    response_future.set_result(data)
            except Exception as e:
                if not response_future.done():
                    response_future.set_exception(e)

        sub = await nc.subscribe(reply_subject, cb=message_handler)

        try:
            # Publish request to the space's channel
            publish_subject = f"syfthub.spaces.{target_username}"
            await nc.publish(publish_subject, json.dumps(request_msg).encode())
            await nc.flush()

            logger.info(
                f"Published tunnel request to {publish_subject} "
                f"(correlation_id={correlation_id}, slug={slug})"
            )

            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response

        except TimeoutError:
            raise NATSTransportError(
                f"Timeout waiting for response from {target_username}/{slug} after {timeout}s",
                code="TIMEOUT",
            )
        finally:
            await sub.unsubscribe()

    async def query_data_source(
        self,
        target_username: str,
        slug: str,
        endpoint_path: str,
        query: str,
        peer_channel: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        transaction_token: str | None = None,
        satellite_token: str | None = None,
        timeout: float | None = None,
    ) -> RetrievalResult:
        """Query a tunneling data source endpoint via NATS.

        Args:
            target_username: Username of the tunneling space.
            slug: Endpoint slug.
            endpoint_path: Full path for logging/citations.
            query: Search query.
            peer_channel: Peer channel for the reply.
            top_k: Number of documents to retrieve.
            similarity_threshold: Minimum similarity score.
            transaction_token: Optional billing token.
            satellite_token: Optional satellite token for authenticated endpoints.
            timeout: Timeout in seconds.

        Returns:
            RetrievalResult with documents and status.
        """
        start_time = time.perf_counter()

        payload: dict[str, Any] = {
            "messages": query,
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
            "include_metadata": True,
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        try:
            response = await self._send_and_receive(
                target_username=target_username,
                peer_channel=peer_channel,
                slug=slug,
                endpoint_type="data_source",
                payload=payload,
                timeout=timeout,
                satellite_token=satellite_token,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response.get("status") == "error":
                error = response.get("error", {})
                error_msg = error.get("message", "Unknown tunnel error")
                logger.warning(
                    f"Tunnel data source query failed: {error_msg}",
                    extra={"endpoint_path": endpoint_path},
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=error_msg,
                    latency_ms=latency_ms,
                )

            # Parse response payload (same format as HTTP response)
            resp_payload = response.get("payload", {})
            documents = self._parse_data_source_response(resp_payload)

            logger.info(
                f"Tunnel data source query complete: {len(documents)} documents, {latency_ms}ms",
                extra={"endpoint_path": endpoint_path},
            )

            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=documents,
                status="success",
                latency_ms=latency_ms,
            )

        except NATSTransportError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                f"Tunnel transport error for data source {endpoint_path}: {e}",
            )
            status = "timeout" if e.code == "TIMEOUT" else "error"
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status=status,
                error_message=str(e),
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                f"Unexpected error querying tunnel data source {endpoint_path}: {e}",
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="error",
                error_message=f"Unexpected error: {e}",
                latency_ms=latency_ms,
            )

    async def query_model(
        self,
        target_username: str,
        slug: str,
        messages: list[dict[str, str]],
        peer_channel: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        transaction_token: str | None = None,
        satellite_token: str | None = None,
        timeout: float | None = None,
    ) -> GenerationResult:
        """Query a tunneling model endpoint via NATS.

        Args:
            target_username: Username of the tunneling space.
            slug: Endpoint slug.
            messages: List of conversation messages.
            peer_channel: Peer channel for the reply.
            max_tokens: Maximum tokens to generate.
            temperature: Temperature for generation.
            transaction_token: Optional billing token.
            satellite_token: Optional satellite token for authenticated endpoints.
            timeout: Timeout in seconds.

        Returns:
            GenerationResult with response and metadata.

        Raises:
            NATSTransportError: On failure.
        """
        start_time = time.perf_counter()

        payload: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "stop_sequences": [],
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        try:
            response = await self._send_and_receive(
                target_username=target_username,
                peer_channel=peer_channel,
                slug=slug,
                endpoint_type="model",
                payload=payload,
                timeout=timeout,
                satellite_token=satellite_token,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response.get("status") == "error":
                error = response.get("error", {})
                error_msg = error.get("message", "Unknown tunnel error")
                raise NATSTransportError(error_msg, code=error.get("code"))

            # Parse response payload (same format as HTTP response)
            resp_payload = response.get("payload", {})
            response_text, usage = self._parse_model_response(resp_payload)

            logger.info(f"Tunnel model query complete: {latency_ms}ms")

            return GenerationResult(
                response=response_text,
                latency_ms=latency_ms,
                usage=usage,
            )

        except NATSTransportError:
            raise
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            raise NATSTransportError(f"Unexpected error: {e}") from e

    def _parse_data_source_response(self, data: dict[str, Any]) -> list[Document]:
        """Parse documents from tunnel response payload.

        The payload matches the SyftAI-Space QueryEndpointResponse format.
        """
        documents: list[Document] = []
        references = data.get("references")
        if not references:
            return documents

        raw_docs = references.get("documents", [])
        for doc in raw_docs:
            if isinstance(doc, dict):
                documents.append(
                    Document(
                        content=doc.get("content", ""),
                        score=float(doc.get("similarity_score", 0.0)),
                        metadata=doc.get("metadata", {}),
                    )
                )
        return documents

    def _parse_model_response(self, data: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        """Parse model response from tunnel response payload.

        Returns:
            Tuple of (response_text, usage_dict).
        """
        summary = data.get("summary")
        if not summary:
            return "", None

        message = summary.get("message", {})
        if isinstance(message, dict):
            response_text = message.get("content", "")
        elif isinstance(message, str):
            response_text = message
        else:
            response_text = ""

        usage = summary.get("usage")
        if usage:
            usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

        return response_text, usage
