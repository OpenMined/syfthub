"""User schemas."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator

from syfthub.schemas.auth import AuthProvider, UserRole

# Tunneling URL prefix for spaces behind firewalls/NAT
TUNNELING_PREFIX = "tunneling:"

# Pattern for valid tunneling usernames (alphanumeric, underscore, hyphen, 1-50 chars)
TUNNELING_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,50}$")


class UserBase(BaseModel):
    """Base user schema."""

    username: str = Field(
        ..., min_length=3, max_length=50, description="Unique username"
    )
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(
        ..., min_length=1, max_length=100, description="User's full name"
    )
    is_active: bool = Field(True, description="Whether the user is active")
    is_email_verified: bool = Field(
        True, description="Whether the user has verified their email"
    )


class UserCreate(UserBase):
    """Schema for creating a new user."""

    pass


class User(UserBase):
    """User model."""

    id: int = Field(..., description="User's unique identifier")
    avatar_url: Optional[str] = Field(
        None, max_length=500, description="URL to user's avatar image"
    )
    role: UserRole = Field(default=UserRole.USER, description="User role")
    password_hash: Optional[str] = Field(
        None, description="Hashed password (null for OAuth users)"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # OAuth fields
    auth_provider: AuthProvider = Field(
        default=AuthProvider.LOCAL, description="Authentication provider"
    )
    google_id: Optional[str] = Field(None, description="Google OAuth user ID")
    # Domain with protocol for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None,
        max_length=500,
        description="Domain with protocol for endpoint URL construction (e.g., 'https://example.com')",
    )
    # Custom aggregator URL for RAG/chat workflows
    aggregator_url: Optional[str] = Field(
        None, description="Custom aggregator URL for RAG/chat workflows"
    )
    # Heartbeat tracking fields
    last_heartbeat_at: Optional[datetime] = Field(
        None, description="Timestamp of last heartbeat received"
    )
    heartbeat_expires_at: Optional[datetime] = Field(
        None, description="Timestamp when heartbeat expires"
    )
    # MPP wallet fields (Tempo blockchain)
    wallet_address: Optional[str] = Field(
        None, description="Tempo wallet address (Ethereum-format)"
    )

    # NOTE: wallet_private_key is intentionally excluded from this response
    # schema.  It lives only on the DB model (UserModel) and must NEVER be
    # serialized in API responses.

    # X25519 public key for NATS tunnel encryption (base64url-encoded)
    encryption_public_key: Optional[str] = Field(
        None, description="X25519 public key for tunnel encryption (base64url)"
    )

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int = Field(..., description="User's unique identifier")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(..., description="User's full name")
    avatar_url: Optional[str] = Field(None, description="URL to user's avatar image")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the user is active")
    is_email_verified: bool = Field(
        ..., description="Whether the user has verified their email"
    )
    auth_provider: AuthProvider = Field(..., description="Authentication provider")
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")
    # MPP wallet address (Tempo blockchain)
    wallet_address: Optional[str] = Field(
        None, description="Tempo blockchain wallet address"
    )
    # Domain with protocol for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None,
        description="Domain with protocol for endpoint URL construction (e.g., 'https://example.com')",
    )
    # Custom aggregator URL for RAG/chat workflows
    aggregator_url: Optional[str] = Field(
        None, description="Custom aggregator URL for RAG/chat workflows"
    )
    # Heartbeat tracking fields
    last_heartbeat_at: Optional[datetime] = Field(
        None, description="Timestamp of last heartbeat received"
    )
    heartbeat_expires_at: Optional[datetime] = Field(
        None, description="Timestamp when heartbeat expires"
    )
    # X25519 public key for NATS tunnel encryption (base64url-encoded)
    encryption_public_key: Optional[str] = Field(
        None, description="X25519 public key for tunnel encryption (base64url)"
    )

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    username: Optional[str] = Field(
        None, min_length=3, max_length=50, description="Unique username"
    )
    email: Optional[EmailStr] = Field(None, description="User's email address")
    full_name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="User's full name"
    )
    avatar_url: Optional[str] = Field(
        None, max_length=500, description="URL to user's avatar image"
    )
    is_active: Optional[bool] = Field(None, description="Whether the user is active")
    # MPP wallet address (Tempo blockchain)
    wallet_address: Optional[str] = Field(
        None, max_length=42, description="Tempo blockchain wallet address"
    )
    # Domain with protocol for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None,
        max_length=500,
        description="Domain with protocol for endpoint URL construction (e.g., 'https://example.com')",
    )
    # Custom aggregator URL for RAG/chat workflows
    aggregator_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Custom aggregator URL for RAG/chat workflows",
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        """Validate domain includes protocol prefix or is a tunneling URL.

        Ensures the domain:
        - Starts with http://, https://, or tunneling:<username>
        - Has a valid hostname (for HTTP URLs)
        - Has a valid username (for tunneling URLs)
        """
        if v is None:
            return None
        v = v.strip().rstrip("/")

        # Handle tunneling URLs (for spaces behind firewalls/NAT)
        if v.startswith(TUNNELING_PREFIX):
            username = v[len(TUNNELING_PREFIX) :]
            if not username:
                raise ValueError("Tunneling URL must include a username")
            if not TUNNELING_USERNAME_PATTERN.match(username):
                raise ValueError(
                    "Tunneling username must be 1-50 characters, "
                    "alphanumeric with underscores and hyphens only"
                )
            return v

        if not v.startswith(("http://", "https://")):
            raise ValueError(
                "Domain must include protocol (e.g., 'https://example.com' or 'http://192.168.1.1:8080')"
            )
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Domain must contain a valid hostname")
        return v


class TunnelCredentialsResponse(BaseModel):
    """Response schema for tunnel credentials endpoint."""

    auth_token: str = Field(
        ..., description="ngrok authtoken for tunnel authentication"
    )
    domain: str = Field(..., description="Reserved tunnel domain for the user")


class HeartbeatRequest(BaseModel):
    """Request schema for heartbeat endpoint.

    .. deprecated::
        Used by the deprecated ``POST /users/me/heartbeat`` and
        ``POST /organizations/{org_id}/heartbeat`` endpoints.
        Use ``EndpointHealthRequest`` (from ``syfthub.schemas.endpoint``) instead.
        Remove this schema when the heartbeat API routes are removed.
    """

    url: str = Field(
        ...,
        description="Full URL of the domain (e.g., 'https://api.example.com')",
        max_length=500,
    )
    ttl_seconds: Optional[int] = Field(
        None,
        ge=1,
        le=3600,
        description="Requested TTL in seconds (capped by server max)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and structure.

        Ensures the URL:
        - Starts with http://, https://, or tunneling:<username>
        - Is parseable (for HTTP URLs)
        - Has a valid hostname (netloc) for HTTP URLs
        - Has a valid username for tunneling URLs
        """
        v = v.strip()

        # Handle tunneling URLs (for spaces behind firewalls/NAT)
        if v.startswith(TUNNELING_PREFIX):
            username = v[len(TUNNELING_PREFIX) :]
            if not username:
                raise ValueError("Tunneling URL must include a username")
            if not TUNNELING_USERNAME_PATTERN.match(username):
                raise ValueError(
                    "Tunneling username must be 1-50 characters, "
                    "alphanumeric with underscores and hyphens only"
                )
            return v

        # Handle HTTP/HTTPS URLs
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"URL must start with http://, https://, or {TUNNELING_PREFIX}"
            )

        # Parse the URL to validate structure
        parsed = urlparse(v)

        # Ensure netloc (host:port) exists
        if not parsed.netloc:
            raise ValueError("URL must contain a valid hostname")

        # Extract hostname (without port) and validate it's not empty
        hostname = parsed.netloc.split(":")[0]
        if not hostname:
            raise ValueError("URL must contain a valid hostname, not just a port")

        return v


