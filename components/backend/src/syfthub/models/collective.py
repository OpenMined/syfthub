"""Collective and CollectiveMember database models.

A Collective is a lightweight, user-owned grouping of endpoints. Unlike an
organization (which groups *users*), a collective groups *endpoints* — its
members are endpoint routes that opted in. Only data-source endpoints
(``data_source`` / ``model_data_source``) are eligible for membership; the
``CollectiveService`` enforces this on both join and invite.

Membership lives in the ``collective_members`` join table. It is an
associative entity, not a plain link row: it carries its own ``status``
workflow so the collective owner can triage join requests (see
``CollectiveModel.auto_approve``) and invite endpoints directly.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin
from syfthub.models.endpoint import JSONType

if TYPE_CHECKING:
    from syfthub.models.endpoint import EndpointModel
    from syfthub.models.user import UserModel


class CollectiveModel(BaseModel, TimestampMixin):
    """Collective database model — a user-owned grouping of endpoints."""

    __tablename__ = "collectives"

    # A collective is always owned by exactly one user.
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # User-controlled fields
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Long-form markdown "about" / README shown on the collective detail page.
    about: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # When True, join requests are accepted immediately; when False the owner
    # must approve each request (see CollectiveMemberModel.status).
    auto_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[List[str]] = mapped_column(
        JSONType, nullable=False, default=lambda: []
    )
    # Toggled out-of-band by ops; not exposed as a user-settable API field.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    owner: Mapped["UserModel"] = relationship("UserModel", back_populates="collectives")
    members: Mapped[List["CollectiveMemberModel"]] = relationship(
        "CollectiveMemberModel",
        back_populates="collective",
        cascade="all, delete-orphan",
    )
    shared_endpoints: Mapped[List["CollectiveSharedEndpointModel"]] = relationship(
        "CollectiveSharedEndpointModel",
        back_populates="collective",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_collectives_owner_id", "owner_id"),
        Index("idx_collectives_slug", "slug"),
    )

    def __repr__(self) -> str:
        """String representation of Collective."""
        return f"<Collective(id={self.id}, slug='{self.slug}', owner={self.owner_id})>"


class CollectiveMemberModel(BaseModel):
    """Membership of an endpoint in a collective.

    Exactly one row per (collective, endpoint) pair — the unique constraint
    means a re-request UPDATEs the existing row rather than inserting a
    duplicate. ``status`` encodes the join/invite workflow:

    - ``pending``  — endpoint owner requested to join; awaiting collective owner
    - ``invited``  — collective owner invited the endpoint; awaiting endpoint owner
    - ``approved`` — active member
    - ``rejected`` — request/invite declined by either side
    """

    __tablename__ = "collective_members"

    collective_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("collectives.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # When the join request / invitation was created (or last re-created).
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # When the membership moved to approved/rejected (NULL while pending/invited).
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # The user who actioned the membership (approver or accepter). NULL when
    # the row was auto-approved or the reviewing user has since been deleted.
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    collective: Mapped["CollectiveModel"] = relationship(
        "CollectiveModel", back_populates="members"
    )
    endpoint: Mapped["EndpointModel"] = relationship(
        "EndpointModel", back_populates="collective_memberships"
    )

    __table_args__ = (
        # One membership row per (collective, endpoint) pair.
        UniqueConstraint(
            "collective_id", "endpoint_id", name="uq_collective_members_pair"
        ),
        Index("idx_collective_members_collective_id", "collective_id"),
        Index("idx_collective_members_endpoint_id", "endpoint_id"),
        # Covers the hot query "approved members of collective C".
        Index(
            "idx_collective_members_collective_status",
            "collective_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        """String representation of CollectiveMember."""
        return (
            f"<CollectiveMember(collective={self.collective_id}, "
            f"endpoint={self.endpoint_id}, status='{self.status}')>"
        )


class CollectiveSharedEndpointModel(BaseModel, TimestampMixin):
    """A named, curated subset of a collective's approved member endpoints.

    Resolves at chat-time as ``collective/<collective_slug>/<slug>`` and fans
    out only to the configured endpoints intersected with the collective's
    *currently* approved members. The implicit ``all`` shared endpoint
    (``collective/<collective_slug>/all``) is never stored — it is hardcoded
    as an alias for "every approved member".
    """

    __tablename__ = "collective_shared_endpoints"

    collective_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("collectives.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Unique per collective (not globally) — see uq_shared_endpoint_collective_slug.
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Relationships
    collective: Mapped["CollectiveModel"] = relationship(
        "CollectiveModel", back_populates="shared_endpoints"
    )
    members: Mapped[List["CollectiveSharedEndpointMemberModel"]] = relationship(
        "CollectiveSharedEndpointMemberModel",
        back_populates="shared_endpoint",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "collective_id", "slug", name="uq_shared_endpoint_collective_slug"
        ),
        Index("idx_shared_endpoint_collective_id", "collective_id"),
    )

    def __repr__(self) -> str:
        """String representation of CollectiveSharedEndpoint."""
        return (
            f"<CollectiveSharedEndpoint(id={self.id}, "
            f"collective={self.collective_id}, slug='{self.slug}')>"
        )


class CollectiveSharedEndpointMemberModel(BaseModel):
    """An endpoint configured into a collective shared-endpoint subset.

    A row here means "the collective owner picked this endpoint as part of the
    subset"; whether the endpoint *currently* participates in chat fan-out
    depends on the intersection with the collective's approved members, which
    is computed at read time.
    """

    __tablename__ = "collective_shared_endpoint_members"

    shared_endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("collective_shared_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationships
    shared_endpoint: Mapped["CollectiveSharedEndpointModel"] = relationship(
        "CollectiveSharedEndpointModel", back_populates="members"
    )
    endpoint: Mapped["EndpointModel"] = relationship(
        "EndpointModel", back_populates="shared_endpoint_memberships"
    )

    __table_args__ = (
        UniqueConstraint(
            "shared_endpoint_id", "endpoint_id", name="uq_shared_endpoint_member_pair"
        ),
        Index("idx_shared_endpoint_member_shared_id", "shared_endpoint_id"),
        Index("idx_shared_endpoint_member_endpoint_id", "endpoint_id"),
    )

    def __repr__(self) -> str:
        """String representation of CollectiveSharedEndpointMember."""
        return (
            f"<CollectiveSharedEndpointMember(shared={self.shared_endpoint_id}, "
            f"endpoint={self.endpoint_id})>"
        )
