from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# Tunnel protocol version
TUNNEL_PROTOCOL_VERSION = "syfthub-tunnel/v1"


class EndpointType(str, Enum):
    DATA_SOURCE = "data_source"
    MODEL = "model"


class TunnelErrorCode(str, Enum):
    """Error codes for tunnel responses."""

    ENDPOINT_NOT_FOUND = "ENDPOINT_NOT_FOUND"
    ENDPOINT_TYPE_MISMATCH = "ENDPOINT_TYPE_MISMATCH"
    HANDLER_ERROR = "HANDLER_ERROR"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    TIMEOUT = "TIMEOUT"


# Data Source Schemas
class DataSourceQueryRequest(BaseModel):
    messages: str
    limit: int = Field(default=5)
    similarity_threshold: float = Field(default=0.5)
    include_metadata: bool = Field(default=True)
    transaction_token: str | None = None


class Document(BaseModel):
    document_id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    similarity_score: float


class ProviderInfo(BaseModel):
    provider: str
    model: str


class References(BaseModel):
    documents: list[Document]
    provider_info: ProviderInfo | None = None
    cost: float | None = None


class DataSourceQueryResponse(BaseModel):
    summary: str | None = None
    references: References


# Model Schemas
class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelQueryRequest(BaseModel):
    messages: list[Message]
    max_tokens: int = Field(default=1024)
    temperature: float = Field(default=0.7)
    stream: bool = Field(default=False)
    stop_sequences: list[str] = Field(default_factory=list)
    transaction_token: str | None = None


class ResponseMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str
    tokens: int | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ModelSummary(BaseModel):
    id: str
    model: str
    message: ResponseMessage
    finish_reason: str
    usage: TokenUsage | None = None
    cost: float | None = None
    provider_info: ProviderInfo | None = None


class ModelQueryResponse(BaseModel):
    summary: ModelSummary
    references: Any = None


# Tunnel Protocol Schemas
class TunnelEndpointInfo(BaseModel):
    """Endpoint identification in tunnel messages."""

    slug: str = Field(..., description="Endpoint slug identifier")
    type: str = Field(..., description="Endpoint type (data_source or model)")


class TunnelRequest(BaseModel):
    """Request message for tunnel protocol.

    This is the structure that goes inside the MQ message payload
    when a client wants to invoke an endpoint via tunneling.
    """

    protocol: str = Field(
        default=TUNNEL_PROTOCOL_VERSION, description="Protocol version identifier"
    )
    type: Literal["endpoint_request"] = Field(
        default="endpoint_request", description="Message type discriminator"
    )
    correlation_id: str = Field(..., description="Unique ID for matching request to response")
    reply_to: str = Field(..., description="Username to send the response to")
    endpoint: TunnelEndpointInfo = Field(..., description="Target endpoint information")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Request payload (matches HTTP request body)"
    )
    timeout_ms: int = Field(default=30000, ge=1000, le=300000, description="Request timeout in ms")


class TunnelError(BaseModel):
    """Error details in tunnel response."""

    code: str = Field(..., description="Error code (see TunnelErrorCode)")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")


class TunnelTiming(BaseModel):
    """Timing information for tunnel response."""

    received_at: str = Field(..., description="ISO timestamp when request was received")
    processed_at: str = Field(..., description="ISO timestamp when processing completed")
    duration_ms: int = Field(..., ge=0, description="Processing duration in milliseconds")


class TunnelResponse(BaseModel):
    """Response message for tunnel protocol.

    This is the structure that goes inside the MQ message payload
    when a Space responds to a tunneled request.
    """

    protocol: str = Field(
        default=TUNNEL_PROTOCOL_VERSION, description="Protocol version identifier"
    )
    type: Literal["endpoint_response"] = Field(
        default="endpoint_response", description="Message type discriminator"
    )
    correlation_id: str = Field(..., description="Matches the request's correlation_id")
    status: Literal["success", "error"] = Field(..., description="Response status")
    endpoint_slug: str = Field(..., description="Endpoint that processed the request")
    payload: dict[str, Any] | None = Field(
        default=None, description="Response payload (on success)"
    )
    error: TunnelError | None = Field(default=None, description="Error details (on error)")
    timing: TunnelTiming | None = Field(default=None, description="Processing timing info")
