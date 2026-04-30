"""Repository for user Xendit subscriptions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.xendit_subscription import UserXenditSubscriptionModel
from syfthub.repositories.base import BaseRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserXenditSubscriptionRepository(BaseRepository[UserXenditSubscriptionModel]):
    """Repository for user_xendit_subscriptions CRUD."""

    def __init__(self, session: Session):
        super().__init__(session, UserXenditSubscriptionModel)

    def list_for_user(self, user_id: int) -> List[UserXenditSubscriptionModel]:
        """Return all subscriptions for a user, newest first."""
        try:
            stmt = (
                select(self.model)
                .where(self.model.user_id == user_id)
                .order_by(self.model.created_at.desc())
            )
            return list(self.session.execute(stmt).scalars().all())
        except SQLAlchemyError:
            return []

    def get_for_user(
        self, user_id: int, subscription_id: int
    ) -> Optional[UserXenditSubscriptionModel]:
        """Get a single subscription, scoped to the owning user."""
        try:
            stmt = select(self.model).where(
                and_(self.model.id == subscription_id, self.model.user_id == user_id)
            )
            return self.session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError:
            return None

    def get_by_credits_url(
        self, user_id: int, credits_url: str
    ) -> Optional[UserXenditSubscriptionModel]:
        """Lookup by the (user_id, credits_url) natural key."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.user_id == user_id,
                    self.model.credits_url == credits_url,
                )
            )
            return self.session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError:
            return None

    def upsert(
        self,
        *,
        user_id: int,
        credits_url: str,
        payment_url: str,
        endpoint_owner: str,
        endpoint_slug: Optional[str],
        currency: str,
        last_known_balance: Optional[float],
    ) -> Optional[UserXenditSubscriptionModel]:
        """Create or refresh a subscription row.

        Existing rows have their balance, mutable metadata, and freshness
        fields refreshed; ``first_funded_at`` is preserved on first non-zero
        balance and never overwritten thereafter.
        """
        try:
            now = datetime.now(timezone.utc)
            existing = self.get_by_credits_url(user_id, credits_url)

            if existing is None:
                row = UserXenditSubscriptionModel(
                    user_id=user_id,
                    credits_url=credits_url,
                    payment_url=payment_url,
                    endpoint_owner=endpoint_owner,
                    endpoint_slug=endpoint_slug,
                    currency=currency,
                    last_known_balance=last_known_balance,
                    last_checked_at=now,
                    first_funded_at=now if (last_known_balance or 0) > 0 else None,
                )
                self.session.add(row)
            else:
                existing.payment_url = payment_url
                existing.endpoint_owner = endpoint_owner
                # Only adopt a more-specific slug; don't blank one out.
                if endpoint_slug:
                    existing.endpoint_slug = endpoint_slug
                existing.currency = currency
                if last_known_balance is not None:
                    existing.last_known_balance = last_known_balance
                existing.last_checked_at = now
                if existing.first_funded_at is None and (last_known_balance or 0) > 0:
                    existing.first_funded_at = now
                row = existing

            self.session.commit()
            self.session.refresh(row)
            return row
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def delete_for_user(self, user_id: int, subscription_id: int) -> bool:
        """Hard-delete a subscription, scoped to the owning user."""
        try:
            row = self.get_for_user(user_id, subscription_id)
            if row is None:
                return False
            self.session.delete(row)
            self.session.commit()
            return True
        except SQLAlchemyError:
            self.session.rollback()
            return False