class HeartbeatResponse(BaseModel):
    """Response schema for heartbeat endpoint.

    .. deprecated::
        Used by the deprecated heartbeat endpoints.
        Use ``EndpointHealthResponse`` (from ``syfthub.schemas.endpoint``) instead.
        Remove this schema when the heartbeat API routes are removed.
    """

    status: str = Field(..., description="Status of heartbeat receipt")
    received_at: datetime = Field(
        ..., description="Timestamp when heartbeat was received"
    )
    expires_at: datetime = Field(..., description="Timestamp when heartbeat expires")
    domain: str = Field(
        ...,
        description="Domain with protocol extracted from URL (e.g., 'https://example.com:8080')",
    )
    ttl_seconds: int = Field(..., description="Actual TTL applied (may be capped)")


# =============================================================================
# User Aggregator Schemas
# =============================================================================


class UserAggregatorBase(BaseModel):
    """Base schema for user aggregator."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Display name for the aggregator"
    )
    url: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="URL of the aggregator service (e.g., 'https://aggregator.example.com')",
    )
    is_default: bool = Field(
        False, description="Whether this is the default aggregator for the user"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format and structure.

        Ensures the URL:
        - Starts with http:// or https://
        - Is parseable
        - Has a valid hostname (netloc)
        """
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        # Parse the URL to validate structure
        parsed = urlparse(v)

        # Ensure netloc (host:port) exists
        if not parsed.netloc:
            raise ValueError("URL must contain a valid hostname")

        # Extract hostname (without port) and validate it's not empty
        hostname = parsed.netloc.split(":")[0]
        if not hostname:
            raise ValueError("URL must contain a valid hostname, not just a port")

        return v


