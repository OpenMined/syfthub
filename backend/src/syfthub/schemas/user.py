"""User schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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

    age: Optional[int] = Field(None, ge=0, le=150, description="User's age")


class User(UserBase):
    """User model."""

    id: int = Field(..., description="User's unique identifier")
    age: Optional[int] = Field(None, ge=0, le=150, description="User's age")
    role: UserRole = Field(default=UserRole.USER, description="User role")
    password_hash: str = Field(..., description="Hashed password")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """Schema for user response."""

    id: int = Field(..., description="User's unique identifier")
    username: str = Field(..., description="Username")
    email: EmailStr = Field(..., description="User's email address")
    full_name: str = Field(..., description="User's full name")
    age: Optional[int] = Field(None, description="User's age")
    role: UserRole = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether the user is active")
    created_at: datetime = Field(..., description="When the user was created")
    updated_at: datetime = Field(..., description="When the user was last updated")

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    email: Optional[EmailStr] = Field(None, description="User's email address")
    full_name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="User's full name"
    )
    age: Optional[int] = Field(None, ge=0, le=150, description="User's age")
    is_active: Optional[bool] = Field(None, description="Whether the user is active")
