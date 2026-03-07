"""Tests for email OTP authentication endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client with clean database."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()

    client = TestClient(app)
    yield client

    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Reset authentication data before each test."""
    token_blacklist.clear()


def _register_user(client: TestClient, **overrides) -> dict:
    """Helper to register a user and return the response JSON."""
    data = {
        "username": "otpuser",
        "email": "otp@example.com",
        "full_name": "OTP User",
        "password": "testpass123",
        **overrides,
    }
    response = client.post("/api/v1/auth/register", json=data)
    assert response.status_code == 201
    return response.json()


# =============================================================================
# GET /auth/config
# =============================================================================
def test_auth_config_defaults(client: TestClient) -> None:
    """Config returns defaults when email is not configured."""
    response = client.get("/api/v1/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert data["require_email_verification"] is False
    assert data["smtp_configured"] is False
    assert data["password_reset_enabled"] is False


def test_auth_config_email_enabled(client: TestClient, monkeypatch) -> None:
    """Config reflects Resend + verification settings."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    response = client.get("/api/v1/auth/config")
    data = response.json()
    assert data["require_email_verification"] is True
    assert data["smtp_configured"] is True
    assert data["password_reset_enabled"] is True


# =============================================================================
# Registration with email verification
# =============================================================================
def test_register_without_verification(client: TestClient) -> None:
    """Registration returns tokens when verification is disabled (default)."""
    result = _register_user(client)
    assert result["access_token"] is not None
    assert result["refresh_token"] is not None
    assert result["requires_email_verification"] is False


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_register_with_verification(mock_send, client: TestClient, monkeypatch) -> None:
    """Registration withholds tokens when verification is enabled."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    result = _register_user(client)
    assert result["access_token"] is None
    assert result["refresh_token"] is None
    assert result["requires_email_verification"] is True
    assert result["user"]["email"] == "otp@example.com"


# =============================================================================
# POST /register/verify-otp
# =============================================================================
@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_verify_otp_success(mock_send, client: TestClient, monkeypatch) -> None:
    """Verifying valid OTP returns tokens and marks email verified."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    # Register (tokens withheld)
    _register_user(client)

    # Extract OTP from the generate_otp call by patching at service level
    with patch("syfthub.services.otp_service.OTPService.verify_otp", return_value=True):
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "otp@example.com", "code": "123456"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is not None
    assert data["refresh_token"] is not None
    assert data["user"]["email"] == "otp@example.com"


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_verify_otp_invalid_code(mock_send, client: TestClient, monkeypatch) -> None:
    """Invalid OTP code returns 400."""
    from syfthub.domain.exceptions import InvalidOTPError

    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    _register_user(client)

    with patch(
        "syfthub.services.otp_service.OTPService.verify_otp",
        side_effect=InvalidOTPError("Invalid verification code"),
    ):
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "otp@example.com", "code": "000000"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_OTP"


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_verify_otp_max_attempts(mock_send, client: TestClient, monkeypatch) -> None:
    """Exceeding max attempts returns 429."""
    from syfthub.domain.exceptions import OTPMaxAttemptsError

    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    _register_user(client)

    with patch(
        "syfthub.services.otp_service.OTPService.verify_otp",
        side_effect=OTPMaxAttemptsError(),
    ):
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "otp@example.com", "code": "999999"},
        )

    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "OTP_MAX_ATTEMPTS"


def test_verify_otp_user_not_found(client: TestClient) -> None:
    """Verify OTP for non-existent user returns 400 (no active OTP)."""
    response = client.post(
        "/api/v1/auth/register/verify-otp",
        json={"email": "nobody@example.com", "code": "123456"},
    )
    # OTP verification runs before user lookup to avoid leaking user existence
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_OTP"


def test_verify_otp_already_verified(client: TestClient) -> None:
    """Verify OTP for already-verified user returns tokens (idempotent)."""
    # Register without verification (user is auto-verified)
    _register_user(client)

    # Patch OTP verification to succeed — the test focuses on the endpoint's
    # handling of already-verified users, not on OTP mechanics.
    with patch("syfthub.services.otp_service.OTPService.verify_otp", return_value=True):
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "otp@example.com", "code": "123456"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] is not None


# =============================================================================
# POST /register/resend-otp
# =============================================================================
@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_resend_otp_success(mock_send, client: TestClient, monkeypatch) -> None:
    """Resend OTP returns 200 for unverified user."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    _register_user(client)

    response = client.post(
        "/api/v1/auth/register/resend-otp",
        json={"email": "otp@example.com"},
    )
    assert response.status_code == 200


def test_resend_otp_nonexistent_email(client: TestClient) -> None:
    """Resend OTP for unknown email still returns 200 (no enumeration)."""
    response = client.post(
        "/api/v1/auth/register/resend-otp",
        json={"email": "nobody@example.com"},
    )
    assert response.status_code == 200


# =============================================================================
# POST /login with email verification
# =============================================================================
@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_login_blocked_unverified(mock_send, client: TestClient, monkeypatch) -> None:
    """Login with unverified email returns 403."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    _register_user(client)

    response = client.post(
        "/api/v1/auth/login",
        data={"username": "otpuser", "password": "testpass123"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"


# =============================================================================
# Password reset endpoints
# =============================================================================
def test_password_reset_request_no_email(client: TestClient) -> None:
    """Password reset request returns 200 even without email configured."""
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "otp@example.com"},
    )
    assert response.status_code == 200


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_password_reset_request_with_email(
    mock_send, client: TestClient, monkeypatch
) -> None:
    """Password reset request sends OTP when email is configured."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")

    _register_user(client)

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "otp@example.com"},
    )
    assert response.status_code == 200


