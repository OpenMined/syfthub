"""Satellite repository.

Unlike its neighbours, this repository does not swallow ``SQLAlchemyError``.
Resolution branches on how many satellites an account owns, and zero means
"register one" — a swallowed error returning ``[]`` would read as "no
satellites" and silently create a duplicate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from syfthub.domain.base_url import BaseUrl
from syfthub.domain.exceptions import ConflictError
from syfthub.domain.satellite import SatelliteKind, SatelliteRef
from syfthub.models.satellite import SatelliteModel
from syfthub.repositories.base import BaseRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _to_ref(model: SatelliteModel) -> SatelliteRef:
    """Convert a row to a session-detached domain reference."""
    return SatelliteRef(
        id=model.id,
        public_id=model.public_id,
        user_id=model.user_id,
        kind=SatelliteKind(model.kind),
        base_url=BaseUrl(model.base_url),
        created_at=model.created_at,
        last_seen_at=model.last_seen_at,
    )


class SatelliteRepository(BaseRepository[SatelliteModel]):
    """Repository for satellite database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, SatelliteModel)

    # ---------------------------------------------------------------- lookups

    def get_by_public_id(
        self, user_id: int, public_id: uuid.UUID
    ) -> Optional[SatelliteRef]:
        """Get one satellite the account owns, or None.

        Owner-scoped, so another account's identifier reads as nonexistent and
        cannot be probed for.
        """
        stmt = select(self.model).where(
            self.model.user_id == user_id,
            self.model.public_id == public_id,
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        return _to_ref(model) if model else None

    def list_for_user(self, user_id: int) -> list[SatelliteRef]:
        """Every satellite the account owns, oldest first.

        Ordered by ``id``, not ``created_at``, so the graduated rule's
        one-satellite branch stays deterministic for same-transaction rows.
        """
        stmt = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.id)
        )
        return [_to_ref(m) for m in self.session.execute(stmt).scalars().all()]

    def find_by_base_url(
        self, user_id: int, base_url: BaseUrl
    ) -> Optional[SatelliteRef]:
        """Get the account's satellite at this origin, or None.

        Exact match: ``BaseUrl`` has already canonicalised both sides.
        """
        stmt = select(self.model).where(
            self.model.user_id == user_id,
            self.model.base_url == base_url.value,
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        return _to_ref(model) if model else None

    # ---------------------------------------------------------------- writes

    def register(
        self, user_id: int, kind: SatelliteKind, base_url: BaseUrl
    ) -> SatelliteRef:
        """Register a new satellite.

        Named ``register``, not ``create``: overriding
        ``BaseRepository.create(**kwargs)`` with a different signature would
        break substitutability.

        Commits, per this package's convention. A satellite abandoned by a
        failing caller is harmless — it holds no catalogue data, and the next
        request for the same origin resolves to it.

        Raises:
            ConflictError: This account already has a satellite at this origin.
        """
        model = SatelliteModel(
            user_id=user_id, kind=kind.value, base_url=base_url.value
        )
        self.session.add(model)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            logger.info("Satellite create conflicted for user %s on base_url", user_id)
            raise ConflictError("satellite", "base_url") from None
        self.session.refresh(model)
        return _to_ref(model)

    def set_base_url(self, satellite_id: int, base_url: BaseUrl) -> None:
        """Record the origin a satellite reported, and that it was seen.

        The heartbeat write. Unlike the ``users.domain`` update it replaces, two
        hosts cannot overwrite each other: each writes its own row.

        Raises:
            ConflictError: A sibling satellite already claims the origin.
        """
        model = self.session.get(self.model, satellite_id)
        if model is None:
            return
        model.base_url = base_url.value
        model.last_seen_at = datetime.now(timezone.utc)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ConflictError("satellite", "base_url") from None

    def move(self, satellite_id: int, base_url: BaseUrl) -> Optional[SatelliteRef]:
        """Point a satellite at a new origin, keeping its identity.

        Distinct from ``set_base_url``, which is the heartbeat write and also
        stamps ``last_seen_at``; this is an explicit reconfiguration.

        Raises:
            ConflictError: A sibling satellite already claims the origin.
        """
        model = self.session.get(self.model, satellite_id)
        if model is None:
            return None
        model.base_url = base_url.value
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ConflictError("satellite", "base_url") from None
        self.session.refresh(model)
        return _to_ref(model)

    def touch_last_seen(self, satellite_id: int) -> None:
        """Record a heartbeat without changing the origin."""
        model = self.session.get(self.model, satellite_id)
        if model is None:
            return
        model.last_seen_at = datetime.now(timezone.utc)
        self.session.commit()
