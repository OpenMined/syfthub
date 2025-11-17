"""Repository pattern for database operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import and_, select

from syfthub.database.models import DatasiteModel, UserModel
from syfthub.schemas.auth import UserRole
from syfthub.schemas.datasite import Connection, Datasite, DatasiteVisibility, Policy
from syfthub.schemas.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserRepository:
    """Repository for user database operations."""

    def __init__(self, session: Session):
        """Initialize with database session."""
        self.session = session

    def create(self, user_data: Dict[str, Any]) -> User:
        """Create a new user."""
        user_model = UserModel(**user_data)
        self.session.add(user_model)
        self.session.commit()
        self.session.refresh(user_model)
        return self._model_to_schema(user_model)

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        stmt = select(UserModel).where(UserModel.id == user_id)
        user_model = self.session.execute(stmt).scalar_one_or_none()
        return self._model_to_schema(user_model) if user_model else None

    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        stmt = select(UserModel).where(UserModel.username == username.lower())
        user_model = self.session.execute(stmt).scalar_one_or_none()
        return self._model_to_schema(user_model) if user_model else None

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        stmt = select(UserModel).where(UserModel.email == email)
        user_model = self.session.execute(stmt).scalar_one_or_none()
        return self._model_to_schema(user_model) if user_model else None

    def get_all(self) -> list[User]:
        """Get all users."""
        stmt = select(UserModel)
        user_models = self.session.execute(stmt).scalars().all()
        return [self._model_to_schema(user_model) for user_model in user_models]

    def update(self, user_id: int, user_data: Dict[str, Any]) -> Optional[User]:
        """Update user by ID."""
        stmt = select(UserModel).where(UserModel.id == user_id)
        user_model = self.session.execute(stmt).scalar_one_or_none()
        if not user_model:
            return None

        # Update fields
        for key, value in user_data.items():
            if hasattr(user_model, key):
                setattr(user_model, key, value)

        user_model.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(user_model)
        return self._model_to_schema(user_model)

    def delete(self, user_id: int) -> bool:
        """Delete user by ID."""
        stmt = select(UserModel).where(UserModel.id == user_id)
        user_model = self.session.execute(stmt).scalar_one_or_none()
        if not user_model:
            return False

        self.session.delete(user_model)
        self.session.commit()
        return True

    def exists_username(
        self, username: str, exclude_user_id: Optional[int] = None
    ) -> bool:
        """Check if username exists."""
        stmt = select(UserModel).where(UserModel.username == username.lower())
        if exclude_user_id:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def exists_email(self, email: str, exclude_user_id: Optional[int] = None) -> bool:
        """Check if email exists."""
        stmt = select(UserModel).where(UserModel.email == email)
        if exclude_user_id:
            stmt = stmt.where(UserModel.id != exclude_user_id)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    @staticmethod
    def _model_to_schema(user_model: UserModel) -> User:
        """Convert UserModel to User schema."""
        return User(
            id=user_model.id,
            username=user_model.username,
            email=user_model.email,
            full_name=user_model.full_name,
            age=user_model.age,
            role=UserRole(user_model.role),
            password_hash=user_model.password_hash,
            public_key=user_model.public_key,
            is_active=user_model.is_active,
            created_at=user_model.created_at,
            updated_at=user_model.updated_at,
            key_created_at=user_model.key_created_at,
        )


class DatasiteRepository:
    """Repository for datasite database operations."""

    def __init__(self, session: Session):
        """Initialize with database session."""
        self.session = session

    def create(self, datasite_data: Dict[str, Any]) -> Datasite:
        """Create a new datasite."""
        datasite_model = DatasiteModel(**datasite_data)
        self.session.add(datasite_model)
        self.session.commit()
        self.session.refresh(datasite_model)
        return self._model_to_schema(datasite_model)

    def get_by_id(self, datasite_id: int) -> Optional[Datasite]:
        """Get datasite by ID."""
        stmt = select(DatasiteModel).where(DatasiteModel.id == datasite_id)
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        return self._model_to_schema(datasite_model) if datasite_model else None

    def get_by_user_and_slug(self, user_id: int, slug: str) -> Optional[Datasite]:
        """Get datasite by user ID and slug."""
        stmt = select(DatasiteModel).where(
            and_(DatasiteModel.user_id == user_id, DatasiteModel.slug == slug)
        )
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        return self._model_to_schema(datasite_model) if datasite_model else None

    def get_by_user_id(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> list[Datasite]:
        """Get datasites by user ID."""
        stmt = select(DatasiteModel).where(DatasiteModel.user_id == user_id)

        if not include_inactive:
            stmt = stmt.where(DatasiteModel.is_active == True)  # noqa: E712

        stmt = stmt.offset(skip).limit(limit)
        datasite_models = self.session.execute(stmt).scalars().all()
        return [
            self._model_to_schema(datasite_model) for datasite_model in datasite_models
        ]

    def get_public_by_user_id(
        self, user_id: int, skip: int = 0, limit: int = 100
    ) -> list[Datasite]:
        """Get public datasites by user ID."""
        stmt = (
            select(DatasiteModel)
            .where(
                and_(
                    DatasiteModel.user_id == user_id,
                    DatasiteModel.is_active == True,  # noqa: E712
                    DatasiteModel.visibility == DatasiteVisibility.PUBLIC,
                )
            )
            .offset(skip)
            .limit(limit)
        )
        datasite_models = self.session.execute(stmt).scalars().all()
        return [
            self._model_to_schema(datasite_model) for datasite_model in datasite_models
        ]

    def update(
        self, datasite_id: int, datasite_data: Dict[str, Any]
    ) -> Optional[Datasite]:
        """Update datasite by ID."""
        stmt = select(DatasiteModel).where(DatasiteModel.id == datasite_id)
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        if not datasite_model:
            return None

        # Update fields
        for key, value in datasite_data.items():
            if hasattr(datasite_model, key):
                setattr(datasite_model, key, value)

        datasite_model.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(datasite_model)
        return self._model_to_schema(datasite_model)

    def delete(self, datasite_id: int) -> bool:
        """Delete datasite by ID."""
        stmt = select(DatasiteModel).where(DatasiteModel.id == datasite_id)
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        if not datasite_model:
            return False

        self.session.delete(datasite_model)
        self.session.commit()
        return True

    def slug_exists_for_user(
        self, user_id: int, slug: str, exclude_datasite_id: Optional[int] = None
    ) -> bool:
        """Check if slug exists for user."""
        stmt = select(DatasiteModel).where(
            and_(DatasiteModel.user_id == user_id, DatasiteModel.slug == slug)
        )
        if exclude_datasite_id:
            stmt = stmt.where(DatasiteModel.id != exclude_datasite_id)

        return self.session.execute(stmt).scalar_one_or_none() is not None

    def get_most_starred(
        self, skip: int = 0, limit: int = 100, min_stars: int = 0
    ) -> list[Datasite]:
        """Get datasites ordered by stars count (most popular first)."""
        stmt = (
            select(DatasiteModel)
            .where(
                and_(
                    DatasiteModel.is_active == True,  # noqa: E712
                    DatasiteModel.visibility == DatasiteVisibility.PUBLIC,
                    DatasiteModel.stars_count >= min_stars,
                )
            )
            .order_by(DatasiteModel.stars_count.desc(), DatasiteModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        datasite_models = self.session.execute(stmt).scalars().all()
        return [
            self._model_to_schema(datasite_model) for datasite_model in datasite_models
        ]

    def increment_stars(self, datasite_id: int) -> bool:
        """Increment the stars count for a datasite."""
        stmt = select(DatasiteModel).where(DatasiteModel.id == datasite_id)
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        if not datasite_model:
            return False

        datasite_model.stars_count += 1
        self.session.commit()
        return True

    def decrement_stars(self, datasite_id: int) -> bool:
        """Decrement the stars count for a datasite (with minimum of 0)."""
        stmt = select(DatasiteModel).where(DatasiteModel.id == datasite_id)
        datasite_model = self.session.execute(stmt).scalar_one_or_none()
        if not datasite_model:
            return False

        datasite_model.stars_count = max(0, datasite_model.stars_count - 1)
        self.session.commit()
        return True

    @staticmethod
    def _model_to_schema(datasite_model: DatasiteModel) -> Datasite:
        """Convert DatasiteModel to Datasite schema."""
        return Datasite(
            id=datasite_model.id,
            user_id=datasite_model.user_id,
            name=datasite_model.name,
            slug=datasite_model.slug,
            description=datasite_model.description,
            visibility=DatasiteVisibility(datasite_model.visibility),
            is_active=datasite_model.is_active,
            contributors=datasite_model.contributors,
            version=datasite_model.version,
            readme=datasite_model.readme,
            stars_count=datasite_model.stars_count,
            policies=[Policy(**policy_data) for policy_data in datasite_model.policies],
            connect=[
                Connection(**connection_data)
                for connection_data in datasite_model.connect
            ],
            created_at=datasite_model.created_at,
            updated_at=datasite_model.updated_at,
        )