def test_password_reset_request_nonexistent_email(
    client: TestClient, monkeypatch
) -> None:
    """Password reset for unknown email returns 200 (no enumeration)."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert response.status_code == 200


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_password_reset_confirm_success(
    mock_send, client: TestClient, monkeypatch
) -> None:
    """Password reset confirm with valid OTP succeeds."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")

    _register_user(client)

    with patch("syfthub.services.otp_service.OTPService.verify_otp", return_value=True):
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "email": "otp@example.com",
                "code": "123456",
                "new_password": "newpass456",
            },
        )

    assert response.status_code == 200

    # Verify new password works
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "otpuser", "password": "newpass456"},
    )
    assert response.status_code == 200


def test_password_reset_confirm_invalid_code(client: TestClient) -> None:
    """Password reset confirm with invalid OTP returns 400."""
    from syfthub.domain.exceptions import InvalidOTPError

    _register_user(client)

    with patch(
        "syfthub.services.otp_service.OTPService.verify_otp",
        side_effect=InvalidOTPError("Invalid verification code"),
    ):
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "email": "otp@example.com",
                "code": "000000",
                "new_password": "newpass456",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_OTP"


# =============================================================================
# IP rate limiting
# =============================================================================
@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_register_ip_rate_limit(mock_send, client: TestClient, monkeypatch) -> None:
    """Registration is blocked when per-IP OTP rate limit is exceeded."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")

    monkeypatch.setattr(
        "syfthub.core.config.settings.otp_ip_rate_limit_max_requests", 2
    )

    # First two registrations should succeed
    _register_user(client, username="user1", email="u1@example.com")
    _register_user(client, username="user2", email="u2@example.com")

    # Third should hit IP rate limit (TestClient always uses same IP)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "user3",
            "email": "u3@example.com",
            "full_name": "User Three",
            "password": "testpass123",
        },
    )
    # OTPRateLimitedError propagates from register_user → 429
    assert response.status_code == 429


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_resend_otp_ip_rate_limit_swallowed(
    mock_send, client: TestClient, monkeypatch
) -> None:
    """Resend-otp swallows IP rate limit error to prevent enumeration."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")

    monkeypatch.setattr(
        "syfthub.core.config.settings.otp_ip_rate_limit_max_requests", 1
    )

    _register_user(client)

    # Second resend should hit IP rate limit, but endpoint swallows it
    response = client.post(
        "/api/v1/auth/register/resend-otp",
        json={"email": "otp@example.com"},
    )
    assert response.status_code == 200


