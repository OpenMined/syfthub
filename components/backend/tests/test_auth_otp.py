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
    """Config returns defaults when SMTP is not configured."""
    response = client.get("/api/v1/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert data["require_email_verification"] is False
    assert data["smtp_configured"] is False
    assert data["password_reset_enabled"] is False


def test_auth_config_smtp_enabled(client: TestClient, monkeypatch) -> None:
    """Config reflects SMTP + verification settings."""
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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

    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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

    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")
    monkeypatch.setattr("syfthub.core.config.settings.require_email_verification", True)

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


def test_password_reset_request_no_smtp(client: TestClient) -> None:
    """Password reset request returns 200 even without SMTP."""
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "otp@example.com"},
    )
    assert response.status_code == 200


@patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
def test_password_reset_request_with_smtp(
    mock_send, client: TestClient, monkeypatch
) -> None:
    """Password reset request sends OTP when SMTP is configured."""
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")

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
    monkeypatch.setattr("syfthub.core.config.settings.smtp_host", "smtp.test.com")

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
