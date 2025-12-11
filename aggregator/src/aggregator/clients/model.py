"""Client for interacting with model endpoints."""

import json
import logging
import time
from collections.abc import AsyncGenerator

import httpx

from aggregator.schemas.internal import GenerationResult
from aggregator.schemas.requests import ChatCompletionRequest, Message

logger = logging.getLogger(__name__)


class ModelClientError(Exception):
    """Error from model endpoint."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ModelClient:
    """Client for calling model endpoints."""

    def __init__(self, timeout: float = 120.0):
        self.timeout = httpx.Timeout(timeout)

    async def chat(
        self,
        url: str,
        messages: list[Message],
    ) -> GenerationResult:
        """
        Send messages to a model endpoint and get a response.

        Args:
            url: Base URL of the model endpoint
            messages: List of conversation messages

        Returns:
            GenerationResult with response text and metadata

        Raises:
            ModelClientError: If the request fails
        """
        start_time = time.perf_counter()

        chat_url = f"{url.rstrip('/')}/chat"
        request_data = ChatCompletionRequest(
            messages=messages,
            stream=False,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    chat_url,
                    json=request_data.model_dump(),
                    headers={"Content-Type": "application/json"},
                )

                latency_ms = int((time.perf_counter() - start_time) * 1000)

                if response.status_code != 200:
                    raise ModelClientError(
                        f"Model request failed: HTTP {response.status_code}",
                        status_code=response.status_code,
                    )

                data = response.json()
                response_text = self._extract_response_text(data)

                logger.info(f"Model chat success: latency={latency_ms}ms")

                return GenerationResult(
                    response=response_text,
                    latency_ms=latency_ms,
                    usage=data.get("usage"),
                )

            except httpx.TimeoutException as e:
                raise ModelClientError("Model request timed out") from e
            except httpx.RequestError as e:
                raise ModelClientError(f"Network error: {e}") from e

    async def chat_stream(
        self,
        url: str,
        messages: list[Message],
    ) -> AsyncGenerator[str, None]:
        """
        Send messages to a model endpoint and stream the response.

        Args:
            url: Base URL of the model endpoint
            messages: List of conversation messages

        Yields:
            Response text chunks as they arrive
        """
        chat_url = f"{url.rstrip('/')}/chat"
        request_data = ChatCompletionRequest(
            messages=messages,
            stream=True,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    chat_url,
                    json=request_data.model_dump(),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                    },
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ModelClientError(
                            f"Model stream failed: HTTP {response.status_code} - {error_text[:200]}",
                            status_code=response.status_code,
                        )

                    async for line in response.aiter_lines():
                        chunk = self._parse_sse_line(line)
                        if chunk:
                            yield chunk

            except httpx.TimeoutException as e:
                raise ModelClientError("Model stream timed out") from e
            except httpx.RequestError as e:
                raise ModelClientError(f"Network error during stream: {e}") from e

    def _extract_response_text(self, data: dict) -> str:
        """Extract response text from model response."""
        # Handle OpenAI-style response
        if "choices" in data:
            choices = data["choices"]
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                return message.get("content", "")

        # Handle simplified response format
        if "message" in data:
            message = data["message"]
            if isinstance(message, dict):
                return message.get("content", "")
            if isinstance(message, str):
                return message

        # Handle direct response
        if "response" in data:
            return data["response"]

        if "content" in data:
            return data["content"]

        logger.warning(f"Could not extract response from model output: {list(data.keys())}")
        return ""

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

                # OpenAI-style delta
                if "choices" in parsed:
                    choices = parsed["choices"]
                    if choices and len(choices) > 0:
                        delta = choices[0].get("delta", {})
                        return delta.get("content")

                # Simple content
                if "content" in parsed:
                    return parsed["content"]

                if "text" in parsed:
                    return parsed["text"]

            except json.JSONDecodeError:
                # Plain text data
                return data

        return None
