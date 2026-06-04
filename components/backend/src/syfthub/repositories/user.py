"""User repository for database operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.user import UserModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.auth import UserRole
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

    def get_by_ids(self, user_ids: list[int]) -> list[User]:
        """Get multiple users by their IDs in a single query."""
        if not user_ids:
            return []
        try:
            stmt = select(self.model).where(self.model.id.in_(user_ids))
            result = self.session.execute(stmt)
            return [User.model_validate(m) for m in result.scalars().all()]
        except Exception:
            return []

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
        auth_provider: str = "local",
        google_id: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Optional[User]:
        """Create a new user.

        Args:
            user_data: User creation data (username, email, full_name)
            password_hash: Hashed password (required for local auth, None for OAuth)
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
                is_email_verified=user_data.is_email_verified,
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
            if "domain" in user_data.model_fields_set:
                user_model.domain = user_data.domain
            # Aggregator URL
            if user_data.aggregator_url is not None:
                user_model.aggregator_url = user_data.aggregator_url
            # Public profile fields. Use model_fields_set so callers can
            # explicitly clear the bio (set to "") without it being ignored.
            if "bio" in user_data.model_fields_set:
                user_model.bio = user_data.bio
            if user_data.is_email_public is not None:
                user_model.is_email_public = user_data.is_email_public

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

    def get_model_by_email(self, email: str) -> Optional[UserModel]:
        """Get the raw SQLAlchemy user model by email.

        Unlike get_by_email(), this returns the ORM model directly
        so callers can inspect fields like auth_provider and password_hash
        without going through the Pydantic schema.
        """
        try:
            stmt = select(self.model).where(self.model.email == email.lower())
            result = self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    def set_email_verified(self, user_id: int) -> bool:
        """Mark a user's email as verified."""
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.is_email_verified = True
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

    def update_last_login(self, user_id: int) -> bool:
        """Stamp the user's last_login_at to the current UTC time.

        Best-effort: any failure is swallowed (returns False) so it never
        breaks the login flow. Returns True on success, False if the user is
        missing or a DB error occurs.
        """
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.last_login_at = datetime.now(timezone.utc)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def count_by_field_grouped(self, column_name: str) -> dict[str, int]:
        """Return a {value: count} mapping grouped by the given column.

        Uses a portable ``GROUP BY`` (identical on SQLite and Postgres). Only
        used for low-cardinality columns (role, auth_provider).
        """
        try:
            column = getattr(self.model, column_name)
            stmt = select(column, func.count()).group_by(column)
            result = self.session.execute(stmt)
            return {row[0]: row[1] for row in result.all()}
        except SQLAlchemyError:
            return {}

    def count_overview(self) -> dict[str, int]:
        """Return all headline counts in a single aggregate query.

        Collapses what would otherwise be six separate ``COUNT`` round-trips
        into one ``COUNT(CASE WHEN ...)`` scan. Portable across SQLite and
        Postgres. Returns zeros on error.
        """
        try:
            stmt = select(
                func.count().label("total"),
                func.count(case((self.model.is_active.is_(True), 1))).label("active"),
                func.count(case((self.model.is_active.is_(False), 1))).label(
                    "inactive"
                ),
                func.count(case((self.model.is_email_verified.is_(True), 1))).label(
                    "verified"
                ),
                func.count(case((self.model.is_email_verified.is_(False), 1))).label(
                    "unverified"
                ),
                func.count(case((self.model.role == UserRole.ADMIN.value, 1))).label(
                    "admins"
                ),
            )
            row = self.session.execute(stmt).one()
            return {
                "total": row.total,
                "active": row.active,
                "inactive": row.inactive,
                "verified": row.verified,
                "unverified": row.unverified,
                "admins": row.admins,
            }
        except SQLAlchemyError:
            return {
                "total": 0,
                "active": 0,
                "inactive": 0,
                "verified": 0,
                "unverified": 0,
                "admins": 0,
            }

    def count_with_filters(
        self,
        *,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
        role: Optional[str] = None,
    ) -> int:
        """Count users matching the provided equality filters."""
        try:
            stmt = select(func.count()).select_from(self.model)
            if is_active is not None:
                stmt = stmt.where(self.model.is_active == is_active)
            if is_email_verified is not None:
                stmt = stmt.where(self.model.is_email_verified == is_email_verified)
            if role is not None:
                stmt = stmt.where(self.model.role == role)
            result = self.session.execute(stmt)
            return result.scalar_one()
        except SQLAlchemyError:
            return 0

    def get_signup_dates(self, since: Optional[datetime] = None) -> list[datetime]:
        """Return users' ``created_at`` for Python-side bucketing.

        Pulls a single column only (not full rows). When ``since`` is given the
        scan is bounded to ``created_at >= since`` so the trend query stays
        proportional to the requested window rather than the whole table.
        Values may be naive or ISO strings on SQLite; the service normalizes
        them.
        """
        try:
            stmt = select(self.model.created_at)
            if since is not None:
                stmt = stmt.where(self.model.created_at >= since)
            result = self.session.execute(stmt)
            return [row[0] for row in result.all()]
        except SQLAlchemyError:
            return []

    def get_last_login_dates(self) -> list[Optional[datetime]]:
        """Return every user's ``last_login_at`` (including None) for bucketing."""
        try:
            stmt = select(self.model.last_login_at)
            result = self.session.execute(stmt)
            return [row[0] for row in result.all()]
        except SQLAlchemyError:
            return []

    def list_users_admin(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
    ) -> tuple[list[User], int]:
        """Filtered, sortable, paginated user listing for the admin table.

        Returns ``(rows, total)`` where ``total`` is the count of users matching
        the filters BEFORE pagination. Runs exactly two queries (count + page).
        Search uses portable ``lower(col) LIKE`` (no Postgres-only ``ilike``).
        """
        try:
            sort_column = self._admin_sort_column(sort_by)
            conditions = self._admin_filter_conditions(
                search=search,
                role=role,
                is_active=is_active,
                is_email_verified=is_email_verified,
            )

            count_stmt = select(func.count()).select_from(self.model)
            page_stmt = select(self.model)
            for cond in conditions:
                count_stmt = count_stmt.where(cond)
                page_stmt = page_stmt.where(cond)

            total = self.session.execute(count_stmt).scalar_one()

            order = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
            page_stmt = (
                page_stmt.order_by(order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            rows = self.session.execute(page_stmt).scalars().all()
            return [User.model_validate(m) for m in rows], total
        except SQLAlchemyError:
            return [], 0

    def _admin_sort_column(self, sort_by: str) -> Any:
        """Map an admin-table sort key to a model column (defaults to created_at)."""
        allowed_sort = {
            "username": self.model.username,
            "email": self.model.email,
            "role": self.model.role,
            "created_at": self.model.created_at,
            "last_login_at": self.model.last_login_at,
        }
        return allowed_sort.get(sort_by, self.model.created_at)

    def _admin_filter_conditions(
        self,
        *,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
    ) -> list[Any]:
        """Build the WHERE conditions shared by the admin listing and export.

        Search uses portable ``lower(col) LIKE`` (no Postgres-only ``ilike``).
        """
        conditions: list[Any] = []
        if search:
            q = f"%{search.lower()}%"
            conditions.append(
                or_(
                    func.lower(self.model.username).like(q),
                    func.lower(self.model.email).like(q),
                )
            )
        if role is not None:
            conditions.append(self.model.role == role)
        if is_active is not None:
            conditions.append(self.model.is_active == is_active)
        if is_email_verified is not None:
            conditions.append(self.model.is_email_verified == is_email_verified)
        return conditions

    def list_users_for_export(
        self,
        *,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
    ) -> list[User]:
        """All users matching the filters (no pagination), for CSV export.

        Reuses the same filter + sort logic as ``list_users_admin``. Returns an
        empty list on error.
        """
        try:
            conditions = self._admin_filter_conditions(
                search=search,
                role=role,
                is_active=is_active,
                is_email_verified=is_email_verified,
            )
            stmt = select(self.model)
            for cond in conditions:
                stmt = stmt.where(cond)
            sort_column = self._admin_sort_column(sort_by)
            order = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
            stmt = stmt.order_by(order)
            rows = self.session.execute(stmt).scalars().all()
            return [User.model_validate(m) for m in rows]
        except SQLAlchemyError:
            return []

    def update_wallet(
        self,
        user_id: int,
        wallet_address: str,
        wallet_private_key: Optional[str] = None,
    ) -> bool:
        """Update user wallet fields atomically.

        Args:
            user_id: ID of the user to update
            wallet_address: Ethereum/Tempo wallet address
            wallet_private_key: Private key for the wallet (optional, None keeps existing)

        Returns:
            True if update was successful, False otherwise
        """
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return False

            user_model.wallet_address = wallet_address
            if wallet_private_key is not None:
                user_model.wallet_private_key = wallet_private_key

            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def get_wallet_private_key(self, user_id: int) -> Optional[str]:
        """Get wallet private key directly from the DB model.

        This bypasses the User response schema (which intentionally excludes
        the private key) and is meant for server-side operations like the
        ``/pay`` endpoint.

        Returns:
            The private key hex string, or None if not set.
        """
        try:
            user_model = self.session.get(self.model, user_id)
            if not user_model:
                return None
            return user_model.wallet_private_key
        except Exception:
            return None

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
