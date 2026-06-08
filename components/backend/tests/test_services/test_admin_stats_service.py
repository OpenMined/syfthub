"""Unit tests for AdminStatsService aggregation logic."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from syfthub.models.user import UserModel
from syfthub.services.admin_stats_service import AdminStatsService


def _make_user(username: str, **overrides) -> UserModel:
    data = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": f"{username.title()} User",
        "role": "user",
        "is_active": True,
        "is_email_verified": True,
        "auth_provider": "local",
        "password_hash": "x",
    }
    data.update(overrides)
    return UserModel(**data)


class TestEmptyDatabase:
    """Empty-DB returns zero-filled buckets, never empty arrays."""

    def test_empty_overview(self, test_session: Session) -> None:
        service = AdminStatsService(test_session)
        overview = service.get_overview(trend_days=30)

        assert overview.headline.total_users == 0
        assert overview.headline.active_users == 0
        assert overview.headline.admins == 0

        # Every role/provider present, all zero.
        assert {r.role.value for r in overview.by_role} == {"admin", "user", "guest"}
        assert all(r.count == 0 for r in overview.by_role)
        assert {p.provider.value for p in overview.by_auth_provider} == {
            "local",
            "google",
            "email_otp",
        }

        # Signup trend zero-filled to exactly trend_days.
        assert overview.signup_trend.days == 30
        assert len(overview.signup_trend.buckets) == 30
        assert all(b.signups == 0 for b in overview.signup_trend.buckets)

        # Five last-login buckets, all zero.
        assert len(overview.last_login.buckets) == 5
        assert all(b.count == 0 for b in overview.last_login.buckets)
        assert overview.last_login.active_24h == 0
        assert overview.last_login.dormant_30d == 0


class TestAggregationCorrectness:
    """Seeded aggregation correctness."""

    @pytest.fixture
    def seeded(self, test_session: Session) -> None:
        now = datetime.now(timezone.utc)
        test_session.add_all(
            [
                # admin, active, verified, local, logged in 1h ago
                _make_user(
                    "admin1", role="admin", last_login_at=now - timedelta(hours=1)
                ),
                # user, active, verified, google, logged in 3 days ago
                _make_user(
                    "user1",
                    auth_provider="google",
                    last_login_at=now - timedelta(days=3),
                ),
                # user, inactive, unverified, local, logged in 45 days ago
                _make_user(
                    "user2",
                    is_active=False,
                    is_email_verified=False,
                    last_login_at=now - timedelta(days=45),
                ),
                # guest, active, verified, local, never logged in
                _make_user("guest1", role="guest", last_login_at=None),
            ]
        )
        test_session.commit()

    def test_headline_counts(self, test_session: Session, seeded: None) -> None:
        service = AdminStatsService(test_session)
        h = service.get_overview(trend_days=30).headline
        assert h.total_users == 4
        assert h.active_users == 3
        assert h.inactive_users == 1
        assert h.email_verified == 3
        assert h.email_unverified == 1
        assert h.admins == 1

    def test_by_role_and_provider(self, test_session: Session, seeded: None) -> None:
        service = AdminStatsService(test_session)
        overview = service.get_overview(trend_days=30)
        role_map = {r.role.value: r.count for r in overview.by_role}
        assert role_map == {"admin": 1, "user": 2, "guest": 1}
        provider_map = {p.provider.value: p.count for p in overview.by_auth_provider}
        assert provider_map == {"local": 3, "google": 1, "email_otp": 0}

    def test_last_login_buckets_sum_to_total(
        self, test_session: Session, seeded: None
    ) -> None:
        service = AdminStatsService(test_session)
        ll = service.get_overview(trend_days=30).last_login
        assert sum(b.count for b in ll.buckets) == 4

        counts = {b.bucket: b.count for b in ll.buckets}
        # admin1 -> 24h; user1 -> 7d; user2 (45d) -> 90d; guest1 (null) -> never
        assert counts["24h"] == 1
        assert counts["7d"] == 1
        assert counts["90d"] == 1
        assert counts["never"] == 1
        assert counts["30d"] == 0

    def test_active_24h_and_dormant_30d(
        self, test_session: Session, seeded: None
    ) -> None:
        service = AdminStatsService(test_session)
        ll = service.get_overview(trend_days=30).last_login
        assert ll.active_24h == 1
        # dormant = null (guest1) + 45-days-ago (user2) = 2
        assert ll.dormant_30d == 2


class TestSignupTrend:
    """Signup-trend gap-filling and ordering."""

    def test_gap_fill_and_ordering(self, test_session: Session) -> None:
        # One user created today (created_at defaults to now via TimestampMixin).
        test_session.add(_make_user("today1"))
        test_session.commit()

        service = AdminStatsService(test_session)
        trend = service.get_overview(trend_days=7).signup_trend
        assert trend.days == 7
        assert len(trend.buckets) == 7

        # Ascending date order.
        dates = [b.date for b in trend.buckets]
        assert dates == sorted(dates)

        # Today's bucket has the signup; days with no signups are 0.
        assert trend.buckets[-1].signups == 1
        assert sum(b.signups for b in trend.buckets) == 1


class TestListUsers:
    """list_users pagination wrapper."""

    def test_total_pages(self, test_session: Session) -> None:
        for i in range(5):
            test_session.add(_make_user(f"user{i}"))
        test_session.commit()

        service = AdminStatsService(test_session)
        page = service.list_users(
            page=1, page_size=2, sort_by="created_at", sort_dir="desc"
        )
        assert page.total == 5
        assert page.total_pages == 3
        assert page.page == 1
        assert page.page_size == 2
        assert len(page.items) == 2
