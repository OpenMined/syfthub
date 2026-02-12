"""API Token database model for personal access tokens."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.user import UserModel


class APITokenModel(BaseModel, TimestampMixin):
    """API Token database model for personal access tokens.

    API tokens provide an alternative authentication method to username/password.
    Tokens are stored as SHA-256 hashes for security - the plaintext token is
    only shown once at creation time.

    Attributes:
        user_id: The ID of the user who owns this token.
        name: A user-friendly label for the token (e.g., "CI/CD Pipeline").
        token_prefix: First 12-16 chars of the token for identification (e.g., "syft_pat_aB3d").
        token_hash: SHA-256 hex digest of the full token (64 chars).
        scopes: List of permission scopes (e.g., ["read"], ["write"], ["full"]).
        expires_at: Optional expiration timestamp. Null means never expires.
        last_used_at: Timestamp of the last successful authentication.
        last_used_ip: IP address from the last successful authentication.
        is_active: Whether the token is active (False = revoked).
    """

    __tablename__ = "api_tokens"

    # Owner relationship
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Token identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Permissions - scopes as JSON array
    # Valid scopes: "read", "write", "full" (V1)
    # Future: "endpoints:read", "endpoints:write", "profile:read", etc.
    scopes: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["full"]
    )

    # Expiration - null means never expires
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Usage tracking
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_used_ip: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        default=None,  # IPv6 max length
    )

    # Soft delete for revocation (keeps audit trail)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationship to user (one-way for now)
    user: Mapped["UserModel"] = relationship("UserModel", lazy="joined")

    # Indexes for performance
    __table_args__ = (
        # Primary lookup index - must be unique for auth
        Index("idx_api_tokens_token_hash", "token_hash", unique=True),
        # For listing user's tokens
        Index("idx_api_tokens_user_id", "user_id"),
        # For listing active tokens for a user
        Index("idx_api_tokens_user_active", "user_id", "is_active"),
        # For cleanup of expired tokens
        Index("idx_api_tokens_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:
        """String representation of APIToken."""
        return (
            f"<APIToken(id={self.id}, user_id={self.user_id}, "
            f"name='{self.name}', prefix='{self.token_prefix}')>"
        )
