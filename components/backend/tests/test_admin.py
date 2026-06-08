"""Tests for the admin user-overview dashboard endpoints."""

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app

API = "/api/v1"


@pytest.fixture
def client() -> TestClient:
    """Create a test client with a clean database."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    yield TestClient(app)
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication state before each test."""
    token_blacklist.clear()
    yield


def _register(client: TestClient, username: str) -> int:
    """Register a user and return their id."""
    resp = client.post(
        f"{API}/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": f"{username.title()} User",
            "password": "testpassword123",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["user"]["id"]


def _login_headers(client: TestClient, username: str) -> dict:
    """Log in and return Authorization headers."""
    resp = client.post(
        f"{API}/auth/login",
        data={"username": username, "password": "testpassword123"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _promote_to_admin(user_id: int) -> None:
    """Promote a user to admin via the repository."""
    from syfthub.database.connection import get_db_session
    from syfthub.repositories.user import UserRepository
    from syfthub.schemas.auth import UserRole

    session = next(get_db_session())
    try:
        UserRepository(session).update_user_role(user_id, UserRole.ADMIN.value)
    finally:
        session.close()


@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    """Register, promote, and log in an admin user."""
    user_id = _register(client, "adminuser")
    _promote_to_admin(user_id)
    return _login_headers(client, "adminuser")


@pytest.fixture
def user_headers(client: TestClient) -> dict:
    """Register and log in a regular (non-admin) user."""
    _register(client, "regularuser")
    return _login_headers(client, "regularuser")


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def test_overview_requires_auth(client: TestClient) -> None:
    """Unauthenticated requests are rejected with 401/403."""
    resp = client.get(f"{API}/admin/overview")
    assert resp.status_code in (401, 403)


def test_users_requires_auth(client: TestClient) -> None:
    """Unauthenticated requests are rejected with 401/403."""
    resp = client.get(f"{API}/admin/users")
    assert resp.status_code in (401, 403)


def test_overview_forbidden_for_non_admin(
    client: TestClient, user_headers: dict
) -> None:
    """A non-admin authenticated user gets 403 on overview."""
    resp = client.get(f"{API}/admin/overview", headers=user_headers)
    assert resp.status_code == 403


def test_users_forbidden_for_non_admin(client: TestClient, user_headers: dict) -> None:
    """A non-admin authenticated user gets 403 on users."""
    resp = client.get(f"{API}/admin/users", headers=user_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Overview shape + correctness
# ---------------------------------------------------------------------------


def test_overview_shape(client: TestClient, admin_headers: dict) -> None:
    """Overview returns the full contract shape."""
    resp = client.get(f"{API}/admin/overview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body.keys()) == {
        "headline",
        "by_role",
        "by_auth_provider",
        "signup_trend",
        "last_login",
    }
    headline = body["headline"]
    assert set(headline.keys()) == {
        "total_users",
        "active_users",
        "inactive_users",
        "email_verified",
        "email_unverified",
        "admins",
    }
    # One admin user exists.
    assert headline["total_users"] == 1
    assert headline["admins"] == 1
    assert headline["active_users"] == 1

    # by_role lists every role, by_auth_provider every provider.
    roles = {r["role"] for r in body["by_role"]}
    assert roles == {"admin", "user", "guest"}
    providers = {p["provider"] for p in body["by_auth_provider"]}
    assert providers == {"local", "google", "email_otp"}

    # Last-login buckets: all five present, mutually exclusive sum == total.
    buckets = body["last_login"]["buckets"]
    bucket_keys = [b["bucket"] for b in buckets]
    assert bucket_keys == ["24h", "7d", "30d", "90d", "never"]
    assert sum(b["count"] for b in buckets) == headline["total_users"]
    assert "active_24h" in body["last_login"]
    assert "dormant_30d" in body["last_login"]


@pytest.mark.parametrize("trend_days", [7, 30, 90])
def test_overview_trend_days(
    client: TestClient, admin_headers: dict, trend_days: int
) -> None:
    """trend_days controls the exact number of (gap-filled) buckets."""
    resp = client.get(
        f"{API}/admin/overview",
        params={"trend_days": trend_days},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    trend = resp.json()["signup_trend"]
    assert trend["days"] == trend_days
    assert len(trend["buckets"]) == trend_days
    # Ascending order.
    dates = [b["date"] for b in trend["buckets"]]
    assert dates == sorted(dates)


def test_overview_invalid_trend_days(client: TestClient, admin_headers: dict) -> None:
    """An out-of-allowed-set trend_days yields 422."""
    resp = client.get(
        f"{API}/admin/overview", params={"trend_days": 5}, headers=admin_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Users table: pagination / sort / filter / search
# ---------------------------------------------------------------------------


def test_users_pagination(client: TestClient, admin_headers: dict) -> None:
    """Pagination returns correct page/total/total_pages."""
    # Register additional users (admin already exists -> total 6).
    for i in range(5):
        _register(client, f"bulk{i}")

    resp = client.get(
        f"{API}/admin/users",
        params={"page": 1, "page_size": 2},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 6
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2
    row = body["items"][0]
    assert set(row.keys()) == {
        "id",
        "username",
        "email",
        "full_name",
        "avatar_url",
        "role",
        "is_active",
        "is_email_verified",
        "auth_provider",
        "created_at",
        "last_login_at",
    }


def test_users_search_username_and_email(
    client: TestClient, admin_headers: dict
) -> None:
    """Search matches username OR email, case-insensitively."""
    _register(client, "alice")
    _register(client, "bob")

    resp = client.get(
        f"{API}/admin/users", params={"search": "ALICE"}, headers=admin_headers
    )
    assert resp.status_code == 200
    usernames = {r["username"] for r in resp.json()["items"]}
    assert usernames == {"alice"}

    # Email substring match.
    resp = client.get(
        f"{API}/admin/users", params={"search": "bob@example"}, headers=admin_headers
    )
    assert resp.status_code == 200
    usernames = {r["username"] for r in resp.json()["items"]}
    assert usernames == {"bob"}


def test_users_role_filter(client: TestClient, admin_headers: dict) -> None:
    """Filtering by role returns only matching users."""
    _register(client, "plainuser")

    resp = client.get(
        f"{API}/admin/users", params={"role": "admin"}, headers=admin_headers
    )
    assert resp.status_code == 200
    rows = resp.json()["items"]
    assert all(r["role"] == "admin" for r in rows)
    assert len(rows) == 1


def test_users_sort(client: TestClient, admin_headers: dict) -> None:
    """Sorting by username asc/desc orders rows correctly."""
    _register(client, "zzz")
    _register(client, "aaa")

    resp = client.get(
        f"{API}/admin/users",
        params={"sort_by": "username", "sort_dir": "asc"},
        headers=admin_headers,
    )
    asc = [r["username"] for r in resp.json()["items"]]
    assert asc == sorted(asc)

    resp = client.get(
        f"{API}/admin/users",
        params={"sort_by": "username", "sort_dir": "desc"},
        headers=admin_headers,
    )
    desc = [r["username"] for r in resp.json()["items"]]
    assert desc == sorted(desc, reverse=True)


def test_users_invalid_sort_by(client: TestClient, admin_headers: dict) -> None:
    """An invalid sort_by yields 422."""
    resp = client.get(
        f"{API}/admin/users",
        params={"sort_by": "password_hash"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# last_login_at stamping
# ---------------------------------------------------------------------------


def _get_last_login(user_id: int):
    """Read a user's last_login_at directly from the DB."""
    from syfthub.database.connection import get_db_session
    from syfthub.models.user import UserModel

    session = next(get_db_session())
    try:
        user = session.get(UserModel, user_id)
        assert user is not None
        return user.last_login_at
    finally:
        session.close()


def test_password_login_stamps_last_login(client: TestClient) -> None:
    """A successful password login sets last_login_at (was null after register)."""
    user_id = _register(client, "stampuser")
    assert _get_last_login(user_id) is None

    _login_headers(client, "stampuser")
    first = _get_last_login(user_id)
    assert first is not None


def test_register_does_not_stamp_last_login(client: TestClient) -> None:
    """Registration alone leaves last_login_at null."""
    user_id = _register(client, "regonly")
    assert _get_last_login(user_id) is None


def test_refresh_does_not_stamp_last_login(client: TestClient) -> None:
    """Token refresh does NOT change last_login_at."""
    user_id = _register(client, "refreshuser")
    resp = client.post(
        f"{API}/auth/login",
        data={"username": "refreshuser", "password": "testpassword123"},
    )
    assert resp.status_code == 200
    after_login = _get_last_login(user_id)
    assert after_login is not None

    refresh_token = resp.json()["refresh_token"]
    refresh_resp = client.post(
        f"{API}/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 200, refresh_resp.text
    after_refresh = _get_last_login(user_id)
    assert after_refresh == after_login


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #


def test_export_requires_admin(client: TestClient, user_headers: dict) -> None:
    """Non-admins get 403, unauthenticated callers 401/403."""
    assert (
        client.get(f"{API}/admin/users/export", headers=user_headers).status_code == 403
    )
    assert client.get(f"{API}/admin/users/export").status_code in (401, 403)


def test_export_returns_csv_without_sensitive_fields(
    client: TestClient, admin_headers: dict
) -> None:
    """Export returns a CSV attachment with a header row and no secrets."""
    _register(client, "alice")
    _register(client, "bob")

    resp = client.get(f"{API}/admin/users/export", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert ".csv" in resp.headers["content-disposition"]

    body = resp.text
    lines = [line for line in body.splitlines() if line.strip()]
    header = lines[0]
    assert header.split(",") == [
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
    ]
    # adminuser + alice + bob = 3 data rows
    assert len(lines) == 1 + 3
    assert "alice@example.com" in body
    # Never leak secrets
    for secret in ("password", "password_hash", "wallet_private_key", "token"):
        assert secret not in header


def test_export_honors_role_filter(client: TestClient, admin_headers: dict) -> None:
    """The export applies the same filters as the table."""
    _register(client, "carol")
    resp = client.get(f"{API}/admin/users/export?role=admin", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    lines = [line for line in resp.text.splitlines() if line.strip()]
    # Only the admin user matches role=admin → header + 1 row.
    assert len(lines) == 1 + 1
    assert "adminuser@example.com" in resp.text
    assert "carol@example.com" not in resp.text
