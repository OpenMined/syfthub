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

    model_config = {"frozen": True}


class AuthTokens(BaseModel):
    """Authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"

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
    user_id: int | None = None
    organization_id: int | None = None
    name: str
    slug: str
    description: str = ""
    type: EndpointType
    visibility: Visibility = Visibility.PUBLIC
    is_active: bool = True
    contributors: list[int] = Field(default_factory=list)
    version: str = "0.1.0"
    readme: str = ""
    stars_count: int = 0
    policies: list[Policy] = Field(default_factory=list)
    connect: list[Connection] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"frozen": True}

    @property
    def owner_type(self) -> str:
        """Return 'user' or 'organization' based on ownership."""
        if self.user_id is not None:
            return "user"
        return "organization"


class EndpointPublic(BaseModel):
    """Public endpoint model (for hub browsing)."""

    name: str
    slug: str
    description: str = ""
    type: EndpointType
    owner_username: str
    version: str = "0.1.0"
    readme: str = ""
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


class AccountingBalance(BaseModel):
    """Accounting balance information."""

    credits: float = 0.0
    currency: str = "USD"
    updated_at: datetime | None = None

    model_config = {"frozen": True}


class AccountingTransaction(BaseModel):
    """Accounting transaction record."""

    id: str
    amount: float
    description: str
    transaction_type: str  # "credit", "debit", "refund"
    created_at: datetime

    model_config = {"frozen": True}
