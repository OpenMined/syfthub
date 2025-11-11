"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
    datasites: Mapped[list[DatasiteModel]] = relationship(
        "DatasiteModel", back_populates="user", cascade="all, delete-orphan"
    )
    items: Mapped[list[ItemModel]] = relationship(
        "ItemModel", back_populates="user", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
    )


class ItemModel(Base):
    """Item database model."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    user: Mapped[UserModel] = relationship("UserModel", back_populates="items")

    # Indexes for performance
    __table_args__ = (
        Index("idx_items_user_id", "user_id"),
        Index("idx_items_is_available", "is_available"),
        Index("idx_items_category", "category"),
        Index("idx_items_price", "price"),
    )


class DatasiteModel(Base):
    """Datasite database model."""

    __tablename__ = "datasites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
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
    user: Mapped[UserModel] = relationship("UserModel", back_populates="datasites")

    # Indexes for performance - slug uniqueness is per-user (like GitHub repos)
    __table_args__ = (
        Index("idx_datasites_user_id", "user_id"),
        Index("idx_datasites_slug", "slug"),
        Index("idx_datasites_user_slug", "user_id", "slug", unique=True),
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
