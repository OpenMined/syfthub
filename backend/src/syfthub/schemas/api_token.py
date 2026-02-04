"""API Token schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class APITokenScope(str, Enum):
    """Permission scopes for API tokens.

    V1 supports simple scope levels. The schema is designed to support
    fine-grained scopes in the future (e.g., "endpoints:read", "profile:write").

    Attributes:
        READ: Read-only access (GET operations only).
        WRITE: Read and write access (GET + POST/PUT/PATCH/DELETE).
        FULL: Full access with the same permissions as the user.
    """

    READ = "read"
    WRITE = "write"
    FULL = "full"


class APITokenBase(BaseModel):
    """Base schema for API token data."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User-friendly label for the token (e.g., 'CI/CD Pipeline')",
    )
    scopes: List[APITokenScope] = Field(
        default=[APITokenScope.FULL],
        description="List of permission scopes. Defaults to full access.",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiration timestamp. Null means never expires.",
    )

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: List[APITokenScope]) -> List[APITokenScope]:
        """Validate that scopes list is not empty."""
        if not v:
            raise ValueError("At least one scope must be specified")
        # Remove duplicates while preserving order
        seen = set()
        unique_scopes = []
        for scope in v:
            if scope not in seen:
                seen.add(scope)
                unique_scopes.append(scope)
        return unique_scopes

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate that expiration is in the future."""
        if v is not None:
            # Ensure timezone-aware comparison
            now = datetime.now(timezone.utc)
            if v.tzinfo is None:
                # Assume UTC if no timezone
                v = v.replace(tzinfo=timezone.utc)
            if v <= now:
                raise ValueError("Expiration must be in the future")
        return v


class APITokenCreate(APITokenBase):
    """Schema for creating a new API token.

    Example:
        {
            "name": "CI/CD Pipeline",
            "scopes": ["write"],
            "expires_at": "2025-12-31T23:59:59Z"
        }
    """

    pass


class APITokenUpdate(BaseModel):
    """Schema for updating an API token.

    Only the name can be updated. Scopes and expiration cannot be changed
    after creation for security reasons.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="New name for the token",
    )


class APIToken(BaseModel):
    """API token response schema (without the actual token value).

    This schema is used for all responses EXCEPT creation, where the actual
    token is shown once.
    """

    id: int = Field(..., description="Unique token identifier")
    name: str = Field(..., description="User-friendly label for the token")
    token_prefix: str = Field(
        ...,
        description="First characters of the token for identification (e.g., 'syft_pat_aB3d')",
    )
    scopes: List[APITokenScope] = Field(..., description="Permission scopes")
    expires_at: Optional[datetime] = Field(
        None, description="Expiration timestamp, null if never expires"
    )
    last_used_at: Optional[datetime] = Field(
        None, description="Last time the token was used for authentication"
    )
    last_used_ip: Optional[str] = Field(
        None, description="IP address from the last authentication"
    )
    is_active: bool = Field(
        ..., description="Whether the token is active (not revoked)"
    )
    created_at: datetime = Field(..., description="When the token was created")
    updated_at: Optional[datetime] = Field(
        None, description="When the token was last updated"
    )

    model_config = {"from_attributes": True}


class APITokenCreateResponse(APIToken):
    """Response schema for token creation.

    IMPORTANT: This is the ONLY time the full token is returned!
    The user must save it immediately as it cannot be retrieved again.
    """

    token: str = Field(
        ...,
        description="The full API token. SAVE THIS NOW - it will not be shown again!",
    )

    @model_validator(mode="after")
    def validate_token_present(self) -> APITokenCreateResponse:
        """Ensure token is present in creation response."""
        if not self.token:
            raise ValueError("Token must be present in creation response")
        return self


class APITokenListResponse(BaseModel):
    """Response schema for listing API tokens."""

    tokens: List[APIToken] = Field(..., description="List of API tokens")
    total: int = Field(..., description="Total number of tokens")
