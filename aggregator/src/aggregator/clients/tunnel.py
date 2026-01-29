"""Client for communicating with tunneled SyftAI-Space endpoints via MQ.

Tunneled endpoints use the SyftHub message queue instead of HTTP for communication.
This enables SyftAI-Spaces running behind firewalls to serve requests without
exposing public HTTP endpoints.

Protocol: syfthub-tunnel/v1
"""

import asyncio
import json
import time
import uuid
from typing import Any

import httpx

from aggregator.observability import get_correlation_id, get_logger
from aggregator.observability.constants import CORRELATION_ID_HEADER, LogEvents
from aggregator.schemas.internal import GenerationResult, RetrievalResult
from aggregator.schemas.responses import Document

logger = get_logger(__name__)

# Tunnel protocol constants
TUNNEL_PROTOCOL_VERSION = "syfthub-tunnel/v1"
TUNNELING_PREFIX = "tunneling:"


def is_tunneled_url(url: str) -> bool:
    """Check if a URL is a tunneled endpoint.

    Args:
        url: The endpoint URL.

    Returns:
        True if the URL starts with 'tunneling:'.
    """
    return url.startswith(TUNNELING_PREFIX)


def extract_tunnel_username(url: str) -> str:
    """Extract the username from a tunneling URL.

    Args:
        url: The tunneling URL (e.g., 'tunneling:bob').

    Returns:
        The username (e.g., 'bob').

    Raises:
        ValueError: If not a valid tunneling URL.
    """
    if not is_tunneled_url(url):
        raise ValueError(f"Not a tunneling URL: {url}")
    return url[len(TUNNELING_PREFIX):]


class TunnelClientError(Exception):
    """Error communicating with a tunneled endpoint."""

    pass


