"""Satellite database model.

One row per service an account owns. Replaces ``users.domain``, a single string
that could only ever describe one host per account.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.domain.base_url import MAX_BASE_URL_LENGTH
from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.user import UserModel


class SatelliteModel(BaseModel, TimestampMixin):
    """A space or station owned by a Hub account."""

    __tablename__ = "satellites"

    # The identifier that leaves the Hub; ``id`` stays internal. Splitting them
    # makes public_id rotatable: reissuing it fails the audience check on every
    # outstanding token for this satellite, with no revocation list. Immediate
    # for POST /verify; local JWKS verifiers lag until they re-read config.
    #
    # gen_random_uuid() server default on PostgreSQL, matching users.public_id.
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), unique=True, nullable=False, default=uuid.uuid4
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # "space" | "station" — see domain.satellite.SatelliteKind.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)

    # Account-scoped handle, for humans and URLs.
    slug: Mapped[str] = mapped_column(String(64), nullable=False)

    # Canonical origin, normalised by BaseUrl before it is written. Nullable: a
    # satellite may be registered before it first reports in, and a station
    # never needs one.
    base_url: Mapped[Optional[str]] = mapped_column(
        String(MAX_BASE_URL_LENGTH), nullable=True, default=None
    )

    # Last heartbeat. Distinct from endpoint health: a satellite can be
    # reachable while an endpoint it serves is not.
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="satellites")
    # No cascade: deleting a satellite orphans its endpoints rather than
    # destroying catalogue entries and the addresses buyers hold. The FK's
    # ON DELETE SET NULL is the backstop.
    endpoints: Mapped[List["EndpointModel"]] = relationship(
        "EndpointModel", back_populates="space"
    )

    __table_args__ = (
        Index("idx_satellites_public_id", "public_id", unique=True),
        Index("idx_satellites_user_id", "user_id"),
        # One slug and one origin per account — the latter is what makes an
        # origin usable as a resolution key. NULLs are distinct in a unique
        # index, so any number of not-yet-reported satellites coexist.
        Index("idx_satellites_user_slug", "user_id", "slug", unique=True),
        Index("idx_satellites_user_base_url", "user_id", "base_url", unique=True),
    )

    def __repr__(self) -> str:
        """String representation of Satellite."""
        return (
            f"<Satellite(id={self.id}, kind='{self.kind}', "
            f"slug='{self.slug}', user={self.user_id})>"
        )
