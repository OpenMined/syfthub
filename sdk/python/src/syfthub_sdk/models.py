"""Pydantic models for SyftHub SDK responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Visibility(str, Enum):
    """Endpoint visibility levels."""

    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"


class EndpointType(str, Enum):
    """Endpoint type classification."""

    MODEL = "model"
    DATA_SOURCE = "data_source"


class UserRole(str, Enum):
    """User role levels."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class OrganizationRole(str, Enum):
    """Role within an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class User(BaseModel):
    """User model returned from API."""

    id: int
    username: str
    email: str
    full_name: str
    avatar_url: str | None = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime
    updated_at: datetime | None = None  # Some endpoints don't return this
    domain: str | None = None  # Domain for endpoint URL construction
    aggregator_url: str | None = None  # Custom aggregator URL for RAG/chat workflows

    model_config = {"frozen": True}


class AuthTokens(BaseModel):
    """Authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"

    model_config = {"frozen": True}


class SatelliteTokenResponse(BaseModel):
    """Response from satellite token endpoint.

    Satellite tokens are short-lived, RS256-signed JWTs that allow satellite
    services (like SyftAI-Space) to verify user identity without calling
    SyftHub for every request.
    """

    target_token: str = Field(
        ..., description="RS256-signed JWT for the target service"
    )
    expires_in: int = Field(..., description="Seconds until the token expires")

    model_config = {"frozen": True}


class Policy(BaseModel):
    """Policy configuration for endpoints."""

    type: str
    version: str = "1.0"
    enabled: bool = True
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class Connection(BaseModel):
    """Connection configuration for endpoints."""

    type: str
    enabled: bool = True
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class Endpoint(BaseModel):
    """Full endpoint model (for user's own endpoints)."""

    id: int
    user_id: int | None = None
    organization_id: int | None = None
    name: str
    slug: str
    description: str = ""
    type: EndpointType
    visibility: Visibility = Visibility.PUBLIC
    is_active: bool = True
    contributors: list[int] = Field(default_factory=list)
    version: str = "0.1.0"
    readme: str = ""
    tags: list[str] = Field(default_factory=list)
    stars_count: int = 0
    policies: list[Policy] = Field(default_factory=list)
    connect: list[Connection] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"frozen": True}

    @property
    def owner_type(self) -> str:
        """Return 'user' or 'organization' based on ownership."""
        if self.user_id is not None:
            return "user"
        return "organization"


class EndpointPublic(BaseModel):
    """Public endpoint model (for hub browsing)."""

    name: str
    slug: str
    description: str = ""
    type: EndpointType
    owner_username: str
    contributors_count: int = 0  # Privacy-friendly count instead of list
    version: str = "0.1.0"
    readme: str = ""
    tags: list[str] = Field(default_factory=list)
    stars_count: int = 0
    policies: list[Policy] = Field(default_factory=list)
    connect: list[Connection] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"frozen": True}

    @property
    def path(self) -> str:
        """Return the GitHub-style path (owner/slug)."""
        return f"{self.owner_username}/{self.slug}"


class EndpointSearchResult(BaseModel):
    """Search result with relevance score from semantic search.

    Extends the public endpoint fields with a relevance score indicating
    how well the endpoint matches the search query.
    """

    name: str
    slug: str
    description: str = ""
    type: EndpointType
    owner_username: str
    contributors_count: int = 0
    version: str = "0.1.0"
    readme: str = ""
    tags: list[str] = Field(default_factory=list)
    stars_count: int = 0
    policies: list[Policy] = Field(default_factory=list)
    connect: list[Connection] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score from semantic search (0.0-1.0)",
    )

    model_config = {"frozen": True}

    @property
    def path(self) -> str:
        """Return the GitHub-style path (owner/slug)."""
        return f"{self.owner_username}/{self.slug}"


class EndpointSearchResponse(BaseModel):
    """Response from the endpoint search API."""

    results: list[EndpointSearchResult] = Field(default_factory=list)
    total: int = 0
    query: str = ""

    model_config = {"frozen": True}


# =============================================================================
# Accounting Models
# =============================================================================


