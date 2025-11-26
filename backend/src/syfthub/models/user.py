"""User database model."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.datasite import DatasiteModel
    from syfthub.models.organization import OrganizationMemberModel


class UserModel(BaseModel, TimestampMixin):
    """User database model."""

    __tablename__ = "users"

    # User fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(
        String(88), nullable=False
    )  # Base64 encoded Ed25519 public key
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    key_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    datasites: Mapped[List["DatasiteModel"]] = relationship(
        "DatasiteModel", back_populates="user", cascade="all, delete-orphan"
    )
    organization_memberships: Mapped[List["OrganizationMemberModel"]] = relationship(
        "OrganizationMemberModel", back_populates="user", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_public_key", "public_key", unique=True),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
