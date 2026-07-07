"""FastAPI dependencies for the aggregator API."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header

from aggregator.clients import DataSourceClient, ErrorReporter, ModelClient
from aggregator.clients.nats_transport import NATSTransport
from aggregator.core.config import get_settings
from aggregator.services import (
    GenerationService,
    Orchestrator,
    PromptBuilder,
    RetrievalService,
)


@lru_cache
def get_error_reporter() -> ErrorReporter:
    """Get the error reporter singleton."""
    settings = get_settings()
    return ErrorReporter(backend_url=settings.syfthub_url)


@lru_cache
def get_data_source_client() -> DataSourceClient:
    """Get the data source client singleton."""
    settings = get_settings()
    return DataSourceClient(
        timeout=settings.retrieval_timeout,
        error_reporter=get_error_reporter(),
    )


@lru_cache
def get_model_client() -> ModelClient:
    """Get the model client singleton."""
    settings = get_settings()
    return ModelClient(
        timeout=settings.generation_timeout,
        error_reporter=get_error_reporter(),
    )


@lru_cache
def get_nats_transport() -> NATSTransport | None:
    """Get the NATS transport singleton (None if NATS is not configured)."""
    settings = get_settings()
    if not settings.nats_auth_token:
        return None
    return NATSTransport(
        nats_url=settings.nats_url,
        nats_auth_token=settings.nats_auth_token,
        default_timeout=settings.nats_tunnel_timeout,
    )


def get_prompt_builder() -> PromptBuilder:
    """Get a prompt builder instance."""
    return PromptBuilder()


def get_retrieval_service(
    data_source_client: Annotated[DataSourceClient, Depends(get_data_source_client)],
    nats_transport: Annotated[NATSTransport | None, Depends(get_nats_transport)],
) -> RetrievalService:
    """Get the retrieval service."""
    return RetrievalService(data_source_client, nats_transport=nats_transport)


def get_generation_service(
    model_client: Annotated[ModelClient, Depends(get_model_client)],
    nats_transport: Annotated[NATSTransport | None, Depends(get_nats_transport)],
) -> GenerationService:
    """Get the generation service."""
    return GenerationService(model_client, nats_transport=nats_transport)


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
