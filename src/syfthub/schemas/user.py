"""User schemas."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema."""

    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    is_active: bool = Field(True, description="Whether the user is active")


class UserCreate(UserBase):
    """Schema for creating a new user."""

    age: int | None = Field(None, ge=0, le=150, description="User's age")


class User(UserBase):
    """User model."""

    id: int = Field(..., description="User's unique identifier")
    age: int | None = Field(None, ge=0, le=150, description="User's age")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int = Field(..., description="User's unique identifier")
    name: str = Field(..., description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    age: int | None = Field(None, description="User's age")
    is_active: bool = Field(..., description="Whether the user is active")

    model_config = {"from_attributes": True}
