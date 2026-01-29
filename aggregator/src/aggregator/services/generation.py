"""Generation service for calling SyftAI-Space model endpoints.

Supports both HTTP endpoints and tunneled endpoints (via MQ).

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
from aggregator.clients.tunnel import (
    TunnelClient,
    TunnelClientError,
    extract_tunnel_username,
    is_tunneled_url,
)
from aggregator.schemas.internal import GenerationResult, ResolvedEndpoint
from aggregator.schemas.requests import Message

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Error during generation."""

    pass


class GenerationService:
    """Service for generating responses from SyftAI-Space model endpoints.

    Supports both HTTP endpoints and tunneled endpoints (via MQ).
    """

    def __init__(
        self,
        model_client: ModelClient,
        tunnel_client: TunnelClient | None = None,
    ):
        self.model_client = model_client
        self.tunnel_client = tunnel_client

    def _get_token_for_endpoint(
        self, endpoint: ResolvedEndpoint, token_mapping: dict[str, str]
    ) -> str | None:
        """Get a token for an endpoint based on its owner username."""
        if endpoint.owner_username and endpoint.owner_username in token_mapping:
            return token_mapping[endpoint.owner_username]
        return None

    async def _query_model(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        max_tokens: int,
        temperature: float,
        endpoint_tokens: dict[str, str],
        transaction_tokens: dict[str, str],
        response_queue_id: str | None,
        response_queue_token: str | None,
    ) -> GenerationResult:
        """Query a model endpoint, routing to HTTP or tunnel as appropriate."""
        if is_tunneled_url(model_endpoint.url):
            # Tunneled endpoint - use MQ
            if not self.tunnel_client:
                raise GenerationError("Tunnel client not configured")
            if not response_queue_id or not response_queue_token:
                raise GenerationError(
                    "Tunneled endpoints require response_queue_id and response_queue_token"
                )

            satellite_token = self._get_token_for_endpoint(model_endpoint, endpoint_tokens)
            if not satellite_token:
                raise GenerationError("Satellite token required for tunneled endpoint")

            # Convert Message objects to dicts for tunnel protocol
            messages_dict = [{"role": m.role, "content": m.content} for m in messages]

            return await self.tunnel_client.query_model(
                target_username=extract_tunnel_username(model_endpoint.url),
                endpoint_slug=model_endpoint.slug,
                messages=messages_dict,
                max_tokens=max_tokens,
                temperature=temperature,
                satellite_token=satellite_token,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
                endpoint_path=model_endpoint.path,
                transaction_token=self._get_token_for_endpoint(model_endpoint, transaction_tokens),
            )
        else:
            # HTTP endpoint
            return await self.model_client.chat(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
                authorization_token=self._get_token_for_endpoint(model_endpoint, endpoint_tokens),
                transaction_token=self._get_token_for_endpoint(model_endpoint, transaction_tokens),
            )

    async def generate(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        response_queue_id: str | None = None,
        response_queue_token: str | None = None,
    ) -> GenerationResult:
        """
        Generate a response from a SyftAI-Space model endpoint.

        Supports both HTTP endpoints and tunneled endpoints (via MQ).
        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            response_queue_id: Reserved queue ID for tunneled responses
            response_queue_token: Token for accessing the reserved queue

        Returns:
            GenerationResult with response and metadata

        Raises:
            GenerationError: If generation fails
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}
        try:
            result = await self._query_model(
                model_endpoint=model_endpoint,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                endpoint_tokens=endpoint_tokens,
                transaction_tokens=transaction_tokens,
                response_queue_id=response_queue_id,
                response_queue_token=response_queue_token,
            )
            logger.info(f"Generation complete: latency={result.latency_ms}ms")
            return result

        except ModelClientError as e:
            logger.error(f"Generation failed: {e}")
            raise GenerationError(f"Model generation failed: {e}") from e

        except TunnelClientError as e:
            logger.error(f"Tunnel generation failed: {e}")
            raise GenerationError(f"Tunneled model generation failed: {e}") from e

    async def generate_stream(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        response_queue_id: str | None = None,
        response_queue_token: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from a SyftAI-Space model endpoint.

        Note: Streaming is not yet supported for tunneled endpoints.
        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            response_queue_id: Reserved queue ID for tunneled responses (not yet supported)
            response_queue_token: Token for accessing the reserved queue (not yet supported)

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails or tunneled streaming is attempted
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        # Streaming not supported for tunneled endpoints yet
        if is_tunneled_url(model_endpoint.url):
            raise GenerationError("Streaming is not yet supported for tunneled endpoints")

        try:
            async for chunk in self.model_client.chat_stream(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
                authorization_token=self._get_token_for_endpoint(model_endpoint, endpoint_tokens),
                transaction_token=self._get_token_for_endpoint(model_endpoint, transaction_tokens),
            ):
                if chunk:
                    yield chunk

        except ModelClientError as e:
            logger.error(f"Stream generation failed: {e}")
            raise GenerationError(f"Model stream failed: {e}") from e