class TransactionStatus(str, Enum):
    """Transaction status in the accounting service."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CreatorType(str, Enum):
    """Who created or resolved a transaction."""

    SYSTEM = "system"
    SENDER = "sender"
    RECIPIENT = "recipient"


class AccountingUser(BaseModel):
    """User from accounting service with balance.

    This represents the user's account in the external accounting service,
    which is separate from the SyftHub user account.
    """

    id: str
    email: str
    balance: float = Field(default=0.0, ge=0.0)
    organization: str | None = None

    model_config = {"frozen": True}


class Transaction(BaseModel):
    """Transaction record from accounting service.

    Transactions go through a lifecycle:
    1. Created (status=PENDING)
    2. Confirmed or Cancelled (status=COMPLETED or CANCELLED)

    The created_by field indicates who initiated the transaction:
    - SENDER: Direct transaction by the payer
    - RECIPIENT: Delegated transaction using a token
    - SYSTEM: System-initiated transaction

    The resolved_by field indicates who confirmed/cancelled.
    """

    id: str
    sender_email: str = Field(alias="senderEmail")
    recipient_email: str = Field(alias="recipientEmail")
    amount: float = Field(gt=0.0)
    status: TransactionStatus
    created_by: CreatorType = Field(alias="createdBy")
    resolved_by: CreatorType | None = Field(default=None, alias="resolvedBy")
    created_at: datetime = Field(alias="createdAt")
    resolved_at: datetime | None = Field(default=None, alias="resolvedAt")
    app_name: str | None = Field(default=None, alias="appName")
    app_ep_path: str | None = Field(default=None, alias="appEpPath")

    model_config = {"frozen": True, "populate_by_name": True}

    @property
    def is_pending(self) -> bool:
        """Check if transaction is still pending."""
        return self.status == TransactionStatus.PENDING

    @property
    def is_completed(self) -> bool:
        """Check if transaction was completed."""
        return self.status == TransactionStatus.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        """Check if transaction was cancelled."""
        return self.status == TransactionStatus.CANCELLED


class AccountingCredentials(BaseModel):
    """Credentials for connecting to an external accounting service.

    These are stored in the SyftHub backend and fetched via API.
    The email is always the same as the user's SyftHub email.
    """

    url: str | None = Field(None, description="Accounting service URL")
    email: str = Field(..., description="User's email (same as SyftHub email)")
    password: str | None = Field(None, description="Accounting service password")

    model_config = {"frozen": True}


# =============================================================================
# Chat Models (for Aggregator integration)
# =============================================================================


class SourceStatus(str, Enum):
    """Status of a data source query."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class EndpointRef(BaseModel):
    """Reference to a SyftAI-Space endpoint with connection details.

    This is used to specify endpoints for chat operations. It can be
    constructed manually or resolved from an EndpointPublic object.

    Example:
        # Direct construction
        ref = EndpointRef(
            url="http://syftai-space:8080",
            slug="my-model",
            name="My Model",
            owner_username="alice",
        )

        # From endpoint path (via ChatResource)
        response = client.chat.complete(
            prompt="Hello",
            model="alice/my-model",  # Resolved automatically
        )
    """

    url: str = Field(..., description="Base URL of the SyftAI-Space instance")
    slug: str = Field(..., description="Endpoint slug for the API path")
    name: str = Field(default="", description="Display name of the endpoint")
    tenant_name: str | None = Field(
        default=None, description="Tenant name for X-Tenant-Name header"
    )
    owner_username: str | None = Field(
        default=None,
        description="Owner's username - used as the audience for satellite token authentication",
    )

    model_config = {"frozen": True}


class Document(BaseModel):
    """A document retrieved from a data source.

    Returned as part of retrieval results when querying data sources.
    """

    content: str = Field(..., description="The document content")
    score: float = Field(default=0.0, description="Relevance score (0-1)")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    model_config = {"frozen": True}


class SourceInfo(BaseModel):
    """Information about a data source retrieval (metadata).

    Provides details about each data source that was queried during
    the retrieval phase of RAG.
    """

    path: str = Field(..., description="Endpoint path (owner/slug)")
    documents_retrieved: int = Field(
        ..., description="Number of documents retrieved from this source"
    )
    status: SourceStatus = Field(..., description="Query status")
    error_message: str | None = Field(
        default=None, description="Error message if status is error/timeout"
    )

    model_config = {"frozen": True}


