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

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from aggregator.clients.model import ModelClient, ModelClientError
from aggregator.clients.nats_transport import (
    NATSTransportError,
    extract_tunnel_username,
    is_tunneling_url,
)
from aggregator.schemas.internal import GenerationResult, ResolvedEndpoint
from aggregator.schemas.requests import Message

if TYPE_CHECKING:
    from aggregator.clients.nats_transport import NATSTransport

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Error during generation."""

    pass


class GenerationService:
    """Service for generating responses from SyftAI-Space model endpoints."""

    def __init__(
        self,
        model_client: ModelClient,
        nats_transport: NATSTransport | None = None,
    ):
        self.model_client = model_client
        self.nats_transport = nats_transport

    def _get_token_for_endpoint(
        self, endpoint: ResolvedEndpoint, token_mapping: dict[str, str]
    ) -> str | None:
        """Get a token for an endpoint based on its owner username."""
        if endpoint.owner_username and endpoint.owner_username in token_mapping:
            return token_mapping[endpoint.owner_username]
        return None

    async def generate(
        self,
        model_endpoint: ResolvedEndpoint,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
        peer_channel: str | None = None,
    ) -> GenerationResult:
        """
        Generate a response from a SyftAI-Space model endpoint.

        Routes through NATS for tunneling endpoints, HTTP for standard endpoints.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            peer_channel: Peer channel for NATS reply (required for tunneling endpoints)

        Returns:
            GenerationResult with response and metadata

        Raises:
            GenerationError: If generation fails
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        # Route through NATS for tunneling endpoints
        if is_tunneling_url(model_endpoint.url) and self.nats_transport and peer_channel:
            try:
                target_username = extract_tunnel_username(model_endpoint.url)
                formatted_messages = [
                    {"role": msg.role, "content": msg.content} for msg in messages
                ]
                result = await self.nats_transport.query_model(
                    target_username=target_username,
                    slug=model_endpoint.slug,
                    messages=formatted_messages,
                    peer_channel=peer_channel,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    transaction_token=self._get_token_for_endpoint(
                        model_endpoint, transaction_tokens
                    ),
                    satellite_token=self._get_token_for_endpoint(
                        model_endpoint, endpoint_tokens
                    ),
                )
                logger.info(f"NATS generation complete: latency={result.latency_ms}ms")
                return result
            except NATSTransportError as e:
                logger.error(f"NATS generation failed: {e}")
                raise GenerationError(f"Model generation via NATS failed: {e}") from e

        # Standard HTTP request
        try:
            result = await self.model_client.chat(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
                authorization_token=self._get_token_for_endpoint(model_endpoint, endpoint_tokens),
                transaction_token=self._get_token_for_endpoint(model_endpoint, transaction_tokens),
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
        max_tokens: int = 1024,
        temperature: float = 0.7,
        endpoint_tokens: dict[str, str] | None = None,
        transaction_tokens: dict[str, str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from a SyftAI-Space model endpoint.

        User identity is derived from satellite tokens by SyftAI-Space.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}
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
