"""User database model."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.organization import OrganizationMemberModel
    from syfthub.models.user_aggregator import UserAggregatorModel


class UserModel(BaseModel, TimestampMixin):
    """User database model."""

    __tablename__ = "users"

    # User fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

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

    # Heartbeat tracking fields for push-based health monitoring
    # Deprecated: These fields are written by the deprecated POST /users/me/heartbeat
    # endpoint and by POST /endpoints/health (heartbeat subsumption). The health monitor
    # reads heartbeat_expires_at as a fallback when per-endpoint health fields are absent.
    # When the deprecated heartbeat endpoints are removed and all clients use
    # POST /endpoints/health, these fields can be removed along with the heartbeat
    # fallback logic in health_monitor._check_endpoint_health().
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    heartbeat_expires_at: Mapped[Optional[datetime]] = mapped_column(
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
    organization_memberships: Mapped[List["OrganizationMemberModel"]] = relationship(
        "OrganizationMemberModel", back_populates="user", cascade="all, delete-orphan"
    )
    aggregators: Mapped[List["UserAggregatorModel"]] = relationship(
        "UserAggregatorModel", back_populates="user", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
        Index("idx_users_heartbeat_expires_at", "heartbeat_expires_at"),
        Index("idx_users_google_id", "google_id"),
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
