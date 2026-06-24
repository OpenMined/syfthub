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
    MODEL_DATA_SOURCE = "model_data_source"
    AGENT = "agent"


class UserRole(str, Enum):
    """User role levels."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


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


class RegisterResult(BaseModel):
    """Result of user registration.

    When ``requires_email_verification`` is True, the client must call
    ``auth.verify_otp()`` before the user can log in.
    """

    user: User
    requires_email_verification: bool = False

    model_config = {"frozen": True}


class AuthConfig(BaseModel):
    """Platform authentication configuration (from GET /auth/config)."""

    require_email_verification: bool = False
    smtp_configured: bool = False
    password_reset_enabled: bool = False

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


class PeerTokenResponse(BaseModel):
    """Response from peer token endpoint.

    Peer tokens are short-lived credentials that allow the aggregator to
    communicate with tunneling SyftAI Spaces via NATS pub/sub.
    """

    peer_token: str = Field(
        ..., description="Short-lived token for NATS authentication"
    )
    peer_channel: str = Field(
        ..., description="Unique reply channel for receiving responses"
    )
    expires_in: int = Field(..., description="Seconds until the token expires")
    nats_url: str = Field(..., description="NATS server URL for WebSocket connections")

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
    user_id: int
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


class AccountingTransaction(BaseModel):
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
    """Status of a data source query.

    The payment/policy values mirror the aggregator's per-source outcome:
    ``payment_failed`` (a metered 402 the aggregator could not settle) and the
    403 rejection causes ``access_denied`` / ``policy_violation`` /
    ``rate_limited`` (derived from the source's ``policy_metadata.outcome``).
    """

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    PAYMENT_FAILED = "payment_failed"
    ACCESS_DENIED = "access_denied"
    POLICY_VIOLATION = "policy_violation"
    RATE_LIMITED = "rate_limited"


class ReasonCode(str, Enum):
    """Machine-readable rejection reason on a :class:`BillingEntry`.

    The known set the producer emits today; ``BillingEntry.reason_code`` stays a
    plain ``str`` so a future code never breaks parsing — compare against these
    members (e.g. ``entry.reason_code == ReasonCode.INSUFFICIENT_BALANCE``).
    """

    NO_PRICING_TIER = "NO_PRICING_TIER"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    RATE_LIMITED = "RATE_LIMITED"


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


class Recipient(BaseModel):
    """The "to whom" of a billing entry — the endpoint owner / publisher.

    All fields are optional; ``wallet_address`` is a public MPP address only
    and never a private key.
    """

    username: str | None = Field(
        default=None, description="Endpoint owner / publisher username"
    )
    email: str | None = Field(default=None, description="Recipient email")
    wallet_address: str | None = Field(
        default=None, description="Public MPP wallet address (never a private key)"
    )

    model_config = {"frozen": True}


class Transaction(BaseModel):
    """A rail-native transaction reference for a billing entry.

    ``id`` is the rail-native identifier (Tempo tx hash for ``mpp``; the ledger
    transaction id for ``xendit`` / ``stripe``); ``rail`` is the discriminator.
    """

    rail: str = Field(
        ..., description="Payment rail discriminator (mpp, xendit, stripe, ...)"
    )
    id: str = Field(..., description="Rail-native transaction id")
    reference: str | None = Field(
        default=None, description="Secondary reference (e.g. MPP external_id)"
    )

    model_config = {"frozen": True}


class BillingEntry(BaseModel):
    """A single policy-metadata entry from a queried source.

    Emitted by both payment and non-payment policies. When surfaced via the
    aggregated :class:`Billing` block, ``source`` carries the ``owner/slug`` of
    the source that produced the entry; on the direct path it is ``None``.
    """

    source: str | None = Field(
        default=None, description="Source endpoint path (owner/slug); None if direct"
    )
    policy_type: str = Field(
        ..., description="Policy type (e.g. mpp_per_request, rate_limit, pii_filter)"
    )
    kind: str = Field(
        ..., description="Policy kind (payment, access, transform, rate_limit)"
    )
    status: str = Field(
        ...,
        description="Outcome status (charged, refunded, free, rejected, applied, skipped)",
    )
    amount: float | None = Field(default=None, description="Charged amount, if any")
    currency: str | None = Field(default=None, description="Currency code, if any")
    recipient: Recipient | None = Field(
        default=None, description="Who the payment is owed to, if any"
    )
    transaction: Transaction | None = Field(
        default=None, description="Rail-native transaction reference, if any"
    )
    reason_code: str | None = Field(
        default=None,
        description="Machine-readable rejection code; see ReasonCode for the known set",
    )
    reason: str | None = Field(
        default=None, description="Human-readable reason message"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra structured details (e.g. {'documents': 3})",
    )

    model_config = {"frozen": True}


class PolicyMetadata(BaseModel):
    """Raw policy-metadata block returned on the direct syft-space path.

    Unlike the aggregated :class:`Billing` block, this is the per-source object
    exactly as the syft-space ``/query`` response carries it: an ``outcome``
    string plus the list of :class:`BillingEntry` items (whose ``source`` key is
    absent / ``None`` on the direct path). No aggregation or total is applied.
    """

    outcome: str = Field(
        ..., description="Query outcome (e.g. success, payment_required)"
    )
    entries: list[BillingEntry] = Field(
        default_factory=list, description="Per-policy metadata entries"
    )

    model_config = {"frozen": True}


class DataSourceQueryResult(BaseModel):
    """Result of a direct data-source query (``client.syftai.query_data_source``).

    Carries the retrieved documents plus the raw ``policy_metadata`` block from
    the syft-space ``/query`` response (Boundary A), so direct-query callers get
    the same authoritative payment/policy metadata the aggregator surfaces.

    The object is iterable over (and indexable into) its documents, so existing
    ``for doc in result`` / ``len(result)`` / ``result[0]`` usage keeps working.
    """

    documents: list[Document] = Field(
        default_factory=list, description="Retrieved documents"
    )
    policy_metadata: PolicyMetadata | None = Field(
        default=None,
        description="Raw policy metadata from the syft-space response, if present",
    )

    model_config = {"frozen": True}

    def __iter__(self) -> Any:
        """Iterate over the retrieved documents."""
        return iter(self.documents)

    def __len__(self) -> int:
        """Number of retrieved documents."""
        return len(self.documents)

    def __getitem__(self, index: int) -> Document:
        """Index into the retrieved documents."""
        return self.documents[index]


class Billing(BaseModel):
    """Aggregated billing block surfaced on chat and search responses.

    ``total_cost`` is the sum of entries with ``status == "charged"`` (None if
    none charged); ``currency`` is the common currency or None if mixed. No FX
    conversion is performed — each entry keeps its own currency.

    Note: ``total_cost`` can be > 0 on a *rejected* query — an earlier policy may
    have committed a charge before a later policy blocked the request, so the
    rejection envelope carries both the ``charged`` entry and the ``rejected``
    one. Inspect per-entry ``status`` (and the source's status) rather than
    assuming a positive ``total_cost`` means the query succeeded.
    """

    total_cost: float | None = Field(
        default=None, description="Sum of charged entries; None if nothing charged"
    )
    currency: str | None = Field(
        default=None, description="Common currency, or None if mixed"
    )
    entries: list[BillingEntry] = Field(
        default_factory=list, description="Per-source policy-metadata entries"
    )

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
    billing: Billing | None = Field(
        default=None,
        description="Aggregated payment-policy metadata across queried sources",
    )

    model_config = {"frozen": True}


class SearchDocument(BaseModel):
    """A single document returned by a retrieval-only search.

    Unlike :class:`Document` (the low-level direct-query shape), this carries
    the document title and the source endpoint path, matching the aggregated
    ``sources`` map returned by the aggregator's retrieval-only path.
    """

    title: str = Field(..., description="Document title (key in the sources map)")
    slug: str = Field(
        ..., description="Source endpoint path (owner/slug) the document came from"
    )
    content: str = Field(..., description="The document content")

    model_config = {"frozen": True}


class SearchResponse(BaseModel):
    """Response from a retrieval-only search via the Aggregator.

    Mirrors :class:`ChatResponse` minus the generated text: retrieval runs
    across the data sources (with satellite-token auth and MPP payment handled
    by the aggregator), but no model is invoked.
    """

    documents: list[SearchDocument] = Field(
        default_factory=list,
        description="Retrieved documents across all data sources",
    )
    retrieval_info: list[SourceInfo] = Field(
        default_factory=list,
        description="Metadata about each data source retrieval (status, count, errors)",
    )
    metadata: ChatMetadata = Field(..., description="Timing metadata")
    billing: Billing | None = Field(
        default=None,
        description="Aggregated payment-policy metadata across queried sources",
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
# NATS Credentials Models
# =============================================================================


class NatsCredentials(BaseModel):
    """Credentials for connecting to the NATS server.

    Fetched from the hub after login so spaces can connect to NATS
    without needing a separate environment variable.
    """

    nats_auth_token: str = Field(
        ..., description="The shared NATS auth token for WebSocket connections"
    )

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


# =============================================================================
# Heartbeat Models
# =============================================================================


class HeartbeatResponse(BaseModel):
    """Response from the heartbeat endpoint.

    The heartbeat mechanism allows SyftAI Spaces to signal their availability
    to SyftHub. The server returns the effective TTL (which may be capped)
    and the expiration time.

    Example:
        response = client.users.send_heartbeat(
            url="https://myspace.example.com",
            ttl_seconds=300
        )
        print(f"Heartbeat expires at: {response.expires_at}")
        print(f"Effective TTL: {response.ttl_seconds}s")
    """

    status: str = Field(..., description="Status of the heartbeat (typically 'ok')")
    received_at: datetime = Field(..., description="When the heartbeat was received")
    expires_at: datetime = Field(..., description="When the heartbeat will expire")
    domain: str = Field(..., description="Extracted domain from the URL")
    ttl_seconds: int = Field(
        ..., description="Effective TTL applied (may be capped by server)"
    )

    model_config = {"frozen": True}


# =============================================================================
# User Aggregator Models
# =============================================================================


class UserAggregator(BaseModel):
    """A user's aggregator configuration.

    Aggregators are custom RAG orchestration service endpoints that users can
    configure to use for chat operations. Each user can have multiple aggregator
    configurations, with one set as the default.

    Example:
        # List user's aggregators
        for agg in client.users.aggregators.list():
            print(f"{agg.name}: {agg.url} (default={agg.is_default})")

        # Create a new aggregator
        agg = client.users.aggregators.create(
            name="My Aggregator",
            url="https://my-aggregator.example.com"
        )
    """

    id: int = Field(..., description="Unique aggregator configuration ID")
    user_id: int = Field(..., description="Owner user ID")
    name: str = Field(..., description="Display name for the aggregator")
    url: str = Field(..., description="Aggregator service URL")
    is_default: bool = Field(
        default=False, description="Whether this is the user's default aggregator"
    )
    created_at: datetime = Field(..., description="When the aggregator was created")
    updated_at: datetime = Field(
        ..., description="When the aggregator was last updated"
    )

    model_config = {"frozen": True}
