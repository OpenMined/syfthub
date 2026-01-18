"""Client for interacting with SyftAI-Space model endpoints."""

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from aggregator.observability import get_correlation_id, get_logger
from aggregator.observability.constants import CORRELATION_ID_HEADER, LogEvents
from aggregator.schemas.internal import GenerationResult
from aggregator.schemas.requests import Message

logger = get_logger(__name__)


class ModelClientError(Exception):
    """Error from model endpoint."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ModelClient:
    """Client for calling SyftAI-Space model endpoints.

    This client is adapted to work with SyftAI-Space's unified endpoint API:
    POST /api/v1/endpoints/{slug}/query

    The endpoint must be configured with response_type that includes "summary"
    (either "summary" or "both") to return LLM-generated content.
    """

    def __init__(self, timeout: float = 120.0):
        self.timeout = httpx.Timeout(timeout)

    async def chat(
        self,
        url: str,
        slug: str,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tenant_name: str | None = None,
        authorization_token: str | None = None,
        transaction_token: str | None = None,
    ) -> GenerationResult:
        """
        Send messages to a SyftAI-Space model endpoint and get a response.

        User identity is derived from the satellite token by SyftAI-Space.

        Args:
            url: Base URL of the SyftAI-Space instance
            slug: Endpoint slug for the API path
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            tenant_name: Tenant name for X-Tenant-Name header (optional)
            authorization_token: Satellite token for Authorization header (optional)
            transaction_token: Transaction token for billing authorization (optional)

        Returns:
            GenerationResult with response text and metadata

        Raises:
            ModelClientError: If the request fails
        """
        start_time = time.perf_counter()

        # Build SyftAI-Space endpoint URL
        chat_url = f"{url.rstrip('/')}/api/v1/endpoints/{slug}/query"

        # Convert messages to SyftAI-Space format
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        # Build SyftAI-Space compatible request body
        # User identity is derived from the satellite token, not the request body
        request_data: dict[str, Any] = {
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "stop_sequences": [],  # Don't stop on newlines - allow complete responses
        }

        # Include transaction token in payload for billing authorization
        if transaction_token:
            request_data["transaction_token"] = transaction_token

        # Build headers with correlation ID for request tracing
        headers: dict[str, str] = {"Content-Type": "application/json"}
        correlation_id = get_correlation_id()
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        if authorization_token:
            headers["Authorization"] = f"Bearer {authorization_token}"

        logger.debug(
            LogEvents.MODEL_QUERY_STARTED,
            chat_url=chat_url,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    chat_url,
                    json=request_data,
                    headers=headers,
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code == 403:
                    error_detail = self._extract_error_detail(response)
                    logger.warning(
                        LogEvents.MODEL_QUERY_FAILED,
                        status_code=403,
                        error=error_detail,
                        latency_ms=latency_ms,
                    )
                    raise ModelClientError(
                        f"Model access denied: {error_detail}",
                        status_code=403,
                    )

                if response.status_code != 200:
                    error_detail = self._extract_error_detail(response)
                    logger.warning(
                        LogEvents.MODEL_QUERY_FAILED,
                        status_code=response.status_code,
                        error=error_detail,
                        latency_ms=latency_ms,
                    )
                    raise ModelClientError(
                        f"Model request failed: HTTP {response.status_code} - {error_detail}",
                        status_code=response.status_code,
                    )

                data = response.json()
                response_text = self._extract_syftai_response(data)
                usage = self._extract_usage(data)

                logger.info(
                    LogEvents.MODEL_QUERY_COMPLETED,
                    latency_ms=latency_ms,
                    usage=usage,
                )

                return GenerationResult(
                    response=response_text,
                    latency_ms=latency_ms,
                    usage=usage,
                )

            except httpx.TimeoutException as e:
                logger.warning(LogEvents.CHAT_GENERATION_TIMEOUT, chat_url=chat_url)
                raise ModelClientError("Model request timed out") from e
            except httpx.RequestError as e:
                logger.warning(
                    LogEvents.MODEL_QUERY_FAILED, chat_url=chat_url, error=str(e)
                )
                raise ModelClientError(f"Network error: {e}") from e

    async def chat_stream(
        self,
        url: str,
        slug: str,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        tenant_name: str | None = None,
        authorization_token: str | None = None,
        transaction_token: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Send messages to a SyftAI-Space model endpoint and stream the response.

        Note: SyftAI-Space streaming may not be fully implemented. This method
        attempts to handle both streaming and non-streaming responses gracefully.

        User identity is derived from the satellite token by SyftAI-Space.

        Args:
            url: Base URL of the SyftAI-Space instance
            slug: Endpoint slug for the API path
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            tenant_name: Tenant name for X-Tenant-Name header (optional)
            authorization_token: Satellite token for Authorization header (optional)
            transaction_token: Transaction token for billing authorization (optional)

        Yields:
            Response text chunks as they arrive
        """
        # Build SyftAI-Space endpoint URL
        chat_url = f"{url.rstrip('/')}/api/v1/endpoints/{slug}/query"

        # Convert messages to SyftAI-Space format
        formatted_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        # Build SyftAI-Space compatible request body
        # User identity is derived from the satellite token, not the request body
        request_data: dict[str, Any] = {
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,  # Request streaming
            "stop_sequences": [],  # Don't stop on newlines - allow complete responses
        }

        # Include transaction token in payload for billing authorization
        if transaction_token:
            request_data["transaction_token"] = transaction_token

        # Build headers with correlation ID for request tracing
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers[CORRELATION_ID_HEADER] = correlation_id
        if tenant_name:
            headers["X-Tenant-Name"] = tenant_name
        if authorization_token:
            headers["Authorization"] = f"Bearer {authorization_token}"

        logger.debug(
            LogEvents.SSE_STREAM_STARTED,
            chat_url=chat_url,
            max_tokens=max_tokens,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    chat_url,
                    json=request_data,
                    headers=headers,
                ) as response:
                    if response.status_code == 403:
                        error_text = await response.aread()
                        raise ModelClientError(
                            f"Model access denied: {error_text[:200]}",
                            status_code=403,
                        )

                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ModelClientError(
                            f"Model stream failed: HTTP {response.status_code} - {error_text[:200]}",
                            status_code=response.status_code,
                        )

                    # Check content type to determine if we got streaming or non-streaming
                    content_type = response.headers.get("content-type", "")

                    if "text/event-stream" in content_type:
                        # Handle SSE streaming
                        async for line in response.aiter_lines():
                            chunk = self._parse_sse_line(line)
                            if chunk:
                                yield chunk
                    else:
                        # SyftAI-Space returned non-streaming response
                        # Read the full response and yield the content
                        body = await response.aread()
                        try:
                            data = json.loads(body)
                            response_text = self._extract_syftai_response(data)
                            if response_text:
                                yield response_text
                        except json.JSONDecodeError:
                            # Plain text response
                            yield body.decode("utf-8")

            except httpx.TimeoutException as e:
                logger.warning(LogEvents.SSE_STREAM_FAILED, chat_url=chat_url, error="timeout")
                raise ModelClientError("Model stream timed out") from e
            except httpx.RequestError as e:
                logger.warning(
                    LogEvents.SSE_STREAM_FAILED, chat_url=chat_url, error=str(e)
                )
                raise ModelClientError(f"Network error during stream: {e}") from e

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract error detail from response."""
        try:
            data = response.json()
            return data.get("detail", response.text[:200])
        except Exception:
            return response.text[:200]

    def _extract_syftai_response(self, data: dict[str, Any]) -> str:
        """Extract response text from SyftAI-Space QueryEndpointResponse.

        SyftAI-Space returns:
        {
            "summary": {
                "id": str,
                "model": str,
                "message": {"role": "assistant", "content": str, "tokens": int},
                "finish_reason": str,
                "usage": {...},
                "cost": float,
                "provider_info": {...}
            } | null,
            "references": {...} | null
        }

        We extract from summary.message.content.
        """
        # Extract summary from SyftAI-Space response
        summary = data.get("summary")
        if not summary:
            logger.debug("No summary in SyftAI-Space response")
            return ""

        # Extract message content
        message = summary.get("message", {})
        if isinstance(message, dict):
            return message.get("content", "")
        if isinstance(message, str):
            return message

        return ""

    def _extract_usage(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract token usage from SyftAI-Space response."""
        summary = data.get("summary")
        if not summary:
            return None

        usage = summary.get("usage")
        if usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        return None

    def _parse_sse_line(self, line: str) -> str | None:
        """Parse a Server-Sent Events line to extract content."""
        line = line.strip()

        if not line:
            return None

        # Handle "data: " prefix
        if line.startswith("data: "):
            data = line[6:]

            # Check for stream end
            if data == "[DONE]":
                return None

            try:
                parsed = json.loads(data)

                # SyftAI-Space streaming format (if implemented)
                if "summary" in parsed:
                    summary = parsed["summary"]
                    if summary:
                        message = summary.get("message", {})
                        if isinstance(message, dict):
                            return message.get("content")

                # OpenAI-style delta (for compatibility)
                if "choices" in parsed:
                    choices = parsed["choices"]
                    if choices and len(choices) > 0:
                        delta = choices[0].get("delta", {})
                        return delta.get("content")

                # Simple content field
                if "content" in parsed:
                    return parsed["content"]

                if "text" in parsed:
                    return parsed["text"]

            except json.JSONDecodeError:
                # Plain text data
                return data

        return None
