"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime, timezone

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""


class UserModel(Base):
    """User database model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(
        String(88), nullable=False
    )  # Base64 encoded Ed25519 public key
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    key_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    datasites: Mapped[list[DatasiteModel]] = relationship(
        "DatasiteModel", back_populates="user", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_public_key", "public_key", unique=True),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
    )


class OrganizationModel(Base):
    """Organization database model."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    members: Mapped[list[OrganizationMemberModel]] = relationship(
        "OrganizationMemberModel",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    datasites: Mapped[list[DatasiteModel]] = relationship(
        "DatasiteModel", back_populates="organization", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index("idx_organizations_name", "name"),
        Index("idx_organizations_is_active", "is_active"),
    )


class OrganizationMemberModel(Base):
    """Organization member database model."""

    __tablename__ = "organization_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
    organization: Mapped[OrganizationModel] = relationship(
        "OrganizationModel", back_populates="members"
    )
    user: Mapped[UserModel] = relationship("UserModel")

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


class DatasiteModel(Base):
    """Datasite database model."""

    __tablename__ = "datasites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="public"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contributors: Mapped[list[int]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="0.1.0")
    readme: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    policies: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )
    connect: Mapped[list[dict]] = mapped_column(
        JSON, nullable=False, default=lambda: []
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped[UserModel | None] = relationship(
        "UserModel", back_populates="datasites"
    )
    organization: Mapped[OrganizationModel | None] = relationship(
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


class DatasiteStarModel(Base):
    """Datasite star relationship model for tracking user stars."""

    __tablename__ = "datasite_stars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