# =============================================================================
# Email retry
# =============================================================================
@pytest.mark.asyncio
async def test_send_otp_email_sends_via_resend(monkeypatch) -> None:
    """send_otp_email sends via Resend API."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    monkeypatch.setattr("syfthub.core.config.settings.otp_email_max_retries", 1)
    monkeypatch.setattr(
        "syfthub.core.config.settings.otp_email_retry_delay_seconds", 0.01
    )

    with patch(
        "syfthub.services.email_service.resend.Emails.send",
        return_value={"id": "email-123"},
    ) as mock_resend:
        from syfthub.services.email_service import send_otp_email

        await send_otp_email("test@example.com", "123456", "registration")

    mock_resend.assert_called_once()
    call_args = mock_resend.call_args[0][0]
    assert call_args["to"] == ["test@example.com"]
    assert "123456" in call_args["html"]


@pytest.mark.asyncio
async def test_send_otp_email_resend_retries_on_failure(monkeypatch) -> None:
    """send_otp_email retries Resend API calls on transient failure."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")
    monkeypatch.setattr("syfthub.core.config.settings.otp_email_max_retries", 3)
    monkeypatch.setattr(
        "syfthub.core.config.settings.otp_email_retry_delay_seconds", 0.01
    )

    call_count = 0

    def mock_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Resend API unreachable")
        return {"id": "email-123"}

    with patch(
        "syfthub.services.email_service.resend.Emails.send", side_effect=mock_send
    ):
        from syfthub.services.email_service import send_otp_email

        await send_otp_email("test@example.com", "123456", "registration")

    assert call_count == 3


# =============================================================================
# OTP cleanup
# =============================================================================
def test_otp_cleanup_deletes_stale_records(client: TestClient, monkeypatch) -> None:
    """delete_expired_used removes old expired/used records but keeps active ones."""
    from datetime import datetime, timedelta, timezone

    from syfthub.database.connection import db_manager
    from syfthub.repositories.otp import OTPRepository

    session = db_manager.get_session()
    try:
        repo = OTPRepository(session)
        now = datetime.now(timezone.utc)

        # Create an old used record (should be deleted)
        repo.create_otp(
            email="old@example.com",
            code_hash="a" * 64,
            purpose="registration",
            expires_at=now - timedelta(hours=48),
        )
        repo.invalidate_existing("old@example.com", "registration")

        # Create a recent active record (should be kept)
        repo.create_otp(
            email="new@example.com",
            code_hash="b" * 64,
            purpose="registration",
            expires_at=now + timedelta(minutes=10),
        )

        deleted = repo.delete_expired_used(retention_hours=24)
        assert deleted >= 1

        # Active record should still exist
        active = repo.get_active_otp("new@example.com", "registration")
        assert active is not None
    finally:
        session.close()


def test_create_otp_stores_requester_ip(client: TestClient) -> None:
    """create_otp stores the requester_ip when provided."""
    from datetime import datetime, timedelta, timezone

    from syfthub.database.connection import db_manager
    from syfthub.repositories.otp import OTPRepository

    session = db_manager.get_session()
    try:
        repo = OTPRepository(session)
        now = datetime.now(timezone.utc)

        otp = repo.create_otp(
            email="ip@example.com",
            code_hash="c" * 64,
            purpose="registration",
            expires_at=now + timedelta(minutes=10),
            requester_ip="192.168.1.1",
        )
        assert otp is not None
        assert otp.requester_ip == "192.168.1.1"

        # count_recent_by_ip should find it
        count = repo.count_recent_by_ip("192.168.1.1", window_minutes=10)
        assert count == 1

        # Different IP should not find it
        count = repo.count_recent_by_ip("10.0.0.1", window_minutes=10)
        assert count == 0
    finally:
        session.close()
