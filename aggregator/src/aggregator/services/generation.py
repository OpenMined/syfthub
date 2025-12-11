"""Generation service for calling model endpoints."""

import logging
from collections.abc import AsyncGenerator

from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.schemas.internal import GenerationResult
from aggregator.schemas.requests import Message

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Error during generation."""

    pass


class GenerationService:
    """Service for generating responses from model endpoints."""

    def __init__(self, model_client: ModelClient):
        self.model_client = model_client

    async def generate(
        self,
        model_url: str,
        messages: list[Message],
    ) -> GenerationResult:
        """
        Generate a response from the model endpoint.

        Args:
            model_url: URL of the model endpoint
            messages: List of conversation messages

        Returns:
            GenerationResult with response and metadata

        Raises:
            GenerationError: If generation fails
        """
        try:
            result = await self.model_client.chat(url=model_url, messages=messages)
            logger.info(f"Generation complete: latency={result.latency_ms}ms")
            return result

        except ModelClientError as e:
            logger.error(f"Generation failed: {e}")
            raise GenerationError(f"Model generation failed: {e}") from e

    async def generate_stream(
        self,
        model_url: str,
        messages: list[Message],
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from the model endpoint.

        Args:
            model_url: URL of the model endpoint
            messages: List of conversation messages

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails
        """
        try:
            async for chunk in self.model_client.chat_stream(url=model_url, messages=messages):
                if chunk:
                    yield chunk

        except ModelClientError as e:
            logger.error(f"Stream generation failed: {e}")
            raise GenerationError(f"Model stream failed: {e}") from e
