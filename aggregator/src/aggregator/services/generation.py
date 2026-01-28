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
from aggregator.clients.tunnel import TunnelClient, extract_tunnel_username, is_tunneled_url
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
        tunnel_client: TunnelClient | None = None,
    ) -> GenerationResult:
        """
        Generate a response from a SyftAI-Space model endpoint.

        User identity is derived from satellite tokens by SyftAI-Space.
        Supports both HTTP endpoints and tunneled endpoints (via MQ).

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            tunnel_client: TunnelClient for tunneled endpoints (required if model is tunneled)

        Returns:
            GenerationResult with response and metadata

        Raises:
            GenerationError: If generation fails
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        try:
            # Check if this is a tunneled endpoint
            if is_tunneled_url(model_endpoint.url):
                if tunnel_client is None:
                    raise GenerationError(
                        "Tunneled model endpoint requires response_queue credentials"
                    )

                target_username = extract_tunnel_username(model_endpoint.url)
                # Convert messages to dict format for tunnel
                messages_dict = [{"role": m.role, "content": m.content} for m in messages]

                result_dict = await tunnel_client.chat_model(
                    target_username=target_username,
                    slug=model_endpoint.slug,
                    endpoint_path=model_endpoint.path,
                    messages=messages_dict,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    transaction_token=self._get_token_for_endpoint(
                        model_endpoint, transaction_tokens
                    ),
                )

                result = GenerationResult(
                    response=result_dict["response"],
                    latency_ms=result_dict["latency_ms"],
                )
            else:
                # HTTP endpoint - use ModelClient
                result = await self.model_client.chat(
                    url=model_endpoint.url,
                    slug=model_endpoint.slug,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    tenant_name=model_endpoint.tenant_name,
                    authorization_token=self._get_token_for_endpoint(
                        model_endpoint, endpoint_tokens
                    ),
                    transaction_token=self._get_token_for_endpoint(
                        model_endpoint, transaction_tokens
                    ),
                )

            logger.info(f"Generation complete: latency={result.latency_ms}ms")
            return result

        except ModelClientError as e:
            logger.error(f"Generation failed: {e}")
            raise GenerationError(f"Model generation failed: {e}") from e
        except TimeoutError as e:
            logger.error(f"Generation timed out: {e}")
            raise GenerationError(f"Model generation timed out: {e}") from e
        except Exception as e:
            if isinstance(e, GenerationError):
                raise
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
        tunnel_client: TunnelClient | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from a SyftAI-Space model endpoint.

        User identity is derived from satellite tokens by SyftAI-Space.

        Note: Streaming through tunneled endpoints is not currently supported.
        For tunneled endpoints, this method falls back to non-streaming and
        yields the complete response as a single chunk.

        Args:
            model_endpoint: Resolved model endpoint with URL, slug, tenant info
            messages: List of conversation messages
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation
            endpoint_tokens: Mapping of owner username to satellite token for auth
            transaction_tokens: Mapping of owner username to transaction token for billing
            tunnel_client: TunnelClient for tunneled endpoints (required if model is tunneled)

        Yields:
            Response text chunks as they arrive

        Raises:
            GenerationError: If generation fails
        """
        endpoint_tokens = endpoint_tokens or {}
        transaction_tokens = transaction_tokens or {}

        try:
            # Check if this is a tunneled endpoint
            if is_tunneled_url(model_endpoint.url):
                # Streaming not supported for tunneled endpoints - fall back to non-streaming
                result = await self.generate(
                    model_endpoint=model_endpoint,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    endpoint_tokens=endpoint_tokens,
                    transaction_tokens=transaction_tokens,
                    tunnel_client=tunnel_client,
                )
                # Yield the complete response as a single chunk
                yield result.response
                return

            # HTTP endpoint - use streaming
            async for chunk in self.model_client.chat_stream(
                url=model_endpoint.url,
                slug=model_endpoint.slug,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                tenant_name=model_endpoint.tenant_name,
                authorization_token=self._get_token_for_endpoint(
                    model_endpoint, endpoint_tokens
                ),
                transaction_token=self._get_token_for_endpoint(
                    model_endpoint, transaction_tokens
                ),
            ):
                if chunk:
                    yield chunk

        except ModelClientError as e:
            logger.error(f"Stream generation failed: {e}")
            raise GenerationError(f"Model stream failed: {e}") from e
        except GenerationError:
            raise
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            raise GenerationError(f"Model stream failed: {e}") from e
