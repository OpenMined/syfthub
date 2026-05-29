"""Admin user-overview statistics service.

Computes the aggregated metrics for the admin dashboard. All time bucketing is
done in Python (NOT SQL ``date_trunc``) so the same logic works identically on
the SQLite test database and the Postgres production database. The only SQL
aggregates used are ``COUNT`` and ``GROUP BY``, which behave identically on
both backends.
"""

from __future__ import annotations

import csv
import io
import math
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from syfthub.repositories.user import UserRepository
from syfthub.schemas.admin import (
    AdminUserPage,
    AdminUserRow,
    AuthProviderCount,
    HeadlineCounts,
    LastLoginBucket,
    LastLoginStats,
    RoleCount,
    SignupBucket,
    SignupTrend,
    UserOverviewStats,
)
from syfthub.schemas.auth import AuthProvider, UserRole
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _normalize(value: Optional[datetime | str]) -> Optional[datetime]:
    """Coerce a stored timestamp to a timezone-aware UTC ``datetime``.

    SQLite may return ISO strings; naive datetimes are assumed UTC.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AdminStatsService(BaseService):
    """Service that computes admin dashboard statistics."""

    def __init__(self, session: Session):
        """Initialize with a database session."""
        super().__init__(session)
        self.user_repository = UserRepository(session)

    def get_overview(self, trend_days: int) -> UserOverviewStats:
        """Compute the full overview payload (everything except the table)."""
        repo = self.user_repository

        counts = repo.count_overview()
        headline = HeadlineCounts(
            total_users=counts["total"],
            active_users=counts["active"],
            inactive_users=counts["inactive"],
            email_verified=counts["verified"],
            email_unverified=counts["unverified"],
            admins=counts["admins"],
        )

        role_counts = repo.count_by_field_grouped("role")
        by_role = [
            RoleCount(role=r, count=int(role_counts.get(r.value, 0))) for r in UserRole
        ]

        provider_counts = repo.count_by_field_grouped("auth_provider")
        by_auth_provider = [
            AuthProviderCount(provider=p, count=int(provider_counts.get(p.value, 0)))
            for p in AuthProvider
        ]

        # Bound the signup scan to the requested window so it stays proportional
        # to trend_days rather than scanning every user's created_at.
        signup_since = datetime.now(timezone.utc) - timedelta(days=trend_days)
        signup_trend = self._build_signup_trend(
            repo.get_signup_dates(since=signup_since), trend_days
        )
        last_login = self._build_last_login_stats(repo.get_last_login_dates())

        return UserOverviewStats(
            headline=headline,
            by_role=by_role,
            by_auth_provider=by_auth_provider,
            signup_trend=signup_trend,
            last_login=last_login,
        )

    @staticmethod
    def _build_signup_trend(raw_dates: list[datetime], trend_days: int) -> SignupTrend:
        """Bucket signups into the last ``trend_days`` daily buckets (UTC).

        Ascending, gap-filled with zeros, always exactly ``trend_days`` entries.
        """
        today = datetime.now(timezone.utc).date()
        # Pre-seed ordered buckets oldest -> newest.
        buckets: OrderedDict[date, int] = OrderedDict()
        for offset in range(trend_days - 1, -1, -1):
            buckets[today - timedelta(days=offset)] = 0

        oldest = today - timedelta(days=trend_days - 1)
        for raw in raw_dates:
            dt = _normalize(raw)
            if dt is None:
                continue
            d = dt.date()
            if oldest <= d <= today:
                buckets[d] += 1

        return SignupTrend(
            days=trend_days,
            buckets=[SignupBucket(date=d, signups=c) for d, c in buckets.items()],
        )

    @staticmethod
    def _build_last_login_stats(
        raw_logins: list[Optional[datetime]],
    ) -> LastLoginStats:
        """Bucket users into mutually-exclusive last-login recency buckets."""
        now = datetime.now(timezone.utc)
        t24h = now - timedelta(hours=24)
        t7d = now - timedelta(days=7)
        t30d = now - timedelta(days=30)
        t90d = now - timedelta(days=90)

        counts = {"24h": 0, "7d": 0, "30d": 0, "90d": 0, "never": 0}
        dormant_30d = 0

        for raw in raw_logins:
            dt = _normalize(raw)
            if dt is None or dt < t90d:
                counts["never"] += 1
                dormant_30d += 1
                continue
            # Consistent half-open buckets: each lower bound is inclusive (>=),
            # so a timestamp lands in the newest bucket whose start it reaches.
            if dt >= t24h:
                counts["24h"] += 1
            elif dt >= t7d:
                counts["7d"] += 1
            elif dt >= t30d:
                counts["30d"] += 1
            else:  # t90d <= dt < t30d (dt < t90d already routed to "never")
                counts["90d"] += 1
            if dt < t30d:
                dormant_30d += 1

        labels = {
            "24h": "Last 24 hours",
            "7d": "Last 7 days",
            "30d": "Last 30 days",
            "90d": "Last 90 days",
            "never": "Never / 90d+",
        }
        buckets = [
            LastLoginBucket(bucket=key, label=labels[key], count=counts[key])
            for key in ("24h", "7d", "30d", "90d", "never")
        ]
        return LastLoginStats(
            buckets=buckets,
            active_24h=counts["24h"],
            dormant_30d=dormant_30d,
        )

    def list_users(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str,
        sort_dir: str,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
    ) -> AdminUserPage:
        """Return a paginated page of users for the admin table."""
        rows, total = self.user_repository.list_users_admin(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
            role=role,
            is_active=is_active,
            is_email_verified=is_email_verified,
        )
        total_pages = math.ceil(total / page_size) if page_size > 0 else 0
        return AdminUserPage(
            items=[AdminUserRow.model_validate(u) for u in rows],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        )

    # CSV columns for the user-base export, in order.
    _EXPORT_COLUMNS = (
        "id",
        "username",
        "email",
        "full_name",
        "role",
        "is_active",
        "is_email_verified",
        "auth_provider",
        "created_at",
        "last_login_at",
    )

    def export_users_csv(
        self,
        *,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
    ) -> str:
        """Render all users matching the filters as a CSV document.

        Same filter/sort semantics as the admin table but without pagination.
        Only account-overview fields are included — never password hashes,
        wallet keys, or tokens. Timestamps are emitted as UTC ISO-8601.
        """
        rows = self.user_repository.list_users_for_export(
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
            role=role,
            is_active=is_active,
            is_email_verified=is_email_verified,
        )

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self._EXPORT_COLUMNS)
        for u in rows:
            created = _normalize(u.created_at)
            last_login = _normalize(u.last_login_at)
            writer.writerow(
                [
                    u.id,
                    u.username,
                    u.email,
                    u.full_name,
                    getattr(u.role, "value", u.role),
                    u.is_active,
                    u.is_email_verified,
                    getattr(u.auth_provider, "value", u.auth_provider),
                    created.isoformat() if created else "",
                    last_login.isoformat() if last_login else "",
                ]
            )
        return buffer.getvalue()
