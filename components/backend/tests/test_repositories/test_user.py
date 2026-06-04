"""Tests for UserRepository admin-dashboard methods."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from syfthub.models.user import UserModel
from syfthub.repositories.user import UserRepository


def _make_user(username: str, **overrides) -> UserModel:
    """Build a UserModel with sensible defaults."""
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


class TestUpdateLastLogin:
    """Tests for update_last_login."""

    def test_sets_timestamp_and_returns_true(self, test_session: Session) -> None:
        repo = UserRepository(test_session)
        user = _make_user("loginuser")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        assert user.last_login_at is None
        assert repo.update_last_login(user.id) is True

        test_session.refresh(user)
        assert user.last_login_at is not None

    def test_missing_user_returns_false(self, test_session: Session) -> None:
        repo = UserRepository(test_session)
        assert repo.update_last_login(999999) is False


class TestListUsersAdmin:
    """Tests for list_users_admin filtering/sorting/pagination."""

    @pytest.fixture
    def seeded(self, test_session: Session) -> None:
        test_session.add_all(
            [
                _make_user("alice", role="admin"),
                _make_user("bob", is_active=False),
                _make_user("carol", is_email_verified=False),
                _make_user("dave"),
            ]
        )
        test_session.commit()

    def test_total_and_pagination(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(page=1, page_size=2)
        assert total == 4
        assert len(rows) == 2

    def test_search_username(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(search="ALICE")
        assert total == 1
        assert rows[0].username == "alice"

    def test_search_email(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(search="bob@example")
        assert total == 1
        assert rows[0].username == "bob"

    def test_role_filter(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(role="admin")
        assert total == 1
        assert rows[0].username == "alice"

    def test_is_active_filter(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(is_active=False)
        assert total == 1
        assert rows[0].username == "bob"

    def test_is_email_verified_filter(
        self, test_session: Session, seeded: None
    ) -> None:
        repo = UserRepository(test_session)
        rows, total = repo.list_users_admin(is_email_verified=False)
        assert total == 1
        assert rows[0].username == "carol"

    def test_sort_username_asc_desc(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        asc, _ = repo.list_users_admin(sort_by="username", sort_dir="asc")
        names = [u.username for u in asc]
        assert names == sorted(names)

        desc, _ = repo.list_users_admin(sort_by="username", sort_dir="desc")
        names = [u.username for u in desc]
        assert names == sorted(names, reverse=True)


class TestAggregateHelpers:
    """Tests for the grouped/filtered count helpers."""

    @pytest.fixture
    def seeded(self, test_session: Session) -> None:
        test_session.add_all(
            [
                _make_user("admin1", role="admin"),
                _make_user("user1", role="user"),
                _make_user("user2", role="user", auth_provider="google"),
            ]
        )
        test_session.commit()

    def test_count_by_field_grouped_role(
        self, test_session: Session, seeded: None
    ) -> None:
        repo = UserRepository(test_session)
        counts = repo.count_by_field_grouped("role")
        assert counts.get("admin") == 1
        assert counts.get("user") == 2

    def test_count_by_field_grouped_provider(
        self, test_session: Session, seeded: None
    ) -> None:
        repo = UserRepository(test_session)
        counts = repo.count_by_field_grouped("auth_provider")
        assert counts.get("local") == 2
        assert counts.get("google") == 1

    def test_count_with_filters(self, test_session: Session, seeded: None) -> None:
        repo = UserRepository(test_session)
        assert repo.count_with_filters() == 3
        assert repo.count_with_filters(role="admin") == 1
        assert repo.count_with_filters(is_active=True) == 3

    def test_get_last_login_dates_includes_none(self, test_session: Session) -> None:
        repo = UserRepository(test_session)
        u1 = _make_user("never")
        u2 = _make_user("recent", last_login_at=datetime.now(timezone.utc))
        test_session.add_all([u1, u2])
        test_session.commit()

        dates = repo.get_last_login_dates()
        assert None in dates
        assert any(d is not None for d in dates)

    def test_get_signup_dates(self, test_session: Session) -> None:
        repo = UserRepository(test_session)
        test_session.add(_make_user("sign1"))
        test_session.commit()
        dates = repo.get_signup_dates()
        assert len(dates) == 1
        # Within the last minute.
        normalized = dates[0]
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=timezone.utc)
        assert datetime.now(timezone.utc) - normalized < timedelta(minutes=5)
