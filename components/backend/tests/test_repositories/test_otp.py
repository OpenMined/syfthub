"""Tests for OTP repository."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from syfthub.repositories.otp import OTPRepository


@pytest.fixture
def otp_repo(test_session):
    return OTPRepository(test_session)


@pytest.fixture
def future_expiry():
    return datetime.now(timezone.utc) + timedelta(minutes=10)


@pytest.fixture
def past_expiry():
    return datetime.now(timezone.utc) - timedelta(minutes=10)


class TestCreateOtp:
    def test_creates_otp_record(self, otp_repo, future_expiry):
        result = otp_repo.create_otp(
            email="test@example.com",
            code_hash="abc123",
            purpose="login",
            expires_at=future_expiry,
        )
        assert result is not None
        assert result.email == "test@example.com"
        assert result.code_hash == "abc123"
        assert result.purpose == "login"

    def test_lowercases_email(self, otp_repo, future_expiry):
        result = otp_repo.create_otp(
            email="TEST@EXAMPLE.COM",
            code_hash="abc123",
            purpose="login",
            expires_at=future_expiry,
        )
        assert result is not None
        assert result.email == "test@example.com"

    def test_stores_requester_ip(self, otp_repo, future_expiry):
        result = otp_repo.create_otp(
            email="test@example.com",
            code_hash="abc123",
            purpose="login",
            expires_at=future_expiry,
            requester_ip="192.168.1.1",
        )
        assert result is not None
        assert result.requester_ip == "192.168.1.1"

    def test_returns_none_on_exception(self, future_expiry):
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit.side_effect = Exception("DB error")
        repo = OTPRepository(mock_session)
        result = repo.create_otp("test@example.com", "hash", "login", future_expiry)
        assert result is None
        mock_session.rollback.assert_called_once()


class TestInvalidateExisting:
    def test_invalidates_active_otps(self, otp_repo, future_expiry):
        otp_repo.create_otp("test@example.com", "hash1", "login", future_expiry)
        otp_repo.invalidate_existing("test@example.com", "login")
        active = otp_repo.get_active_otp("test@example.com", "login")
        assert active is None

    def test_rollsback_on_exception(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        repo = OTPRepository(mock_session)
        repo.invalidate_existing("test@example.com", "login")
        mock_session.rollback.assert_called_once()


class TestIncrementAttempts:
    def test_increments_attempt_count(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result
        repo = OTPRepository(mock_session)
        new_count = repo.increment_attempts(1)
        assert new_count == 1

    def test_returns_scalar_value(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 3
        mock_session.execute.return_value = mock_result
        repo = OTPRepository(mock_session)
        count = repo.increment_attempts(1)
        assert count == 3

    def test_returns_zero_when_scalar_none(self):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result
        repo = OTPRepository(mock_session)
        count = repo.increment_attempts(1)
        assert count == 0

    def test_returns_zero_on_exception(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        repo = OTPRepository(mock_session)
        result = repo.increment_attempts(999)
        assert result == 0
        mock_session.rollback.assert_called_once()


class TestMarkUsed:
    def test_marks_otp_as_used(self, otp_repo, future_expiry):
        otp = otp_repo.create_otp(
            email="test@example.com",
            code_hash="hash1",
            purpose="login",
            expires_at=future_expiry,
        )
        assert otp is not None
        result = otp_repo.mark_used(otp.id)
        assert result is True
        active = otp_repo.get_active_otp("test@example.com", "login")
        assert active is None

    def test_returns_false_for_nonexistent_id(self, otp_repo):
        result = otp_repo.mark_used(99999)
        assert result is False

    def test_returns_false_on_exception(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        repo = OTPRepository(mock_session)
        result = repo.mark_used(1)
        assert result is False
        mock_session.rollback.assert_called_once()

    def test_returns_false_for_already_used(self, otp_repo, future_expiry):
        otp = otp_repo.create_otp(
            email="test@example.com",
            code_hash="hash1",
            purpose="login",
            expires_at=future_expiry,
        )
        assert otp is not None
        otp_repo.mark_used(otp.id)
        result = otp_repo.mark_used(otp.id)
        assert result is False


class TestDeleteExpiredUsed:
    def test_deletes_expired_records(self, otp_repo, past_expiry):
        otp_repo.create_otp("test@example.com", "hash1", "login", past_expiry)
        deleted = otp_repo.delete_expired_used(retention_hours=0)
        assert deleted >= 1

    def test_does_not_delete_active_records(self, otp_repo, future_expiry):
        otp_repo.create_otp("test@example.com", "hash1", "login", future_expiry)
        deleted = otp_repo.delete_expired_used(retention_hours=24)
        assert deleted == 0

    def test_returns_zero_on_exception(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        repo = OTPRepository(mock_session)
        result = repo.delete_expired_used(24)
        assert result == 0
        mock_session.rollback.assert_called_once()
