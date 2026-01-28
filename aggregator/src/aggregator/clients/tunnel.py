"""Client for communicating with tunneled SyftAI-Space endpoints via MQ."""

import asyncio
import json
import time
import uuid
from typing import Any

from aggregator.observability import get_correlation_id, get_logger
from aggregator.observability.constants import LogEvents
from aggregator.schemas.internal import RetrievalResult
from aggregator.schemas.responses import Document

logger = get_logger(__name__)

# Tunneling URL prefix
TUNNELING_PREFIX = "tunneling:"


def is_tunneled_url(url: str) -> bool:
    """Check if a URL is a tunneled endpoint."""
    return url.startswith(TUNNELING_PREFIX)


def extract_tunnel_username(url: str) -> str:
    """Extract the username from a tunneling URL.

    Args:
        url: URL in format "tunneling:username"

    Returns:
        The username portion
    """
    if not is_tunneled_url(url):
        raise ValueError(f"Not a tunneling URL: {url}")
    return url[len(TUNNELING_PREFIX):]


class TunnelClient:
    """Client for querying tunneled SyftAI-Space endpoints via message queue.

    This client sends requests through the MQ system to endpoints that are
    behind firewalls/NAT and cannot be reached directly via HTTP.

    The tunnel protocol uses JSON messages with the following structure:
    - Request: {protocol, type: "endpoint_request", correlation_id, reply_to, endpoint, payload}
    - Response: {protocol, type: "endpoint_response", correlation_id, endpoint, status, payload}
    """

    PROTOCOL_VERSION = "syfthub-tunnel/v1"
    DEFAULT_TIMEOUT = 30.0
    POLL_INTERVAL = 0.1  # 100ms between polls

    def __init__(
        self,
        syfthub_client: Any,  # SyftHubClient from SDK
        response_queue_id: str,
        response_queue_token: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the tunnel client.

        Args:
            syfthub_client: Authenticated SyftHubClient for MQ operations
            response_queue_id: Reserved queue ID to receive responses
            response_queue_token: Token for the response queue
            timeout: Request timeout in seconds
        """
        self.client = syfthub_client
        self.response_queue_id = response_queue_id
        self.response_queue_token = response_queue_token
        self.timeout = timeout

    async def query_data_source(
        self,
        target_username: str,
        slug: str,
        endpoint_path: str,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5,
        transaction_token: str | None = None,
    ) -> RetrievalResult:
        """Query a tunneled data source endpoint.

        Args:
            target_username: Username of the endpoint owner (from tunneling URL)
            slug: Endpoint slug
            endpoint_path: Full path for logging (e.g., "owner/slug")
            query: The search query
            top_k: Number of documents to retrieve
            similarity_threshold: Minimum similarity score
            transaction_token: Transaction token for billing (optional)

        Returns:
            RetrievalResult with documents and status
        """
        start_time = time.perf_counter()
        correlation_id = str(uuid.uuid4())

        logger.debug(
            LogEvents.DATA_SOURCE_QUERY_STARTED,
            endpoint_path=endpoint_path,
            transport="tunnel",
            target=target_username,
        )

        # Build tunnel request payload
        payload = {
            "query": query,
            "limit": top_k,
            "similarity_threshold": similarity_threshold,
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        # Build tunnel message
        request_message = {
            "protocol": self.PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": self.response_queue_id,
            "endpoint": {
                "slug": slug,
                "type": "data_source",
            },
            "payload": payload,
        }

        # Add correlation ID from context if available
        ctx_correlation_id = get_correlation_id()
        if ctx_correlation_id:
            request_message["context"] = {"correlation_id": ctx_correlation_id}

        try:
            # Send request to endpoint owner's queue
            await asyncio.to_thread(
                self.client.mq.publish,
                target_username=target_username,
                message=json.dumps(request_message),
            )

            # Wait for response on our queue
            response_data = await self._wait_for_response(correlation_id)

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response_data is None:
                logger.warning(
                    LogEvents.CHAT_RETRIEVAL_TIMEOUT,
                    endpoint_path=endpoint_path,
                    latency_ms=latency_ms,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="timeout",
                    error_message="Tunnel request timed out",
                    latency_ms=latency_ms,
                )

            # Parse response
            status = response_data.get("status", "error")

            if status == "error":
                error = response_data.get("error", {})
                error_message = error.get("message", "Unknown error")
                logger.warning(
                    LogEvents.DATA_SOURCE_QUERY_FAILED,
                    endpoint_path=endpoint_path,
                    error=error_message,
                    latency_ms=latency_ms,
                )
                return RetrievalResult(
                    endpoint_path=endpoint_path,
                    documents=[],
                    status="error",
                    error_message=error_message,
                    latency_ms=latency_ms,
                )

            # Extract documents from response payload
            response_payload = response_data.get("payload", {})
            documents = self._parse_documents(response_payload)

            logger.info(
                LogEvents.DATA_SOURCE_QUERY_COMPLETED,
                endpoint_path=endpoint_path,
                documents_count=len(documents),
                latency_ms=latency_ms,
            )

            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=documents,
                status="success",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                LogEvents.DATA_SOURCE_QUERY_FAILED,
                endpoint_path=endpoint_path,
                error=str(e),
                latency_ms=latency_ms,
            )
            return RetrievalResult(
                endpoint_path=endpoint_path,
                documents=[],
                status="error",
                error_message=f"Tunnel error: {e}",
                latency_ms=latency_ms,
            )

    async def _wait_for_response(self, correlation_id: str) -> dict[str, Any] | None:
        """Wait for a response with the given correlation ID.

        Polls the response queue until a matching response is found or timeout.

        Args:
            correlation_id: The correlation ID to match

        Returns:
            Response data dict or None if timeout
        """
        deadline = time.perf_counter() + self.timeout

        while time.perf_counter() < deadline:
            try:
                # Poll the response queue (using consume with queue_id for reserved queue)
                response = await asyncio.to_thread(
                    self.client.mq.consume,
                    queue_id=self.response_queue_id,
                    token=self.response_queue_token,
                    limit=10,
                )

                # Check each message for matching correlation ID
                for msg in response.messages:
                    try:
                        data = json.loads(msg.message)
                        if data.get("correlation_id") == correlation_id:
                            return data
                    except json.JSONDecodeError:
                        continue

                # No match found, wait and poll again
                if response.remaining == 0:
                    await asyncio.sleep(self.POLL_INTERVAL)

            except Exception as e:
                logger.warning(f"Error polling response queue: {e}")
                await asyncio.sleep(self.POLL_INTERVAL)

        return None

    def _parse_documents(self, payload: dict[str, Any]) -> list[Document]:
        """Parse documents from tunnel response payload.

        The payload follows SyftAI-Space format with references.documents.
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

    async def chat_model(
        self,
        target_username: str,
        slug: str,
        endpoint_path: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        transaction_token: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat request to a tunneled model endpoint.

        Args:
            target_username: Username of the endpoint owner (from tunneling URL)
            slug: Endpoint slug
            endpoint_path: Full path for logging (e.g., "owner/slug")
            messages: List of message dicts with role and content
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            transaction_token: Transaction token for billing (optional)

        Returns:
            Dict with response text, latency_ms, and status

        Raises:
            Exception: If the request fails or times out
        """
        start_time = time.perf_counter()
        correlation_id = str(uuid.uuid4())

        logger.debug(
            LogEvents.MODEL_CHAT_STARTED,
            endpoint_path=endpoint_path,
            transport="tunnel",
            target=target_username,
        )

        # Build tunnel request payload
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if transaction_token:
            payload["transaction_token"] = transaction_token

        # Build tunnel message
        request_message = {
            "protocol": self.PROTOCOL_VERSION,
            "type": "endpoint_request",
            "correlation_id": correlation_id,
            "reply_to": self.response_queue_id,
            "endpoint": {
                "slug": slug,
                "type": "model",
            },
            "payload": payload,
        }

        # Add correlation ID from context if available
        ctx_correlation_id = get_correlation_id()
        if ctx_correlation_id:
            request_message["context"] = {"correlation_id": ctx_correlation_id}

        try:
            # Send request to endpoint owner's queue
            await asyncio.to_thread(
                self.client.mq.publish,
                target_username=target_username,
                message=json.dumps(request_message),
            )

            # Wait for response on our queue
            response_data = await self._wait_for_response(correlation_id)

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response_data is None:
                logger.warning(
                    LogEvents.MODEL_CHAT_TIMEOUT,
                    endpoint_path=endpoint_path,
                    latency_ms=latency_ms,
                )
                raise TimeoutError(f"Tunnel request to {endpoint_path} timed out")

            # Parse response
            status = response_data.get("status", "error")

            if status == "error":
                error = response_data.get("error", {})
                error_message = error.get("message", "Unknown error")
                logger.warning(
                    LogEvents.MODEL_CHAT_FAILED,
                    endpoint_path=endpoint_path,
                    error=error_message,
                    latency_ms=latency_ms,
                )
                raise Exception(f"Model error: {error_message}")

            # Extract response from payload
            response_payload = response_data.get("payload", {})
            response_text = response_payload.get("response", "")

            logger.info(
                LogEvents.MODEL_CHAT_COMPLETED,
                endpoint_path=endpoint_path,
                latency_ms=latency_ms,
            )

            return {
                "response": response_text,
                "latency_ms": latency_ms,
                "status": "success",
            }

        except TimeoutError:
            raise
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception(
                LogEvents.MODEL_CHAT_FAILED,
                endpoint_path=endpoint_path,
                error=str(e),
                latency_ms=latency_ms,
            )
            raise