class DocumentSource(BaseModel):
    """A document source entry with endpoint path and content.

    Used in the sources dict of ChatResponse, keyed by document title.
    """

    slug: str = Field(
        ..., description="Endpoint path (owner/slug) where document was retrieved"
    )
    content: str = Field(..., description="The actual document content")

    model_config = {"frozen": True}


class ChatMetadata(BaseModel):
    """Timing metadata for chat response.

    Provides performance metrics for the RAG pipeline.
    """

    retrieval_time_ms: int = Field(
        ..., description="Time spent retrieving documents (ms)"
    )
    generation_time_ms: int = Field(
        ..., description="Time spent generating response (ms)"
    )
    total_time_ms: int = Field(..., description="Total request time (ms)")

    model_config = {"frozen": True}


class TokenUsage(BaseModel):
    """Token usage information from model generation.

    Provides token counts for prompt and completion.
    """

    prompt_tokens: int = Field(default=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(
        default=0, description="Number of tokens in the completion"
    )
    total_tokens: int = Field(default=0, description="Total tokens used")

    model_config = {"frozen": True}


class ChatResponse(BaseModel):
    """Response from a chat completion request.

    Contains the generated response, source information, timing metadata,
    and token usage if available.
    """

    response: str = Field(..., description="The generated response text")
    sources: dict[str, DocumentSource] = Field(
        default_factory=dict,
        description="Retrieved documents keyed by title, with endpoint slug and content",
    )
    retrieval_info: list[SourceInfo] = Field(
        default_factory=list,
        description="Metadata about each data source retrieval (status, count, errors)",
    )
    metadata: ChatMetadata = Field(..., description="Timing metadata")
    usage: TokenUsage | None = Field(
        default=None, description="Token usage if available"
    )

    model_config = {"frozen": True}


class Message(BaseModel):
    """A chat message for model queries.

    Used when making direct queries to model endpoints via SyftAIResource.
    """

    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")

    model_config = {"frozen": True}


# =============================================================================
# API Token Models
# =============================================================================


class APITokenScope(str, Enum):
    """API token permission scopes."""

    READ = "read"
    WRITE = "write"
    FULL = "full"


class APIToken(BaseModel):
    """API token metadata (without the actual token value).

    The full token value is only returned once during creation.
    """

    id: int
    name: str
    token_prefix: str = Field(
        ..., description="First 12 chars of the token for identification"
    )
    scopes: list[APITokenScope] = Field(default_factory=lambda: [APITokenScope.FULL])
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    last_used_ip: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"frozen": True}


class APITokenCreateResponse(APIToken):
    """Response from creating an API token.

    IMPORTANT: The `token` field is only returned ONCE during creation.
    Store it securely - it cannot be retrieved later.
    """

    token: str = Field(..., description="The full token value (shown only once)")


class CreateAPITokenInput(BaseModel):
    """Input for creating a new API token."""

    name: str = Field(..., min_length=1, max_length=100, description="Token name")
    scopes: list[APITokenScope] = Field(
        default_factory=lambda: [APITokenScope.FULL],
        description="Permission scopes",
    )
    expires_at: datetime | None = Field(
        default=None, description="Optional expiration date"
    )


class UpdateAPITokenInput(BaseModel):
    """Input for updating an API token (only name can be changed)."""

    name: str = Field(..., min_length=1, max_length=100, description="New token name")


class APITokenListResponse(BaseModel):
    """Response from listing API tokens."""

    tokens: list[APIToken] = Field(default_factory=list)
    total: int = 0

    model_config = {"frozen": True}


# =============================================================================
# Sync Endpoints Models
# =============================================================================


class SyncEndpointsResponse(BaseModel):
    """Response from the sync endpoints operation.

    Contains details about the sync operation including how many endpoints
    were deleted, how many were created, and the full list of created endpoints.
    """

    synced: int = Field(..., ge=0, description="Number of endpoints created")
    deleted: int = Field(..., ge=0, description="Number of endpoints deleted")
    endpoints: list[Endpoint] = Field(
        ..., description="List of created endpoints with full details"
    )

    model_config = {"frozen": True}
