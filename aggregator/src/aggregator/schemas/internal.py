"""Internal DTOs used within the aggregator service."""

from typing import Literal

from pydantic import BaseModel, Field

from aggregator.schemas.responses import Document


class ResolvedEndpoint(BaseModel):
    """An endpoint with connection details for SyftAI-Space.

    This is the internal representation used after converting from EndpointRef.
    Contains all information needed to make API calls to SyftAI-Space.
    """

    path: str = Field(..., description="Display path/name for logging")
    url: str = Field(..., description="Base URL of the SyftAI-Space instance")
    slug: str = Field(..., description="Endpoint slug for the API path")
    endpoint_type: Literal["model", "data_source"] = Field(..., description="Type of endpoint")
    name: str = Field(..., description="Display name of the endpoint")
    tenant_name: str | None = Field(
        default=None,
        description="Tenant name for X-Tenant-Name header",
    )


class RetrievalResult(BaseModel):
    """Result of querying a single data source."""

    endpoint_path: str = Field(..., description="Path of the data source")
    documents: list[Document] = Field(default_factory=list, description="Retrieved documents")
    status: Literal["success", "error", "timeout"] = Field(..., description="Query status")
    error_message: str | None = Field(default=None, description="Error message if failed")
    latency_ms: int = Field(..., description="Query latency in milliseconds")


class AggregatedContext(BaseModel):
    """Context aggregated from multiple data sources."""

    documents: list[Document] = Field(default_factory=list, description="All retrieved documents")
    retrieval_results: list[RetrievalResult] = Field(
        default_factory=list, description="Results from each data source"
    )
    total_latency_ms: int = Field(..., description="Total retrieval time")


class GenerationResult(BaseModel):
    """Result of calling the model endpoint."""

    response: str = Field(..., description="Generated response text")
    latency_ms: int = Field(..., description="Generation time in milliseconds")
    usage: dict | None = Field(default=None, description="Token usage if available")
