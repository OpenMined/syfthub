"""Tests for OTP cleanup background job."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syfthub.jobs.otp_cleanup import OTP_CLEANUP_LOCK_ID, OTPCleanupJob


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.otp_cleanup_interval_minutes = 60
    settings.otp_cleanup_retention_hours = 24
    return settings


@pytest.fixture
def job(mock_settings):
    return OTPCleanupJob(mock_settings)


class TestOTPCleanupJobInit:
    def test_init_sets_interval_and_retention(self, mock_settings):
        job = OTPCleanupJob(mock_settings)
        assert job.interval == 60 * 60
        assert job.retention_hours == 24
        assert job._running is False
        assert job._task is None

    def test_init_custom_values(self):
        settings = MagicMock()
        settings.otp_cleanup_interval_minutes = 30
        settings.otp_cleanup_retention_hours = 48
        job = OTPCleanupJob(settings)
        assert job.interval == 30 * 60
        assert job.retention_hours == 48


class TestRunCleanupCycle:
    @pytest.mark.asyncio
    async def test_skips_when_lock_not_acquired(self, job):
        mock_repo = MagicMock()

        with (
            patch("syfthub.jobs.otp_cleanup.db_manager") as mock_db,
            patch("syfthub.jobs.otp_cleanup.OTPRepository", return_value=mock_repo),
        ):
            mock_db.locked_session.return_value.__enter__.return_value = None
            await job.run_cleanup_cycle()
            mock_repo.delete_expired_used.assert_not_called()
            mock_db.locked_session.assert_called_once_with(OTP_CLEANUP_LOCK_ID)

    @pytest.mark.asyncio
    async def test_runs_cleanup_when_lock_acquired(self, job):
        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.delete_expired_used.return_value = 5

        with (
            patch("syfthub.jobs.otp_cleanup.db_manager") as mock_db,
            patch("syfthub.jobs.otp_cleanup.OTPRepository", return_value=mock_repo),
        ):
            mock_db.locked_session.return_value.__enter__.return_value = mock_session
            await job.run_cleanup_cycle()
            mock_repo.delete_expired_used.assert_called_once_with(24)

    @pytest.mark.asyncio
    async def test_logs_when_no_records_deleted(self, job):
        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.delete_expired_used.return_value = 0

        with (
            patch("syfthub.jobs.otp_cleanup.db_manager") as mock_db,
            patch("syfthub.jobs.otp_cleanup.OTPRepository", return_value=mock_repo),
        ):
            mock_db.locked_session.return_value.__enter__.return_value = mock_session
            await job.run_cleanup_cycle()

    @pytest.mark.asyncio
    async def test_handles_exception_during_cleanup(self, job):
        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.delete_expired_used.side_effect = Exception("repo error")

        with (
            patch("syfthub.jobs.otp_cleanup.db_manager") as mock_db,
            patch("syfthub.jobs.otp_cleanup.OTPRepository", return_value=mock_repo),
        ):
            mock_db.locked_session.return_value.__enter__.return_value = mock_session
            await job.run_cleanup_cycle()  # swallowed and logged, not raised


class TestStart:
    @pytest.mark.asyncio
    async def test_start_runs_one_cycle_then_stops(self, job):
        call_count = 0

        async def fake_cycle():
            nonlocal call_count
            call_count += 1
            job._running = False  # stop after first cycle

        job.interval = 0  # no sleep needed
        with (
            patch.object(job, "run_cleanup_cycle", side_effect=fake_cycle),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await job.start()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_start_breaks_on_cancelled_error_in_cycle(self, job):
        async def raise_cancelled():
            raise asyncio.CancelledError()

        with (
            patch.object(job, "run_cleanup_cycle", side_effect=raise_cancelled),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await job.start()

    @pytest.mark.asyncio
    async def test_start_handles_exception_in_cycle(self, job):
        call_count = 0

        async def fail_then_stop():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("transient error")
            job._running = False

        job.interval = 0
        with (
            patch.object(job, "run_cleanup_cycle", side_effect=fail_then_stop),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            await job.start()

        assert call_count == 2


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, job):
        job._running = True
        await job.stop()
        assert job._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_running_task(self, job):
        async def noop():
            pass

        real_task = asyncio.ensure_future(noop())
        real_task.cancel()

        job._task = real_task
        job._running = True

        await job.stop()

        assert job._running is False

    @pytest.mark.asyncio
    async def test_stop_skips_cancel_when_task_done(self, job):
        mock_task = MagicMock()
        mock_task.done.return_value = True
        job._task = mock_task
        job._running = True

        await job.stop()

        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_when_no_task(self, job):
        job._running = True
        job._task = None
        await job.stop()
        assert job._running is False
