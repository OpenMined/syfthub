"""User schemas."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field

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

    age: int | None = Field(None, ge=0, le=150, description="User's age")


class User(UserBase):
    """User model."""

    id: int = Field(..., description="User's unique identifier")
    age: int | None = Field(None, ge=0, le=150, description="User's age")
    role: UserRole = Field(default=UserRole.USER, description="User role")
    password_hash: str = Field(..., description="Hashed password")
    public_key: str = Field(..., description="Base64 encoded Ed25519 public key")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    key_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int = Field(..., description="User's unique identifier")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(..., description="User's full name")
    age: int | None = Field(None, description="User's age")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the user is active")
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    email: EmailStr | None = Field(None, description="User's email address")
    full_name: str | None = Field(
        None, min_length=1, max_length=100, description="User's full name"
    )
    age: int | None = Field(None, ge=0, le=150, description="User's age")
    is_active: bool | None = Field(None, description="Whether the user is active")
