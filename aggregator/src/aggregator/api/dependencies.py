"""FastAPI dependencies for the aggregator API.

TODO: Satellite Token Integration
---------------------------------
Currently the aggregator receives user tokens but does not forward them to
SyftAI-Space endpoints. When SyftAI-Space implements satellite token support:

1. The `get_optional_token()` function extracts Bearer tokens from requests
2. These tokens should be passed through the orchestrator to the clients
3. DataSourceClient and ModelClient should include Authorization headers
4. SyftAI-Space will validate tokens and check user permissions

See also:
- aggregator/clients/data_source.py - needs Authorization header
- aggregator/clients/model.py - needs Authorization header
- syfthub backend token endpoint - generates satellite tokens
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from aggregator.clients import DataSourceClient, ModelClient, TunnelClient
from aggregator.core.config import get_settings
from aggregator.services import (
    GenerationService,
    Orchestrator,
    PromptBuilder,
    RetrievalService,
)


@lru_cache
def get_data_source_client() -> DataSourceClient:
    """Get the data source client singleton."""
    settings = get_settings()
    return DataSourceClient(timeout=settings.retrieval_timeout)


@lru_cache
def get_model_client() -> ModelClient:
    """Get the model client singleton."""
    settings = get_settings()
    return ModelClient(timeout=settings.generation_timeout)


@lru_cache
def get_tunnel_client() -> TunnelClient:
    """Get the tunnel client singleton for MQ-based communication."""
    settings = get_settings()
    return TunnelClient(
        syfthub_url=settings.syfthub_url,
        timeout=settings.retrieval_timeout,
    )


def get_prompt_builder() -> PromptBuilder:
    """Get a prompt builder instance."""
    return PromptBuilder()


def get_retrieval_service(
    data_source_client: Annotated[DataSourceClient, Depends(get_data_source_client)],
    tunnel_client: Annotated[TunnelClient, Depends(get_tunnel_client)],
) -> RetrievalService:
    """Get the retrieval service with tunnel support."""
    return RetrievalService(data_source_client, tunnel_client)


def get_generation_service(
    model_client: Annotated[ModelClient, Depends(get_model_client)],
    tunnel_client: Annotated[TunnelClient, Depends(get_tunnel_client)],
) -> GenerationService:
    """Get the generation service with tunnel support."""
    return GenerationService(model_client, tunnel_client)


def get_orchestrator(
    retrieval_service: Annotated[RetrievalService, Depends(get_retrieval_service)],
    generation_service: Annotated[GenerationService, Depends(get_generation_service)],
    prompt_builder: Annotated[PromptBuilder, Depends(get_prompt_builder)],
) -> Orchestrator:
    """Get the orchestrator service."""
    return Orchestrator(
        retrieval_service=retrieval_service,
        generation_service=generation_service,
        prompt_builder=prompt_builder,
    )


def get_optional_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """Extract the bearer token from Authorization header if present."""
    if not authorization:
        return None

    # Handle "Bearer <token>" format
    if authorization.lower().startswith("bearer "):
        return authorization[7:]

    return authorization
