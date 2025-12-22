"""Generation service for calling SyftAI-Space model endpoints.

TODO: Streaming Support
----------------------
Currently SyftAI-Space does not implement model streaming - it accepts the
`stream` parameter but always returns a synchronous JSON response. The
`generate_stream` method in this service is preserved for future use when
SyftAI-Space adds streaming support.

To enable streaming:
1. Wait for SyftAI-Space to implement the `stream=true` parameter properly
2. Set AGGREGATOR_MODEL_STREAMING_ENABLED=true in environment
3. The orchestrator will then use generate_stream() instead of generate()
"""

import logging
from collections.abc import AsyncGenerator

from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.schemas.internal import GenerationResult, ResolvedEndpoint
from aggregator.schemas.requests import Message

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Error during generation."""

    pass


class GenerationService:
    """Service for generating responses from SyftAI-Space model endpoints."""

    def __init__(self, model_client: ModelClient):
        self.model_client = model_client

    async def generate(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        user_email: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> GenerationResult:
        """
        Generate a response from a SyftAI-Space model endpoint.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            user_email: User email for SyftAI-Space visibility/policy checks
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation

        Returns:
            GenerationResult with response and metadata

        Raises:
            GenerationError: If generation fails
        """
        try:
            result = await self.model_client.chat(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                user_email=user_email,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
            )
            logger.info(f"Generation complete: latency={result.latency_ms}ms")
            return result

        except ModelClientError as e:
            logger.error(f"Generation failed: {e}")
            raise GenerationError(f"Model generation failed: {e}") from e

    async def generate_stream(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        user_email: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from a SyftAI-Space model endpoint.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            user_email: User email for SyftAI-Space visibility/policy checks
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails
        """
        try:
            async for chunk in self.model_client.chat_stream(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                user_email=user_email,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
            ):
                if chunk:
                    yield chunk

        except ModelClientError as e:
            logger.error(f"Stream generation failed: {e}")
            raise GenerationError(f"Model stream failed: {e}") from e