class UserAggregatorCreate(UserAggregatorBase):
    """Schema for creating a new user aggregator."""

    pass


class UserAggregatorUpdate(BaseModel):
    """Schema for updating a user aggregator."""

    model_config = {"extra": "ignore"}

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Display name for the aggregator",
    )
    url: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="URL of the aggregator service",
    )
    is_default: Optional[bool] = Field(
        default=None, description="Whether this is the default aggregator"
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format and structure."""
        if v is None:
            return None

        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("URL must contain a valid hostname")

        hostname = parsed.netloc.split(":")[0]
        if not hostname:
            raise ValueError("URL must contain a valid hostname, not just a port")

        return v


class UserAggregatorResponse(BaseModel):
    """Schema for user aggregator response."""

    id: int = Field(..., description="Aggregator's unique identifier")
    user_id: int = Field(..., description="ID of the user who owns this aggregator")
    name: str = Field(..., description="Display name for the aggregator")
    url: str = Field(..., description="URL of the aggregator service")
    is_default: bool = Field(..., description="Whether this is the default aggregator")
    created_at: datetime = Field(..., description="When the aggregator was created")
    updated_at: datetime = Field(
        ..., description="When the aggregator was last updated"
    )

    model_config = {"from_attributes": True}


class UserAggregatorListResponse(BaseModel):
    """Schema for list of user aggregators response."""

    aggregators: list[UserAggregatorResponse] = Field(
        ..., description="List of user's aggregators"
    )
    default_aggregator_id: Optional[int] = Field(
        None, description="ID of the default aggregator, if any"
    )


# =============================================================================
# MPP / Wallet Schemas
# =============================================================================


class WalletResponse(BaseModel):
    """Response schema for wallet status check."""

    address: Optional[str] = None
    exists: bool = False


class CreateWalletResponse(BaseModel):
    """Response schema for wallet creation."""

    address: str


class ImportWalletRequest(BaseModel):
    """Request schema for importing an existing wallet."""

    private_key: str


class PaymentRequest(BaseModel):
    """Request schema for MPP payment."""

    www_authenticate: str
    endpoint_slug: str


class PaymentResponse(BaseModel):
    """Response schema for MPP payment."""

    x_payment: str


class WalletTransaction(BaseModel):
    """Schema for a single wallet transaction."""

    id: str
    sender_email: str
    recipient_email: str
    amount: float
    status: str
    created_at: str
    app_name: Optional[str] = None
    app_ep_path: Optional[str] = None


class WalletBalanceResponse(BaseModel):
    """Response schema for wallet balance query."""

    balance: float
    currency: str = "USD"
    recent_transactions: list[WalletTransaction] = []
    wallet_configured: bool = False
