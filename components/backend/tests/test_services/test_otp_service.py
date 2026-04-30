"""Tests for OTPService."""

from unittest.mock import MagicMock, patch

import pytest

from syfthub.domain.exceptions import (
    InvalidOTPError,
    OTPMaxAttemptsError,
    OTPRateLimitedError,
)
from syfthub.services.otp_service import OTPService, _hash_code


class TestHashCode:
    def test_produces_sha256_hex(self):
        result = _hash_code("123456")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_input_same_output(self):
        assert _hash_code("abc") == _hash_code("abc")

    def test_different_inputs_different_outputs(self):
        assert _hash_code("123456") != _hash_code("654321")


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def otp_service(mock_session):
    return OTPService(mock_session)


class TestGenerateOtp:
    def test_generates_code_successfully(self, otp_service):
        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_ip_rate_limit_window_minutes = 60
            mock_settings.otp_ip_rate_limit_max_requests = 5
            mock_settings.otp_rate_limit_window_minutes = 60
            mock_settings.otp_rate_limit_max_requests = 10
            mock_settings.otp_expiry_minutes = 10
            otp_service.otp_repo.count_recent_by_ip = MagicMock(return_value=0)
            otp_service.otp_repo.count_recent = MagicMock(return_value=0)
            otp_service.otp_repo.invalidate_existing = MagicMock()
            mock_otp = MagicMock()
            otp_service.otp_repo.create_otp = MagicMock(return_value=mock_otp)

            code = otp_service.generate_otp("test@example.com", "login", "192.168.1.1")
            assert len(code) == 6
            assert code.isdigit()

    def test_raises_when_ip_rate_limited(self, otp_service):
        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_ip_rate_limit_window_minutes = 60
            mock_settings.otp_ip_rate_limit_max_requests = 5
            otp_service.otp_repo.count_recent_by_ip = MagicMock(return_value=10)

            with pytest.raises(OTPRateLimitedError):
                otp_service.generate_otp("test@example.com", "login", "192.168.1.1")

    def test_raises_when_email_rate_limited(self, otp_service):
        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_rate_limit_window_minutes = 60
            mock_settings.otp_rate_limit_max_requests = 3
            otp_service.otp_repo.count_recent = MagicMock(return_value=5)

            with pytest.raises(OTPRateLimitedError):
                otp_service.generate_otp("test@example.com", "login")

    def test_raises_invalid_when_create_returns_none(self, otp_service):
        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_rate_limit_window_minutes = 60
            mock_settings.otp_rate_limit_max_requests = 10
            mock_settings.otp_expiry_minutes = 10
            otp_service.otp_repo.count_recent = MagicMock(return_value=0)
            otp_service.otp_repo.invalidate_existing = MagicMock()
            otp_service.otp_repo.create_otp = MagicMock(return_value=None)

            with pytest.raises(InvalidOTPError):
                otp_service.generate_otp("test@example.com", "login")

    def test_no_ip_check_when_ip_is_none(self, otp_service):
        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_rate_limit_window_minutes = 60
            mock_settings.otp_rate_limit_max_requests = 10
            mock_settings.otp_expiry_minutes = 10
            otp_service.otp_repo.count_recent = MagicMock(return_value=0)
            otp_service.otp_repo.count_recent_by_ip = MagicMock(return_value=0)
            otp_service.otp_repo.invalidate_existing = MagicMock()
            mock_otp = MagicMock()
            otp_service.otp_repo.create_otp = MagicMock(return_value=mock_otp)

            otp_service.generate_otp("test@example.com", "login", requester_ip=None)
            otp_service.otp_repo.count_recent_by_ip.assert_not_called()


class TestVerifyOtp:
    def _make_mock_otp(self, code: str, attempts: int = 0):
        mock_otp = MagicMock()
        mock_otp.id = 1
        mock_otp.attempts = attempts
        mock_otp.code_hash = _hash_code(code)
        return mock_otp

    def test_returns_true_on_valid_code(self, otp_service):
        code = "123456"
        mock_otp = self._make_mock_otp(code)
        otp_service.otp_repo.get_active_otp = MagicMock(return_value=mock_otp)
        otp_service.otp_repo.increment_attempts = MagicMock(return_value=1)
        otp_service.otp_repo.mark_used = MagicMock(return_value=True)

        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_max_attempts = 5
            result = otp_service.verify_otp("test@example.com", code, "login")
            assert result is True

    def test_raises_when_no_active_otp(self, otp_service):
        otp_service.otp_repo.get_active_otp = MagicMock(return_value=None)
        with pytest.raises(InvalidOTPError):
            otp_service.verify_otp("test@example.com", "123456", "login")

    def test_raises_max_attempts_when_exceeded(self, otp_service):
        code = "123456"
        mock_otp = self._make_mock_otp(code, attempts=5)
        otp_service.otp_repo.get_active_otp = MagicMock(return_value=mock_otp)

        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_max_attempts = 5
            with pytest.raises(OTPMaxAttemptsError):
                otp_service.verify_otp("test@example.com", code, "login")

    def test_raises_invalid_on_wrong_code(self, otp_service):
        mock_otp = self._make_mock_otp("123456", attempts=0)
        otp_service.otp_repo.get_active_otp = MagicMock(return_value=mock_otp)
        otp_service.otp_repo.increment_attempts = MagicMock(return_value=1)

        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_max_attempts = 5
            with pytest.raises(InvalidOTPError):
                otp_service.verify_otp("test@example.com", "999999", "login")

    def test_raises_max_attempts_on_last_wrong_attempt(self, otp_service):
        mock_otp = self._make_mock_otp("123456", attempts=4)
        otp_service.otp_repo.get_active_otp = MagicMock(return_value=mock_otp)
        otp_service.otp_repo.increment_attempts = MagicMock(return_value=5)

        with patch("syfthub.services.otp_service.settings") as mock_settings:
            mock_settings.otp_max_attempts = 5
            with pytest.raises(OTPMaxAttemptsError):
                otp_service.verify_otp("test@example.com", "999999", "login")
