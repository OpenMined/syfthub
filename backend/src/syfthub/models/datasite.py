"""Datasite and DatasiteStar database models."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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
    from syfthub.models.organization import OrganizationModel
    from syfthub.models.user import UserModel


class DatasiteModel(BaseModel, TimestampMixin):
    """Datasite database model."""

    __tablename__ = "datasites"

    # Owner fields (exactly one of user_id or organization_id must be set)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )

    # Datasite fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    readme: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # JSON fields for complex data
    contributors: Mapped[List[int]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )
    policies: Mapped[List[dict]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )
    connect: Mapped[List[dict]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )

    # Relationships
    user: Mapped[Optional["UserModel"]] = relationship(
        "UserModel", back_populates="datasites"
    )
    organization: Mapped[Optional["OrganizationModel"]] = relationship(
        "OrganizationModel", back_populates="datasites"
    )

    # Indexes for performance - slug uniqueness is per-owner (user or organization)
    __table_args__ = (
        # Ensure exactly one owner (user_id XOR organization_id)
        CheckConstraint(
            "(user_id IS NULL) != (organization_id IS NULL)",
            name="ck_datasites_single_owner",
        ),
        Index("idx_datasites_user_id", "user_id"),
        Index("idx_datasites_organization_id", "organization_id"),
        Index("idx_datasites_slug", "slug"),
        # Unique slug per user (nulls ignored in unique constraints)
        Index("idx_datasites_user_slug", "user_id", "slug", unique=True),
        # Unique slug per organization (nulls ignored in unique constraints)
        Index("idx_datasites_org_slug", "organization_id", "slug", unique=True),
        Index("idx_datasites_visibility", "visibility"),
        Index("idx_datasites_is_active", "is_active"),
        Index("idx_datasites_version", "version"),
        Index("idx_datasites_stars_count", "stars_count"),
    )

    def __repr__(self) -> str:
        """String representation of Datasite."""
        owner = (
            f"user={self.user_id}" if self.user_id else f"org={self.organization_id}"
        )
        return f"<Datasite(id={self.id}, slug='{self.slug}', {owner})>"


class DatasiteStarModel(BaseModel):
    """Datasite star relationship model for tracking user stars."""

    __tablename__ = "datasite_stars"

    # Star relationship fields
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    datasite_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datasites.id", ondelete="CASCADE"), nullable=False
    )
    starred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Indexes for performance and uniqueness
    __table_args__ = (
        Index("idx_datasite_stars_user_id", "user_id"),
        Index("idx_datasite_stars_datasite_id", "datasite_id"),
        Index(
            "idx_datasite_stars_unique", "user_id", "datasite_id", unique=True
        ),  # Prevent duplicate stars
        Index("idx_datasite_stars_starred_at", "starred_at"),
    )

    def __repr__(self) -> str:
        """String representation of DatasiteStar."""
        return f"<DatasiteStar(id={self.id}, user_id={self.user_id}, datasite_id={self.datasite_id})>"
