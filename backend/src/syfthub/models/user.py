"""User database model."""

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.organization import OrganizationMemberModel


class UserModel(BaseModel, TimestampMixin):
    """User database model."""

    __tablename__ = "users"

    # User fields
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Accounting service credentials (for external billing integration)
    accounting_service_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, default=None
    )
    accounting_password: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Domain for dynamic endpoint URL construction
    domain: Mapped[Optional[str]] = mapped_column(
        String(253), nullable=True, default=None
    )

    # Relationships
    endpoints: Mapped[List["EndpointModel"]] = relationship(
        "EndpointModel", back_populates="user", cascade="all, delete-orphan"
    )
    organization_memberships: Mapped[List["OrganizationMemberModel"]] = relationship(
        "OrganizationMemberModel", back_populates="user", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
        Index("idx_users_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        """String representation of User."""
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
