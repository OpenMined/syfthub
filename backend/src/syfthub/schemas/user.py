"""User schemas."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, EmailStr, Field, field_validator

from syfthub.schemas.auth import UserRole

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
    password_hash: str = Field(..., description="Hashed password")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Accounting fields
    accounting_service_url: Optional[str] = Field(
        None, description="URL to external accounting service"
    )
    accounting_password: Optional[str] = Field(
        None, description="Password for external accounting service"
    )
    # Domain for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None, max_length=253, description="Domain for endpoint URL construction"
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
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")
    # Accounting - only expose URL, never expose password in user response
    accounting_service_url: Optional[str] = Field(
        None, description="URL to external accounting service"
    )
    # Domain for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None, description="Domain for endpoint URL construction"
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
    # Accounting service credentials
    accounting_service_url: Optional[str] = Field(
        None, max_length=500, description="URL to external accounting service"
    )
    accounting_password: Optional[str] = Field(
        None, max_length=255, description="Password for external accounting service"
    )
    # Domain for dynamic endpoint URL construction
    domain: Optional[str] = Field(
        None,
        max_length=253,
        description="Domain for endpoint URL construction (no protocol)",
    )
    # Custom aggregator URL for RAG/chat workflows
    aggregator_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Custom aggregator URL for RAG/chat workflows",
    )


class AccountingCredentialsResponse(BaseModel):
    """Schema for accounting credentials response."""

    url: Optional[str] = Field(None, description="Accounting service URL")
    email: str = Field(..., description="User's email (same as SyftHub email)")
    password: Optional[str] = Field(None, description="Accounting service password")

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
    """Response schema for heartbeat endpoint."""

    status: str = Field(..., description="Status of heartbeat receipt")
    received_at: datetime = Field(
        ..., description="Timestamp when heartbeat was received"
    )
    expires_at: datetime = Field(..., description="Timestamp when heartbeat expires")
    domain: str = Field(..., description="Normalized domain extracted from URL")
    ttl_seconds: int = Field(..., description="Actual TTL applied (may be capped)")
