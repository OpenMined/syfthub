"""User database model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.collective import CollectiveModel
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.user_aggregator import UserAggregatorModel


class UserModel(BaseModel, TimestampMixin):
    """User database model."""

    __tablename__ = "users"

    # Stable, opaque public identifier. This — never ``id`` — is what leaves the
    # backend as an external reference to a user (the OIDC ``sub`` claim), so
    # relying parties never learn SyftHub's internal, sequential primary keys
    # (see the privacy notes on EndpointPublicResponse). Immutable once assigned.
    #
    # The Python-side default covers ORM inserts, including SQLite in dev/tests.
    # PostgreSQL additionally carries a ``gen_random_uuid()`` server default,
    # applied in migration 022 rather than declared here: SQLite has no such
    # function and would choke on it during ``create_all()``. The server default
    # is what keeps signups working during a deploy, while the previous release
    # — which knows nothing about this column — is still serving traffic.
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), unique=True, nullable=False, default=uuid.uuid4
    )

    # User fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    # Address the user has asked to move to but has not yet proven control of.
    # ``email`` is only overwritten once an OTP sent to this address verifies, so
    # ``is_email_verified`` never ends up describing an unproven address. See
    # EmailChangeService.
    pending_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # OAuth fields
    auth_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="local"
    )
    google_id: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )

    # MPP wallet fields (Tempo blockchain)
    wallet_address: Mapped[Optional[str]] = mapped_column(
        String(42), nullable=True, default=None
    )
    wallet_private_key: Mapped[Optional[str]] = mapped_column(
        String(66), nullable=True, default=None
    )

    # Domain with protocol for dynamic endpoint URL construction
    domain: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )

    # Custom aggregator URL for RAG/chat workflows
    aggregator_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )

    # Public profile bio (Markdown). Surfaced on /:username public profile page.
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)

    # Whether the user's email is shown on their public profile page.
    is_email_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Timestamp of the user's last successful login (password or Google sign-in).
    # Null until the user logs in for the first time. Used by the admin
    # user-overview dashboard for last-login recency bucketing.
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # X25519 public key for NATS tunnel E2E encryption (base64url-encoded, 44 chars)
    # Registered by the space on startup via PUT /api/v1/nats/encryption-key
    encryption_public_key: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )

    # Relationships
    endpoints: Mapped[List["EndpointModel"]] = relationship(
        "EndpointModel", back_populates="user", cascade="all, delete-orphan"
    )
    aggregators: Mapped[List["UserAggregatorModel"]] = relationship(
        "UserAggregatorModel", back_populates="user", cascade="all, delete-orphan"
    )
    collectives: Mapped[List["CollectiveModel"]] = relationship(
        "CollectiveModel", back_populates="owner", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
        Index("idx_users_google_id", "google_id"),
        Index("idx_users_last_login_at", "last_login_at"),
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
