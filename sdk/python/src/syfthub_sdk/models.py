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


# =============================================================================
# Accounting Models
# =============================================================================


class TransactionStatus(str, Enum):
    """Transaction status in the accounting service."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CreatorType(str, Enum):
    """Who created or resolved a transaction."""

    SYSTEM = "system"
    SENDER = "sender"
    RECIPIENT = "recipient"


class AccountingUser(BaseModel):
    """User from accounting service with balance.

    This represents the user's account in the external accounting service,
    which is separate from the SyftHub user account.
    """

    id: str
    email: str
    balance: float = Field(default=0.0, ge=0.0)
    organization: str | None = None

    model_config = {"frozen": True}


class Transaction(BaseModel):
    """Transaction record from accounting service.

    Transactions go through a lifecycle:
    1. Created (status=PENDING)
    2. Confirmed or Cancelled (status=COMPLETED or CANCELLED)

    The created_by field indicates who initiated the transaction:
    - SENDER: Direct transaction by the payer
    - RECIPIENT: Delegated transaction using a token
    - SYSTEM: System-initiated transaction

    The resolved_by field indicates who confirmed/cancelled.
    """

    id: str
    sender_email: str = Field(alias="senderEmail")
    recipient_email: str = Field(alias="recipientEmail")
    amount: float = Field(gt=0.0)
    status: TransactionStatus
    created_by: CreatorType = Field(alias="createdBy")
    resolved_by: CreatorType | None = Field(default=None, alias="resolvedBy")
    created_at: datetime = Field(alias="createdAt")
    resolved_at: datetime | None = Field(default=None, alias="resolvedAt")
    app_name: str | None = Field(default=None, alias="appName")
    app_ep_path: str | None = Field(default=None, alias="appEpPath")

    model_config = {"frozen": True, "populate_by_name": True}

    @property
    def is_pending(self) -> bool:
        """Check if transaction is still pending."""
        return self.status == TransactionStatus.PENDING

    @property
    def is_completed(self) -> bool:
        """Check if transaction was completed."""
        return self.status == TransactionStatus.COMPLETED

    @property
    def is_cancelled(self) -> bool:
        """Check if transaction was cancelled."""
        return self.status == TransactionStatus.CANCELLED


# Backward compatibility aliases (deprecated)
AccountingBalance = AccountingUser  # Use AccountingUser instead
AccountingTransaction = Transaction  # Use Transaction instead


class AccountingCredentials(BaseModel):
    """Credentials for connecting to an external accounting service.

    These are stored in the SyftHub backend and fetched via API.
    The email is always the same as the user's SyftHub email.
    """

    url: str | None = Field(None, description="Accounting service URL")
    email: str = Field(..., description="User's email (same as SyftHub email)")
    password: str | None = Field(None, description="Accounting service password")

    model_config = {"frozen": True}
