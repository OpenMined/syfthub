"""API Token repository for database operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import and_, select

from syfthub.models.api_token import APITokenModel
from syfthub.repositories.base import BaseRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class APITokenRepository(BaseRepository[APITokenModel]):
    """Repository for API token database operations.

    This repository handles CRUD operations for API tokens. The critical method
    for authentication is get_by_hash(), which is optimized for fast lookups.
    """

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, APITokenModel)

    def get_by_hash(self, token_hash: str) -> Optional[APITokenModel]:
        """Get an API token by its hash.

        This is the primary lookup method used during authentication.
        Returns the raw model (not schema) to allow access to user relationship.

        Args:
            token_hash: SHA-256 hex digest of the token.

        Returns:
            The APITokenModel if found, None otherwise.
        """
        try:
            stmt = select(self.model).where(self.model.token_hash == token_hash)
            result = self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    def get_by_id_for_user(
        self, token_id: int, user_id: int
    ) -> Optional[APITokenModel]:
        """Get an API token by ID, ensuring it belongs to the specified user.

        Args:
            token_id: The token ID.
            user_id: The user ID (for ownership verification).

        Returns:
            The APITokenModel if found and owned by user, None otherwise.
        """
        try:
            stmt = select(self.model).where(
                and_(self.model.id == token_id, self.model.user_id == user_id)
            )
            result = self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    def get_user_tokens(
        self,
        user_id: int,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[APITokenModel]:
        """Get all API tokens for a user.

        Args:
            user_id: The user ID.
            include_inactive: Whether to include revoked tokens.
            skip: Number of records to skip (pagination).
            limit: Maximum number of records to return.

        Returns:
            List of APITokenModel objects.
        """
        try:
            stmt = select(self.model).where(self.model.user_id == user_id)

            if not include_inactive:
                stmt = stmt.where(self.model.is_active == True)  # noqa: E712

            stmt = stmt.order_by(self.model.created_at.desc())
            stmt = stmt.offset(skip).limit(limit)

            result = self.session.execute(stmt)
            return list(result.scalars().all())
        except Exception:
            return []

    def create_token(
        self,
        user_id: int,
        name: str,
        token_prefix: str,
        token_hash: str,
        scopes: List[str],
        expires_at: Optional[datetime] = None,
    ) -> Optional[APITokenModel]:
        """Create a new API token.

        Args:
            user_id: The user ID who owns this token.
            name: User-friendly label for the token.
            token_prefix: First chars of token for display.
            token_hash: SHA-256 hex digest of the full token.
            scopes: List of permission scopes.
            expires_at: Optional expiration timestamp.

        Returns:
            The created APITokenModel if successful, None otherwise.
        """
        try:
            token_model = APITokenModel(
                user_id=user_id,
                name=name,
                token_prefix=token_prefix,
                token_hash=token_hash,
                scopes=scopes,
                expires_at=expires_at,
                is_active=True,
            )

            self.session.add(token_model)
            self.session.commit()
            self.session.refresh(token_model)

            return token_model
        except Exception:
            self.session.rollback()
            return None

    def update_last_used(self, token_id: int, client_ip: Optional[str] = None) -> bool:
        """Update the last used timestamp and IP for a token.

        This method is called during authentication to track token usage.
        It should be fast and non-blocking.

        Args:
            token_id: The token ID.
            client_ip: The client IP address (optional).

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            token_model = self.session.get(self.model, token_id)
            if not token_model:
                return False

            token_model.last_used_at = datetime.now(timezone.utc)
            if client_ip:
                token_model.last_used_ip = client_ip

            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def update_name(
        self, token_id: int, user_id: int, name: str
    ) -> Optional[APITokenModel]:
        """Update the name of an API token.

        Args:
            token_id: The token ID.
            user_id: The user ID (for ownership verification).
            name: The new name.

        Returns:
            The updated APITokenModel if successful, None otherwise.
        """
        try:
            token_model = self.get_by_id_for_user(token_id, user_id)
            if not token_model:
                return None

            token_model.name = name
            self.session.commit()
            self.session.refresh(token_model)

            return token_model
        except Exception:
            self.session.rollback()
            return None

    def revoke(self, token_id: int, user_id: int) -> bool:
        """Revoke an API token (soft delete).

        Args:
            token_id: The token ID.
            user_id: The user ID (for ownership verification).

        Returns:
            True if revoked successfully, False otherwise.
        """
        try:
            token_model = self.get_by_id_for_user(token_id, user_id)
            if not token_model:
                return False

            token_model.is_active = False
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def delete_token(self, token_id: int, user_id: int) -> bool:
        """Hard delete an API token.

        Args:
            token_id: The token ID.
            user_id: The user ID (for ownership verification).

        Returns:
            True if deleted successfully, False otherwise.
        """
        try:
            token_model = self.get_by_id_for_user(token_id, user_id)
            if not token_model:
                return False

            self.session.delete(token_model)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def count_user_tokens(self, user_id: int, active_only: bool = True) -> int:
        """Count the number of tokens for a user.

        Args:
            user_id: The user ID.
            active_only: Whether to count only active tokens.

        Returns:
            The number of tokens.
        """
        filters = {"user_id": user_id}
        if active_only:
            filters["is_active"] = True
        return self.count(filters)

    def hash_exists(self, token_hash: str) -> bool:
        """Check if a token hash already exists.

        Used to prevent hash collisions (extremely unlikely but possible).

        Args:
            token_hash: SHA-256 hex digest of the token.

        Returns:
            True if the hash exists, False otherwise.
        """
        return self.exists(token_hash=token_hash)
