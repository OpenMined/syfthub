"""Organization and OrganizationMember database models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.user import UserModel


class OrganizationModel(BaseModel, TimestampMixin):
    """Organization database model."""

    __tablename__ = "organizations"

    # Organization fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Domain for dynamic endpoint URL construction
    domain: Mapped[Optional[str]] = mapped_column(
        String(253), nullable=True, default=None
    )

    # Heartbeat tracking fields for push-based health monitoring
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    heartbeat_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    members: Mapped[List["OrganizationMemberModel"]] = relationship(
        "OrganizationMemberModel",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    endpoints: Mapped[List["EndpointModel"]] = relationship(
        "EndpointModel", back_populates="organization", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index("idx_organizations_name", "name"),
        Index("idx_organizations_is_active", "is_active"),
        Index("idx_organizations_heartbeat_expires_at", "heartbeat_expires_at"),
    )

    def __repr__(self) -> str:
        """String representation of Organization."""
        return f"<Organization(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class OrganizationMemberModel(BaseModel):
    """Organization member database model."""

    __tablename__ = "organization_members"

    # Member fields
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    organization: Mapped["OrganizationModel"] = relationship(
        "OrganizationModel", back_populates="members"
    )
    user: Mapped["UserModel"] = relationship(
        "UserModel", back_populates="organization_memberships"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_org_members_org_id", "organization_id"),
        Index("idx_org_members_user_id", "user_id"),
        Index("idx_org_members_role", "role"),
        Index("idx_org_members_is_active", "is_active"),
        Index(
            "idx_org_members_unique", "organization_id", "user_id", unique=True
        ),  # Prevent duplicate memberships
    )

    def __repr__(self) -> str:
        """String representation of OrganizationMember."""
        return f"<OrganizationMember(id={self.id}, org_id={self.organization_id}, user_id={self.user_id}, role='{self.role}')>"
