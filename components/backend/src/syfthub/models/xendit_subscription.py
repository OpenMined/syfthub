"""User Xendit subscription database model.

Records the publisher-side wallets that a SyftHub user has funded via the
Xendit policy flow. SyftHub does not custody the wallet itself; it stores the
``credits_url`` (which uniquely identifies a wallet on the publisher's
syft_space) plus enough metadata to render the credits panel and re-mint a
satellite token to query the live balance.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.user import UserModel


class UserXenditSubscriptionModel(BaseModel, TimestampMixin):
    """A user's funded Xendit wallet (one per distinct credits_url)."""

    __tablename__ = "user_xendit_subscriptions"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Wallet identity on the publisher syft_space.
    credits_url: Mapped[str] = mapped_column(Text, nullable=False)
    payment_url: Mapped[str] = mapped_column(Text, nullable=False)

    # Display + auth metadata.
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IDR")
    endpoint_owner: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint_slug: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=None
    )

    # Cached balance for fast initial paint (always re-fetched live).
    last_known_balance: Mapped[Optional[float]] = mapped_column(
        Numeric(18, 4), nullable=True, default=None
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # When the first non-zero balance was detected. Lets the UI show
    # "subscribed since …".
    first_funded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    user: Mapped["UserModel"] = relationship("UserModel", lazy="joined")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "credits_url", name="uq_user_xendit_subs_user_credits"
        ),
        Index("idx_user_xendit_subs_user", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserXenditSubscription(id={self.id}, user_id={self.user_id}, "
            f"owner='{self.endpoint_owner}')>"
        )
