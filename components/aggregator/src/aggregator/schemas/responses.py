"""Response schemas for the aggregator API."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A document retrieved from a data source."""

    content: str = Field(..., description="The document content")
    score: float = Field(default=0.0, description="Relevance score")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class QueryResponse(BaseModel):
    """Response from a data source endpoint's /query interface."""

    documents: list[Document] = Field(default_factory=list)


class SourceInfo(BaseModel):
    """Information about a data source used in the response."""

    path: str = Field(..., description="Endpoint path (owner/slug)")
    documents_retrieved: int = Field(..., description="Number of documents retrieved")
    status: Literal["success", "error", "timeout"] = Field(..., description="Query status")
    error_message: str | None = Field(default=None, description="Error message if failed")


class DocumentSource(BaseModel):
    """A document source entry with endpoint path and content.

    Used in the sources dict of ChatResponse, keyed by document title.
    """

    slug: str = Field(..., description="Endpoint path (owner/slug) where document was retrieved")
    content: str = Field(..., description="The actual document content")


class ResponseMetadata(BaseModel):
    """Metadata about the aggregator response."""

    retrieval_time_ms: int = Field(..., description="Time spent retrieving documents")
    generation_time_ms: int = Field(..., description="Time spent generating response")
    total_time_ms: int = Field(..., description="Total request time")


class TokenUsage(BaseModel):
    """Token usage information from model generation."""

    prompt_tokens: int = Field(default=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(default=0, description="Number of tokens in the completion")
    total_tokens: int = Field(default=0, description="Total tokens used")


class ChatResponse(BaseModel):
    """Response from the aggregator chat endpoint."""

    response: str = Field(..., description="The generated response")
    sources: dict[str, DocumentSource] = Field(
        default_factory=dict,
        description="Retrieved documents keyed by title, with endpoint slug and content",
    )
    retrieval_info: list[SourceInfo] = Field(
        default_factory=list,
        description="Metadata about each data source retrieval (status, count, errors)",
    )
    metadata: ResponseMetadata = Field(..., description="Timing metadata")
    usage: TokenUsage | None = Field(default=None, description="Token usage if available")
    profit_share: dict[str, float] | None = Field(
        default=None,
        description="Normalized contribution scores per source (owner/slug to fraction 0-1)",
    )


class ChatCompletionResponse(BaseModel):
    """Response from a model endpoint's /chat interface."""

    message: dict[str, Any] = Field(..., description="The assistant's message")
    usage: dict[str, Any] | None = Field(default=None, description="Token usage information")


class ErrorResponse(BaseModel):
    """Error response from the aggregator."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")
