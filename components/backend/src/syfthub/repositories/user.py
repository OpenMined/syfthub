"""User repository for database operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.user import UserModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.user import User, UserCreate, UserUpdate

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserRepository(BaseRepository[UserModel]):
    """Repository for user database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, UserModel)

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        try:
            stmt = select(self.model).where(self.model.username == username.lower())
            result = self.session.execute(stmt)
            user_model = result.scalar_one_or_none()

            if user_model:
                return User.model_validate(user_model)
            return None
        except Exception:
            return None

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        try:
            stmt = select(self.model).where(self.model.email == email.lower())
            result = self.session.execute(stmt)
            user_model = result.scalar_one_or_none()

            if user_model:
                return User.model_validate(user_model)
            return None
        except Exception:
            return None

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        try:
            user_model = self.session.get(self.model, user_id)
            if user_model:
                return User.model_validate(user_model)
            return None
        except Exception:
            return None

    def get_by_google_id(self, google_id: str) -> Optional[User]:
        """Get user by Google OAuth ID."""
        try:
            stmt = select(self.model).where(self.model.google_id == google_id)
            result = self.session.execute(stmt)
            user_model = result.scalar_one_or_none()

            if user_model:
                return User.model_validate(user_model)
            return None
        except Exception:
            return None

    def create_user(
        self,
        user_data: UserCreate,
        password_hash: Optional[str] = None,
        accounting_service_url: Optional[str] = None,
        accounting_password: Optional[str] = None,
        auth_provider: str = "local",
        google_id: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Optional[User]:
        """Create a new user.

        Args:
            user_data: User creation data (username, email, full_name)
            password_hash: Hashed password (required for local auth, None for OAuth)
            accounting_service_url: URL to accounting service
            accounting_password: Password for accounting service
            auth_provider: Authentication provider ('local' or 'google')
            google_id: Google OAuth user ID (for Google auth)
            avatar_url: URL to user's avatar image
        """
        try:
            user_model = UserModel(
                username=user_data.username.lower(),
                email=user_data.email.lower(),
                full_name=user_data.full_name,
                password_hash=password_hash,
                is_active=True,
                accounting_service_url=accounting_service_url,
                accounting_password=accounting_password,
                auth_provider=auth_provider,
                google_id=google_id,
                avatar_url=avatar_url,
            )

            self.session.add(user_model)
            self.session.commit()
            self.session.refresh(user_model)

            return User.model_validate(user_model)
        except Exception:
            self.session.rollback()
            return None

    def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[User]:
        """Update user information."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return None

            # Update fields if provided
            if user_data.username is not None:
                user_model.username = user_data.username.lower()
            if user_data.email is not None:
                user_model.email = user_data.email.lower()
            if user_data.full_name is not None:
                user_model.full_name = user_data.full_name
            if user_data.avatar_url is not None:
                user_model.avatar_url = user_data.avatar_url
            if user_data.is_active is not None:
                user_model.is_active = user_data.is_active
            # Accounting fields
            if user_data.accounting_service_url is not None:
                user_model.accounting_service_url = user_data.accounting_service_url
            if user_data.accounting_password is not None:
                user_model.accounting_password = user_data.accounting_password
            if "domain" in user_data.model_fields_set:
                user_model.domain = user_data.domain
            # Aggregator URL
            if user_data.aggregator_url is not None:
                user_model.aggregator_url = user_data.aggregator_url

            self.session.commit()
            self.session.refresh(user_model)

            return User.model_validate(user_model)
        except Exception:
            self.session.rollback()
            return None

    def update_password(self, user_id: int, new_password_hash: str) -> bool:
        """Update user password hash."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.password_hash = new_password_hash
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def link_google_account(
        self, user_id: int, google_id: str, avatar_url: Optional[str] = None
    ) -> bool:
        """Link a Google account to an existing user.

        Args:
            user_id: ID of the user to update
            google_id: Google OAuth user ID
            avatar_url: Google profile picture URL (optional)

        Returns:
            True if update was successful, False otherwise
        """
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.google_id = google_id
            if avatar_url and not user_model.avatar_url:
                user_model.avatar_url = avatar_url

            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def update_user_role(self, user_id: int, role: str) -> bool:
        """Update user role."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.role = role
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user account."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.is_active = False
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def activate_user(self, user_id: int) -> bool:
        """Activate a user account."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.is_active = True
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def update_heartbeat(
        self,
        user_id: int,
        domain: str,
        last_heartbeat_at: datetime,
        heartbeat_expires_at: datetime,
    ) -> bool:
        """Update user heartbeat information.

        Args:
            user_id: ID of the user to update
            domain: Normalized domain from the heartbeat URL
            last_heartbeat_at: When the heartbeat was received
            heartbeat_expires_at: When the heartbeat expires

        Returns:
            True if update was successful, False otherwise
        """
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.domain = domain
            user_model.last_heartbeat_at = last_heartbeat_at
            user_model.heartbeat_expires_at = heartbeat_expires_at

            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def username_exists(self, username: str) -> bool:
        """Check if username already exists."""
        return self.exists(username=username.lower())

    def email_exists(self, email: str) -> bool:
        """Check if email already exists."""
        return self.exists(email=email.lower())

    def delete(self, user_id: int) -> bool:
        """Delete a user by ID."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            self.session.delete(user_model)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def create(self, data=None, **kwargs) -> Optional[User]:
        """Create a new user with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            user_model = self.model(**kwargs)
            self.session.add(user_model)
            self.session.commit()
            self.session.refresh(user_model)
            return User.model_validate(user_model)
        except Exception:
            self.session.rollback()
            return None

    def get_all(
        self, skip: int = 0, limit: int = 100, filters: Optional[dict] = None
    ) -> list[User]:
        """Get all users with pagination and filtering."""
        try:
            user_models = super().get_all(skip=skip, limit=limit, filters=filters)
            return [User.model_validate(user_model) for user_model in user_models]
        except Exception:
            return []

    def update(self, user_id: int, data=None, **kwargs) -> Optional[User]:
        """Update a user with data dict or kwargs (for test compatibility)."""
        try:
            if data is not None:
                kwargs.update(data)
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return None

            for field, value in kwargs.items():
                if hasattr(user_model, field):
                    setattr(user_model, field, value)

            self.session.commit()
            self.session.refresh(user_model)
            return User.model_validate(user_model)
        except Exception:
            self.session.rollback()
            return None

    def count(self, filters: Optional[dict] = None) -> int:
        """Count users with optional filtering."""
        return super().count(filters)

    def exists_username(self, username: str) -> bool:
        """Check if username exists (alias for test compatibility)."""
        return self.username_exists(username)

    def exists_email(self, email: str) -> bool:
        """Check if email exists (alias for test compatibility)."""
        return self.email_exists(email)
