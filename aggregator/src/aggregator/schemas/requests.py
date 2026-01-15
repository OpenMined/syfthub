"""Request schemas for the aggregator API."""

from typing import Literal

from pydantic import BaseModel, Field


class EndpointRef(BaseModel):
    """Reference to a SyftAI-Space endpoint with connection details.

    The aggregator uses these details to construct the proper API call:
    - URL: {url}/api/v1/endpoints/{slug}/query
    - Header: X-Tenant-Name: {tenant_name} (if provided)
    - Header: Authorization: Bearer {token} (from endpoint_tokens mapping)
    """

    url: str = Field(
        ...,
        description="Base URL of the SyftAI-Space instance (e.g., 'http://localhost:8080')",
    )
    slug: str = Field(
        ...,
        description="Endpoint slug for the SyftAI-Space API path",
    )
    name: str = Field(
        default="",
        description="Display name for attribution/logging",
    )
    tenant_name: str | None = Field(
        default=None,
        description="Tenant name for X-Tenant-Name header (required when multi-tenancy is enabled)",
    )
    owner_username: str | None = Field(
        default=None,
        description="Owner's username - used to lookup satellite token from endpoint_tokens",
    )


class ChatRequest(BaseModel):
    """Request to the aggregator chat endpoint.

    This schema is designed for stateless operation - all required information
    for accessing SyftAI-Space endpoints must be provided in each request.

    Authentication:
        The endpoint_tokens field maps owner usernames to satellite tokens.
        Each endpoint's owner_username is used to lookup its token from this mapping.
        The aggregator forwards these tokens in Authorization headers to SyftAI-Space.
        User identity is derived from the satellite tokens (not passed separately).

    Billing:
        The transaction_tokens field maps owner usernames to accounting transaction tokens.
        These tokens authorize endpoint owners to charge the user for usage.
        The aggregator forwards these tokens to SyftAI-Space endpoints via headers.
    """

    prompt: str = Field(..., min_length=1, description="The user's question or prompt")
    model: EndpointRef = Field(..., description="Model endpoint reference with URL and slug")
    data_sources: list[EndpointRef] = Field(
        default_factory=list,
        description="List of data source endpoint references",
    )
    endpoint_tokens: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of owner username to satellite token for authentication",
    )
    transaction_tokens: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of owner username to transaction token for billing authorization",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of documents to retrieve per source (maps to 'limit' in SyftAI-Space)",
    )
    stream: bool = Field(default=False, description="Enable streaming response")
    # LLM parameters passed to SyftAI-Space
    max_tokens: int = Field(
        default=1024,
        ge=1,
        description="Maximum tokens for LLM generation",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM generation",
    )
    similarity_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for retrieved documents",
    )


class Message(BaseModel):
    """A message in a chat conversation."""

    role: Literal["system", "user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    """Request to a data source endpoint's /query interface."""

    query: str = Field(..., description="The search query")
    top_k: int = Field(default=5, ge=1, description="Number of documents to retrieve")


class ChatCompletionRequest(BaseModel):
    """Request to a model endpoint's /chat interface."""

    messages: list[Message] = Field(..., description="List of messages in the conversation")
    stream: bool = Field(default=False, description="Enable streaming response")
