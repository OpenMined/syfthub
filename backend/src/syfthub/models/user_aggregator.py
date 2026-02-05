"""User aggregator database model."""

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from syfthub.models.base import BaseModel, TimestampMixin

if TYPE_CHECKING:
    from syfthub.models.user import UserModel


class UserAggregatorModel(BaseModel, TimestampMixin):
    """User aggregator configuration model.

    Stores multiple aggregator URLs for each user, allowing them to
    switch between different RAG orchestration services.
    """

    __tablename__ = "user_aggregators"

    # Foreign key to user
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Aggregator configuration
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="aggregators")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_user_aggregators_user_id", "user_id"),
        Index("idx_user_aggregators_is_default", "is_default"),
        # Ensure only one default per user
        UniqueConstraint(
            "user_id",
            "is_default",
            name="uq_user_default_aggregator",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    def __repr__(self) -> str:
        """String representation of UserAggregator."""
        return f"<UserAggregator(id={self.id}, user_id={self.user_id}, name='{self.name}', is_default={self.is_default})>"
