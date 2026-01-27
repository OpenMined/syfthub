"""User schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from syfthub.schemas.auth import UserRole


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
        """Validate URL format."""
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
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
