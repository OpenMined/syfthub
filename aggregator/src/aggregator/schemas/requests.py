"""Request schemas for the aggregator API."""

from typing import Literal

from pydantic import BaseModel, Field


class EndpointRef(BaseModel):
    """Reference to an endpoint with its URL for direct access."""

    url: str = Field(..., description="Base URL of the endpoint (aggregator appends /chat or /query)")
    name: str = Field(default="", description="Display name for attribution/logging")


class ChatRequest(BaseModel):
    """Request to the aggregator chat endpoint."""

    prompt: str = Field(..., min_length=1, description="The user's question or prompt")
    model: EndpointRef = Field(..., description="Model endpoint with URL")
    data_sources: list[EndpointRef] = Field(
        default_factory=list,
        description="List of data source endpoints with URLs",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of documents per source")
    stream: bool = Field(default=False, description="Enable streaming response")


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
