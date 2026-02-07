"""User schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator

from syfthub.schemas.auth import AuthProvider, UserRole


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
    # Accounting fields (Unified Global Ledger)
    accounting_service_url: Optional[str] = Field(
        None, description="URL to Unified Global Ledger service"
    )
    accounting_api_token: Optional[str] = Field(
        None, description="API token for Unified Global Ledger (at_* format)"
    )
    accounting_account_id: Optional[str] = Field(
        None, description="UUID of user's account in Unified Global Ledger"
    )
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
    auth_provider: AuthProvider = Field(..., description="Authentication provider")
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")
    # Accounting - only expose URL and account ID, never expose API token in response
    accounting_service_url: Optional[str] = Field(
        None, description="URL to Unified Global Ledger service"
    )
    accounting_account_id: Optional[str] = Field(
        None, description="UUID of user's account in Unified Global Ledger"
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
    # Accounting service credentials (Unified Global Ledger)
    accounting_service_url: Optional[str] = Field(
        None, max_length=500, description="URL to Unified Global Ledger service"
    )
    accounting_api_token: Optional[str] = Field(
        None,
        max_length=500,
        description="API token for Unified Global Ledger (at_* format)",
    )
    accounting_account_id: Optional[str] = Field(
        None,
        max_length=36,
        description="UUID of user's account in Unified Global Ledger",
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
        """Validate domain includes protocol prefix.

        Ensures the domain:
        - Starts with http:// or https://
        - Has a valid hostname
        """
        if v is None:
            return None
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                "Domain must include protocol (e.g., 'https://example.com' or 'http://192.168.1.1:8080')"
            )
        parsed = urlparse(v)
        if not parsed.netloc:
            raise ValueError("Domain must contain a valid hostname")
        return v


class AccountingCredentialsResponse(BaseModel):
    """Schema for accounting credentials response.

    Returns accounting configuration for the Unified Global Ledger.
    Note: The API token is never exposed - users must manage tokens via the ledger UI.
    """

    url: Optional[str] = Field(None, description="Unified Global Ledger URL")
    account_id: Optional[str] = Field(
        None, description="User's account ID in the ledger"
    )
    has_api_token: bool = Field(False, description="Whether an API token is configured")

    model_config = {"from_attributes": True}


class HeartbeatRequest(BaseModel):
    """Request schema for heartbeat endpoint."""

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


class HeartbeatResponse(BaseModel):
    """Response schema for heartbeat endpoint."""

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
