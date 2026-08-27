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
from syfthub.repositories.user import UserRepository
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
        # Only for the legacy users.domain mirror; see _mirror_legacy_domain.
        self.user_repository = UserRepository(session)

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
        self._mirror_legacy_domain(user_id, ref)
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
        self._mirror_legacy_domain(user_id, updated)
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

    def resolve_existing(
        self,
        user_id: int,
        satellite_id: Optional[uuid.UUID] = None,
        kind: Optional[SatelliteKind] = SatelliteKind.SPACE,
    ) -> Optional[SatelliteRef]:
        """Pick the satellite a write belongs to, without creating one.

            explicit satellite_id  ->  use it (must belong to the caller)
            account owns exactly 1 ->  use it            <- every account today
            account owns 2+        ->  refuse, naming the ambiguity
            account owns 0         ->  None

        The count is over one ``kind``, defaulting to spaces. An account may run
        a station alongside its single space; counting both would make every
        endpoint write on that account ambiguous, for a satellite that can never
        serve endpoints anyway. Pass ``kind=None`` to count all of them.

        The 1-satellite branch is why this rollout is safe: nothing changes for
        anyone until they add a second space, at which point the ambiguity is
        real and guessing would corrupt data.

        ``None`` is for writes that carry no URL — publish and sync. They leave
        the endpoint unattached rather than failing, which is exactly what
        happens today for an account that has never reported a domain.

        Raises:
            NotFoundError: An explicit satellite_id that is not the caller's.
            AmbiguousSatelliteError: 2+ satellites and no explicit choice.
        """
        if satellite_id is not None:
            return self._require(user_id, satellite_id)

        owned = self.satellite_repository.list_for_user(user_id, kind=kind)
        if len(owned) == 1:
            return owned[0]
        if len(owned) > 1:
            raise AmbiguousSatelliteError(len(owned))
        return None

    def resolve(
        self,
        user_id: int,
        satellite_id: Optional[uuid.UUID] = None,
        reported_url: Optional[str] = None,
        kind: SatelliteKind = SatelliteKind.SPACE,
    ) -> SatelliteRef:
        """Same rule, but register from the reported URL if the account owns none.

        For writes that carry a URL — today only the health report, which has
        always sent one, so no space-side change is needed.

        Raises:
            NotFoundError: An explicit satellite_id that is not the caller's.
            AmbiguousSatelliteError: 2+ satellites and no explicit choice.
            ValidationError: No satellites, and no URL to register one from.
        """
        ref = self.resolve_existing(user_id, satellite_id, kind=kind)
        if ref is not None:
            return ref

        if not reported_url:
            raise ValidationError(
                "This account has no satellites yet; register one, or send the "
                "URL this request is for"
            )
        return self.satellite_repository.register(
            user_id=user_id, kind=kind, base_url=BaseUrl(reported_url)
        )

    def record_heartbeat(
        self,
        user_id: int,
        reported_url: str,
        satellite_id: Optional[uuid.UUID] = None,
    ) -> SatelliteRef:
        """Resolve the satellite a health report is for and record its origin.

        Replaces the ``users.domain`` update this used to perform. That was one
        field for the whole account, so two spaces overwrote each other on every
        cycle and whichever reported last decided where *all* the account's
        endpoints appeared to live. Each satellite now writes its own row.

        Raises:
            NotFoundError: An explicit satellite_id that is not the caller's.
            AmbiguousSatelliteError: 2+ satellites and no explicit choice.
            ConflictError: Another of the account's satellites claims this origin.
        """
        ref = self.resolve(user_id, satellite_id, reported_url)
        base_url = BaseUrl(reported_url)
        if ref.base_url == base_url:
            # Same origin as last time: record liveness only.
            self.satellite_repository.touch_last_seen(ref.id)
            return ref

        self.satellite_repository.set_base_url(ref.id, base_url)
        moved = self.satellite_repository.get_by_public_id(user_id, ref.public_id)
        if moved is not None:
            self._mirror_legacy_domain(user_id, moved)
            return moved
        return ref

    def register_or_move_space(self, user_id: int, base_url: str) -> SatelliteRef:
        """Point the account's space at this origin, registering one if it has none.

        Backs the legacy ``PUT /users/me {domain}`` path, which carries no
        satellite id and which spaces have always called at setup. It must
        **move** the existing space rather than add one: a space whose public URL
        changed between deployments would otherwise leave the account owning two
        satellites, and every subsequent endpoint write would then be ambiguous.

        Raises:
            AmbiguousSatelliteError: The account already owns several spaces, so
                this id-less call cannot say which one is meant.
            ConflictError: A sibling satellite already claims the origin.
        """
        url = BaseUrl(base_url)
        existing = self.resolve_existing(user_id)
        if existing is None:
            registered = self.satellite_repository.register(
                user_id=user_id, kind=SatelliteKind.SPACE, base_url=url
            )
            self._mirror_legacy_domain(user_id, registered)
            return registered
        if existing.base_url == url:
            return existing
        moved = self.satellite_repository.move(existing.id, url)
        result = moved if moved is not None else existing
        self._mirror_legacy_domain(user_id, result)
        return result

    def _mirror_legacy_domain(self, user_id: int, ref: SatelliteRef) -> None:
        """Keep ``users.domain`` in step with the account's single space.

        Rollback insurance. Nothing reads the column any more, but if this
        release is rolled back the previous code does, and a value frozen at
        deploy time would send every endpoint to wherever the space used to be.

        Mirrored **only when the account has exactly one space** — which is the
        only situation the column could ever represent, and the only one a
        rollback could land in. An account with two spaces is post-migration by
        definition, and no single field can describe it.
        """
        if ref.kind is not SatelliteKind.SPACE:
            return
        spaces = self.satellite_repository.list_for_user(
            user_id, kind=SatelliteKind.SPACE
        )
        if len(spaces) != 1 or spaces[0].id != ref.id:
            return
        if self.user_repository.set_legacy_domain(user_id, ref.base_url.value):
            self.session.commit()

    def primary_space_url(self, user_id: int) -> Optional[str]:
        """The origin to show as "the account's domain", or None.

        A domain is per-endpoint now, so this exists only to keep the
        per-account ``domain`` field on the profile responses meaningful. It is
        the account's oldest **space** — never a station, whose origin is not
        where anything is served from.

        Returns None for an account with no space, which is the honest answer
        and what the field already carried for such accounts.
        """
        spaces = self.satellite_repository.list_for_user(
            user_id, kind=SatelliteKind.SPACE
        )
        return spaces[0].base_url.value if spaces else None

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
