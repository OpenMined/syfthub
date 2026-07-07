"""OTP code cleanup background job.

Periodically deletes expired and used OTP records that are older than the
configured retention period, preventing unbounded growth of the otp_codes table.

Multi-worker safety:
    Uses a PostgreSQL advisory lock (pg_try_advisory_lock) to ensure only
    one worker runs the cleanup cycle at a time. The lock is automatically
    released when the database session closes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import text

from syfthub.database.connection import db_manager
from syfthub.repositories.otp import OTPRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.core.config import Settings

logger = logging.getLogger(__name__)

OTP_CLEANUP_LOCK_ID = 839202


class OTPCleanupJob:
    """Background job that periodically purges stale OTP records."""

    def __init__(self, settings: Settings) -> None:
        self.interval = settings.otp_cleanup_interval_minutes * 60
        self.retention_hours = settings.otp_cleanup_retention_hours
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    def _try_acquire_lock(self, session: Session) -> bool:
        """Try to acquire PostgreSQL advisory lock for cleanup exclusion."""
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect != "postgresql":
            return True

        try:
            result = session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": OTP_CLEANUP_LOCK_ID},
            )
            return bool(result.scalar())
        except Exception as e:
            logger.warning(f"Failed to acquire OTP cleanup lock: {e}")
            return False

    async def run_cleanup_cycle(self) -> None:
        """Run a single cleanup cycle."""
        session = db_manager.get_session()
        try:
            if not self._try_acquire_lock(session):
                logger.debug("OTP cleanup lock held by another worker, skipping")
                return

            repo = OTPRepository(session)
            deleted = repo.delete_expired_used(self.retention_hours)
            if deleted > 0:
                logger.info(f"OTP cleanup: deleted {deleted} stale record(s)")
        except Exception as e:
            logger.error(f"OTP cleanup cycle failed: {e}", exc_info=True)
        finally:
            session.close()

    async def start(self) -> None:
        """Start the cleanup background loop."""
        self._running = True
        logger.info(
            f"Starting OTP cleanup job "
            f"(interval: {self.interval}s, retention: {self.retention_hours}h)"
        )

        while self._running:
            cycle_start = time.monotonic()
            try:
                await self.run_cleanup_cycle()
            except asyncio.CancelledError:
                logger.info("OTP cleanup cycle cancelled")
                break
            except Exception as e:
                logger.error(f"OTP cleanup cycle failed: {e}", exc_info=True)

            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, self.interval - elapsed)
            try:
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                logger.info("OTP cleanup sleep cancelled")
                break

        logger.info("OTP cleanup job stopped")

    async def stop(self) -> None:
        """Stop the cleanup background loop."""
        logger.info("Stopping OTP cleanup job...")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
