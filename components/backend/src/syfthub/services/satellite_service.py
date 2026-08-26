"""Satellite management and resolution.

Two responsibilities, kept together because they share a repository and the
resolution rule is small: CRUD for the ``/satellites`` endpoints, and
``resolve()`` — the single answer to "which satellite is this write for".

``resolve()`` is the important half. Every write path that used to update
``users.domain`` account-wide goes through it, and they must all agree; five
copies of these branches would drift into either misattributed endpoints or a
token minted for the wrong audience.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from syfthub.domain.base_url import BaseUrl
from syfthub.domain.exceptions import NotFoundError, ValidationError
from syfthub.domain.satellite import (
    AmbiguousSatelliteError,
    SatelliteKind,
    SatelliteRef,
)
from syfthub.repositories.satellite import SatelliteRepository
from syfthub.schemas.satellite import (
    SatelliteCreate,
    SatelliteResponse,
    SatelliteUpdate,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SatelliteService(BaseService):
    """Manages an account's satellites and resolves writes to one of them."""

    def __init__(self, session: Session):
        """Initialize satellite service."""
        super().__init__(session)
        self.satellite_repository = SatelliteRepository(session)

    # ------------------------------------------------------------------ CRUD

    def list_satellites(self, user_id: int) -> list[SatelliteResponse]:
        """Every satellite the account owns, oldest first."""
        return [
            _to_response(ref)
            for ref in self.satellite_repository.list_for_user(user_id)
        ]

    def get_satellite(self, user_id: int, satellite_id: uuid.UUID) -> SatelliteResponse:
        """Get one satellite the account owns.

        Raises:
            NotFoundError: No such satellite on this account.
        """
        return _to_response(self._require(user_id, satellite_id))

    def create_satellite(
        self, user_id: int, data: SatelliteCreate
    ) -> SatelliteResponse:
        """Register a satellite.

        Stations must be registered explicitly: they serve no endpoints and so
        never report health, meaning they would never acquire a row implicitly.

        Raises:
            ConflictError: This account already has a satellite at this origin.
        """
        ref = self.satellite_repository.register(
            user_id=user_id, kind=data.kind, base_url=BaseUrl(data.base_url)
        )
        return _to_response(ref)

    def update_satellite(
        self, user_id: int, satellite_id: uuid.UUID, data: SatelliteUpdate
    ) -> SatelliteResponse:
        """Move a satellite to a new origin, keeping its identifier.

        Raises:
            NotFoundError: No such satellite on this account.
            ConflictError: A sibling satellite already claims the origin.
        """
        ref = self._require(user_id, satellite_id)
        updated = self.satellite_repository.move(ref.id, BaseUrl(data.base_url))
        if updated is None:
            raise NotFoundError("Satellite", str(satellite_id))
        return _to_response(updated)

    def delete_satellite(self, user_id: int, satellite_id: uuid.UUID) -> None:
        """Delete a satellite and every endpoint it served.

        "Delete this space" means the space and what it served. The endpoints go
        via the FK's ON DELETE CASCADE — leaving them behind deactivated would
        keep their slugs held and block the owner from republishing them.

        Callers should confirm first: this also takes each endpoint's stars,
        uptime history, and collective memberships, none of which a resync can
        restore.

        Raises:
            NotFoundError: No such satellite on this account.
        """
        ref = self._require(user_id, satellite_id)
        self.satellite_repository.delete(ref.id)

    # ------------------------------------------------------------- resolution

    def resolve(
        self,
        user_id: int,
        satellite_id: Optional[uuid.UUID] = None,
        reported_url: Optional[str] = None,
        kind: SatelliteKind = SatelliteKind.SPACE,
    ) -> SatelliteRef:
        """Decide which satellite a write belongs to.

            explicit satellite_id  ->  use it (must belong to the caller)
            account owns 0         ->  register one from the reported URL
            account owns exactly 1 ->  use it            <- every account today
            account owns 2+        ->  refuse, naming the ambiguity

        The 1-satellite branch is why this rollout is safe: nothing changes for
        anyone until they add a second space, at which point the ambiguity is
        real and guessing would corrupt data.

        Args:
            user_id: The account the write is authenticated as.
            satellite_id: Explicit choice, if the caller made one.
            reported_url: Origin the caller reported, used only to register a
                first satellite for an account that owns none.
            kind: What to register in that case.

        Raises:
            NotFoundError: An explicit satellite_id that is not the caller's.
            AmbiguousSatelliteError: 2+ satellites and no explicit choice.
            ValidationError: No satellites, and no URL to register one from.
        """
        if satellite_id is not None:
            return self._require(user_id, satellite_id)

        owned = self.satellite_repository.list_for_user(user_id)
        if len(owned) == 1:
            return owned[0]
        if len(owned) > 1:
            raise AmbiguousSatelliteError(len(owned))

        if not reported_url:
            raise ValidationError(
                "This account has no satellites yet; register one, or send the "
                "URL this request is for"
            )
        return self.satellite_repository.register(
            user_id=user_id,
            kind=kind,
            base_url=BaseUrl(reported_url),
        )

    # ----------------------------------------------------------------- helper

    def _require(self, user_id: int, satellite_id: uuid.UUID) -> SatelliteRef:
        """Fetch a satellite the account owns, or raise.

        Owner-scoped, so someone else's identifier is reported as missing rather
        than forbidden — it cannot be used to probe for satellites.
        """
        ref = self.satellite_repository.get_by_public_id(user_id, satellite_id)
        if ref is None:
            raise NotFoundError("Satellite", str(satellite_id))
        return ref


def _to_response(ref: SatelliteRef) -> SatelliteResponse:
    """Project a satellite onto its API shape, exposing public_id as ``id``."""
    return SatelliteResponse(
        id=ref.public_id,
        kind=ref.kind,
        base_url=ref.base_url.value,
        last_seen_at=ref.last_seen_at,
        created_at=ref.created_at,
    )
