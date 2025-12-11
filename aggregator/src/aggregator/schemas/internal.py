"""Internal DTOs used within the aggregator service."""

from typing import Literal

from pydantic import BaseModel, Field

from aggregator.schemas.responses import Document


class ResolvedEndpoint(BaseModel):
    """An endpoint resolved from SyftHub with connection details."""

    path: str = Field(..., description="Endpoint path (owner/slug)")
    url: str = Field(..., description="URL to reach the endpoint")
    endpoint_type: Literal["model", "data_source"] = Field(..., description="Type of endpoint")
    name: str = Field(..., description="Display name of the endpoint")


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
