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

    base_url: Mapped[str] = mapped_column(String(MAX_BASE_URL_LENGTH), nullable=False)

    # Last heartbeat. Distinct from endpoint health: a satellite can be
    # reachable while an endpoint it serves is not.
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="satellites")
    # Deleting a satellite deletes what it served. passive_deletes defers the
    # work to the FK's ON DELETE CASCADE rather than loading every child to
    # null its space_id, which is the SQLAlchemy default and would fight the
    # constraint.
    endpoints: Mapped[List["EndpointModel"]] = relationship(
        "EndpointModel",
        back_populates="space",
        cascade="all, delete",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_satellites_public_id", "public_id", unique=True),
        Index("idx_satellites_user_id", "user_id"),
        # One origin per account. A satellite has no name: public_id identifies
        # it, and this is what makes one host exactly one satellite — and an
        # origin usable as a resolution key.
        Index("idx_satellites_user_base_url", "user_id", "base_url", unique=True),
    )

    def __repr__(self) -> str:
        """String representation of Satellite."""
        return (
            f"<Satellite(id={self.public_id}, kind='{self.kind}', "
            f"base_url='{self.base_url}', user={self.user_id})>"
        )
