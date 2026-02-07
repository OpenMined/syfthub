"""Authentication schemas."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Union

from pydantic import BaseModel, EmailStr, Field, field_validator

from syfthub.core.config import settings


class UserRole(str, Enum):
    """User roles for role-based access control."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class AuthProvider(str, Enum):
    """Authentication provider types."""

    LOCAL = "local"
    GOOGLE = "google"


class Token(BaseModel):
    """Token response schema."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")


class TokenData(BaseModel):
    """Token data schema for JWT payload."""

    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[UserRole] = None


class UserLogin(BaseModel):
    """User login schema."""

    username: str = Field(
        ..., min_length=1, max_length=50, description="Username or email"
    )
    password: str = Field(..., min_length=1, description="User password")


class UserRegister(BaseModel):
    """User registration schema.

    For Unified Global Ledger integration, users must:
    1. Create an account in the ledger UI
    2. Generate an API token
    3. Provide both during registration (or configure later in settings)

    Accounting configuration is optional during registration - users can
    set it up later in their account settings.
    """

    username: str = Field(
        ..., min_length=3, max_length=50, description="Unique username"
    )
    email: EmailStr = Field(..., description="User email address")
    full_name: str = Field(
        ..., min_length=1, max_length=100, description="User's full name"
    )
    password: str = Field(..., description="User password")
    # Unified Global Ledger configuration (optional)
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

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password requirements."""
        if len(v) < settings.password_min_length:
            msg = f"Password must be at least {settings.password_min_length} characters long"
            raise ValueError(msg)

        # Check for at least one number and one letter
        if not any(c.isdigit() for c in v):
            msg = "Password must contain at least one digit"
            raise ValueError(msg)

        if not any(c.isalpha() for c in v):
            msg = "Password must contain at least one letter"
            raise ValueError(msg)

        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username requirements."""
        if not v.replace("_", "").replace("-", "").isalnum():
            msg = "Username can only contain letters, numbers, underscores, and hyphens"
            raise ValueError(msg)
        return v.lower()


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""

    refresh_token: str = Field(..., description="Valid refresh token")


class PasswordChange(BaseModel):
    """Password change schema."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        """Validate new password requirements."""
        if len(v) < settings.password_min_length:
            msg = f"Password must be at least {settings.password_min_length} characters long"
            raise ValueError(msg)

        # Check for at least one number and one letter
        if not any(c.isdigit() for c in v):
            msg = "Password must contain at least one digit"
            raise ValueError(msg)

        if not any(c.isalpha() for c in v):
            msg = "Password must contain at least one letter"
            raise ValueError(msg)

        return v


class AuthResponse(BaseModel):
    """Authentication response with user info and tokens."""

    user: Dict[str, Union[str, int, bool, None]] = Field(
        ..., description="User information"
    )
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")


# RegistrationResponse is now identical to AuthResponse
RegistrationResponse = AuthResponse


class GoogleAuthRequest(BaseModel):
    """Google OAuth authentication request schema."""

    credential: str = Field(
        ...,
        min_length=1,
        description="Google ID token (JWT) received from Google Sign-In",
    )