class TunnelClient:
    """Client for communicating with tunneled endpoints via MQ.

    This client implements the syfthub-tunnel/v1 protocol:
    1. Publishes a request to the target Space's MQ queue
    2. Polls a reserved queue for the response
    3. Parses the response according to the tunnel protocol

    The client uses satellite tokens for MQ authentication.
    """

    def __init__(
        self,
        syfthub_url: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
    ):
        """Initialize the tunnel client.

        Args:
            syfthub_url: Base URL of the SyftHub backend.
            timeout: Total timeout for tunnel requests in seconds.
            poll_interval: Interval between queue polls in seconds.
        """
        self.syfthub_url = syfthub_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.http_timeout = httpx.Timeout(10.0)  # HTTP timeout for individual requests

    async def query_data_source(
        self,
        target_username: str,
        endpoint_slug: str,
        query: str,
        top_k: int,
        similarity_threshold: float,
        satellite_token: str,
        response_queue_id: str,
        response_queue_token: str,
        endpoint_path: str,
        transaction_token: str | None = None,
    ) -> RetrievalResult:
        """Query a tunneled data source endpoint.

        Args:
            target_username: Username of the Space owner (from tunneling URL).
            endpoint_slug: The endpoint slug.
            query: The search query.
            top_k: Number of documents to retrieve.
            similarity_threshold: Minimum similarity score.
            satellite_token: Satellite token for MQ authentication.
            response_queue_id: Reserved queue ID for receiving response.
            response_queue_token: Token for accessing the reserved queue.
            endpoint_path: Path identifier for logging.
            transaction_token: Optional transaction token for billing.

        Returns:
            RetrievalResult with documents and status.
        """
        start_time = time.perf_counter()
        correlation_id = get_correlation_id() or str(uuid.uuid4())

        logger.debug(
            LogEvents.DATA_SOURCE_QUERY_STARTED,
            endpoint_path=endpoint_path,
            target_username=target_username,
            tunneled=True,
        )

        try:
            # Build tunnel request payload
            payload: dict[str, Any] = {
                "messages": query,
                "limit": top_k,
                "similarity_threshold": similarity_threshold,
                "include_metadata": True,
            }
            if transaction_token:
                payload["transaction_token"] = transaction_token

            # Send request via tunnel
            response = await self._send_tunnel_request(
                target_username=target_username,
                endpoint_slug=endpoint_slug,
                endpoint_type="data_source",
                payload=payload,
                satellite_token=satellite_token,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
                correlation_id=correlation_id,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Check for error response
            if response.get("status") == "error":
                error = response.get("error", {})
                error_message = error.get("message", "Unknown tunnel error")
                logger.warning(
                    LogEvents.DATA_SOURCE_QUERY_FAILED,
                    endpoint_path=endpoint_path,
                    error=error_message,
                    latency_ms=latency_ms,
                    tunneled=True,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=error_message,
                    latency_ms=latency_ms,
                )

            # Parse successful response
            documents = self._parse_data_source_response(response.get("payload", {}))

            logger.info(
                LogEvents.DATA_SOURCE_QUERY_COMPLETED,
                endpoint_path=endpoint_path,
                documents_count=len(documents),
                latency_ms=latency_ms,
                tunneled=True,
            )

            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=documents,
                status="success",
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                LogEvents.CHAT_RETRIEVAL_TIMEOUT,
                endpoint_path=endpoint_path,
                latency_ms=latency_ms,
                tunneled=True,
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="timeout",
                error_message="Tunnel request timed out",
                latency_ms=latency_ms,
            )

        except TunnelClientError as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                LogEvents.DATA_SOURCE_QUERY_FAILED,
                endpoint_path=endpoint_path,
                error=str(e),
                latency_ms=latency_ms,
                tunneled=True,
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="error",
                error_message=str(e),
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                LogEvents.DATA_SOURCE_QUERY_FAILED,
                endpoint_path=endpoint_path,
                error=str(e),
                latency_ms=latency_ms,
                tunneled=True,
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="error",
                error_message=f"Tunnel error: {e}",
                latency_ms=latency_ms,
            )

    async def query_model(
        self,
        target_username: str,
        endpoint_slug: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        satellite_token: str,
        response_queue_id: str,
        response_queue_token: str,
        endpoint_path: str,
        transaction_token: str | None = None,
    ) -> GenerationResult:
        """Query a tunneled model endpoint.

        Args:
            target_username: Username of the Space owner (from tunneling URL).
            endpoint_slug: The endpoint slug.
            messages: List of chat messages.
            max_tokens: Maximum tokens for generation.
            temperature: Temperature for generation.
            satellite_token: Satellite token for MQ authentication.
            response_queue_id: Reserved queue ID for receiving response.
            response_queue_token: Token for accessing the reserved queue.
            endpoint_path: Path identifier for logging.
            transaction_token: Optional transaction token for billing.

        Returns:
            GenerationResult with generated content and status.
        """
        start_time = time.perf_counter()
        correlation_id = get_correlation_id() or str(uuid.uuid4())

        logger.debug(
            "model_query_started",
            endpoint_path=endpoint_path,
            target_username=target_username,
            tunneled=True,
        )

        try:
            # Build tunnel request payload
            payload: dict[str, Any] = {
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,  # Tunneled requests don't support streaming
            }
            if transaction_token:
                payload["transaction_token"] = transaction_token

            # Send request via tunnel
            response = await self._send_tunnel_request(
                target_username=target_username,
                endpoint_slug=endpoint_slug,
                endpoint_type="model",
                payload=payload,
                satellite_token=satellite_token,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
                correlation_id=correlation_id,
            )

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            # Check for error response
            if response.get("status") == "error":
                error = response.get("error", {})
                error_message = error.get("message", "Unknown tunnel error")
                logger.warning(
                    "model_query_failed",
                    endpoint_path=endpoint_path,
                    error=error_message,
                    latency_ms=latency_ms,
                    tunneled=True,
                )
                raise TunnelClientError(error_message)

            # Parse successful response
            response_text = self._parse_model_response(response.get("payload", {}))

            logger.info(
                "model_query_completed",
                endpoint_path=endpoint_path,
                content_length=len(response_text),
                latency_ms=latency_ms,
                tunneled=True,
            )

            return GenerationResult(
                response=response_text,
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                "model_query_timeout",
                endpoint_path=endpoint_path,
                latency_ms=latency_ms,
                tunneled=True,
            )
            raise TunnelClientError("Tunnel request timed out")

        except TunnelClientError:
            raise

        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                "model_query_failed",
                endpoint_path=endpoint_path,
                error=str(e),
                latency_ms=latency_ms,
                tunneled=True,
            )
            raise TunnelClientError(f"Tunnel error: {e}") from e

    async def _send_tunnel_request(
        self,
        target_username: str,
        endpoint_slug: str,
        endpoint_type: str,
        payload: dict[str, Any],
        satellite_token: str,
        response_queue_id: str,
        response_queue_token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Send a request via the tunnel protocol.

        Args:
            target_username: Username of the Space owner.
            endpoint_slug: The endpoint slug.
            endpoint_type: Type of endpoint ('data_source' or 'model').
            payload: Request payload.
            satellite_token: Satellite token for MQ authentication.
            response_queue_id: Reserved queue ID for response.
            response_queue_token: Token for accessing reserved queue.
            correlation_id: Correlation ID for request tracking.

        Returns:
            Parsed response from the tunnel.

        Raises:
            TunnelClientError: If the tunnel request fails.
            asyncio.TimeoutError: If the request times out.
        """
        # Build tunnel protocol message
        tunnel_request = {
            "protocol": TUNNEL_PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": response_queue_id,
            "endpoint": {
                "slug": endpoint_slug,
                "type": endpoint_type,
            },
            "payload": payload,
            "context": {
                "correlation_id": correlation_id,
            },
        }

        # Publish to target's queue
        await self._publish_to_queue(
            target_username=target_username,
            message=json.dumps(tunnel_request),
            satellite_token=satellite_token,
        )

        # Poll for response
        response = await asyncio.wait_for(
            self._poll_for_response(
                queue_id=response_queue_id,
                token=response_queue_token,
                correlation_id=correlation_id,
            ),
            timeout=self.timeout,
        )

        return response

    async def _publish_to_queue(
        self,
        target_username: str,
        message: str,
        satellite_token: str,
    ) -> None:
        """Publish a message to a user's queue via SyftHub MQ.

        Args:
            target_username: Username of the target user.
            message: Message to publish.
            satellite_token: Satellite token for authentication.

        Raises:
            TunnelClientError: If publishing fails.
        """
        url = f"{self.syfthub_url}/api/v1/mq/pub"
        headers = {
            "Authorization": f"Bearer {satellite_token}",
            "Content-Type": "application/json",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            try:
                response = await client.post(
                    url,
                    json={
                        "target_username": target_username,
                        "message": message,
                    },
                    headers=headers,
                )

                if response.status_code != 200:
                    error_detail = self._extract_error_detail(response)
                    raise TunnelClientError(
                        f"Failed to publish to queue: HTTP {response.status_code}: {error_detail}"
                    )

            except httpx.RequestError as e:
                raise TunnelClientError(f"Failed to publish to queue: {e}") from e

    async def _poll_for_response(
        self,
        queue_id: str,
        token: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Poll the reserved queue for a response.

        Args:
            queue_id: Reserved queue ID.
            token: Token for accessing the queue.
            correlation_id: Correlation ID to match response.

        Returns:
            Parsed response message.

        Raises:
            TunnelClientError: If polling fails or response is invalid.
        """
        url = f"{self.syfthub_url}/api/v1/mq/consume"
        headers = {
            "Content-Type": "application/json",
        }
        req_correlation_id = get_correlation_id()
        if req_correlation_id:
            headers[CORRELATION_ID_HEADER] = req_correlation_id

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            while True:
                try:
                    # Note: We don't need Authorization header for consume since we use queue token
                    # But the endpoint still requires some auth - we'll use an empty auth for now
                    # Actually, looking at the backend, consume still needs user auth
                    # We need to pass the satellite token here too
                    response = await client.post(
                        url,
                        json={
                            "queue_id": queue_id,
                            "token": token,
                            "limit": 10,
                        },
                        headers=headers,
                    )

                    if response.status_code != 200:
                        error_detail = self._extract_error_detail(response)
                        raise TunnelClientError(
                            f"Failed to consume from queue: HTTP {response.status_code}: {error_detail}"
                        )

                    data = response.json()
                    messages = data.get("messages", [])

                    # Look for response matching our correlation ID
                    for msg in messages:
                        try:
                            msg_content = json.loads(msg.get("message", "{}"))
                            if (
                                msg_content.get("protocol") == TUNNEL_PROTOCOL_VERSION
                                and msg_content.get("type") == "endpoint_response"
                                and msg_content.get("correlation_id") == correlation_id
                            ):
                                return msg_content
                        except json.JSONDecodeError:
                            continue

                    # No matching response yet, wait and retry
                    await asyncio.sleep(self.poll_interval)

                except httpx.RequestError as e:
                    raise TunnelClientError(
                        f"Failed to poll queue: {e}"
                    ) from e

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract error detail from HTTP response."""
        try:
            data = response.json()
            return data.get("detail", response.text[:200])
        except Exception:
            return response.text[:200]

    def _parse_data_source_response(self, payload: dict[str, Any]) -> list[Document]:
        """Parse documents from tunnel response payload.

        The payload follows SyftAI-Space QueryEndpointResponse format.
        """
        documents = []
        references = payload.get("references")
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

    def _parse_model_response(self, payload: dict[str, Any]) -> str:
        """Parse content from tunnel model response payload.

        The payload follows SyftAI-Space ChatEndpointResponse format.
        """
        summary = payload.get("summary")
        if not summary:
            return ""

        message = summary.get("message", {})
        return message.get("content", "")
