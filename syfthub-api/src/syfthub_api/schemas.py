from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EndpointType(str, Enum):
    DATA_SOURCE = "data_source"
    MODEL = "model"


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
