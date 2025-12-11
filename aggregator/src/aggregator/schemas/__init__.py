"""Schemas package - request/response models for the aggregator."""

from aggregator.schemas.internal import (
    AggregatedContext,
    GenerationResult,
    ResolvedEndpoint,
    RetrievalResult,
)
from aggregator.schemas.requests import (
    ChatCompletionRequest,
    ChatRequest,
    EndpointRef,
    Message,
    QueryRequest,
)
from aggregator.schemas.responses import (
    ChatCompletionResponse,
    ChatResponse,
    Document,
    ErrorResponse,
    QueryResponse,
    ResponseMetadata,
    SourceInfo,
)

__all__ = [
    # Requests
    "ChatRequest",
    "EndpointRef",
    "Message",
    "QueryRequest",
    "ChatCompletionRequest",
    # Responses
    "ChatResponse",
    "Document",
    "QueryResponse",
    "SourceInfo",
    "ResponseMetadata",
    "ChatCompletionResponse",
    "ErrorResponse",
    # Internal
    "ResolvedEndpoint",
    "RetrievalResult",
    "AggregatedContext",
    "GenerationResult",
]
