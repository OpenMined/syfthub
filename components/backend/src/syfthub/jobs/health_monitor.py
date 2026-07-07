"""Endpoint health monitoring background job.

This module provides a background task that periodically evaluates the health
of all registered endpoints from client-reported per-endpoint health:

   Per-endpoint health (client-reported via POST /endpoints/health):
   If health_checked_at + health_ttl_seconds > now, the client-reported
   status is trusted. Otherwise — no report, or the report has expired — the
   endpoint is considered unhealthy.

After consecutive failures reach the configured threshold, is_active is set
to False. If the endpoint becomes healthy again, is_active is restored.

Multi-worker safety:
    In multi-worker deployments (e.g., uvicorn --workers 4), each worker
    starts its own health monitor loop. A PostgreSQL advisory lock
    (pg_try_advisory_lock) ensures only one worker executes the health
    check cycle at any given time. Workers that cannot acquire the lock
    skip the cycle gracefully. The lock is automatically released when
    the database session closes, including on worker crashes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import case, select, text, update
from sqlalchemy.sql import label
from sqlalchemy.sql.expression import literal

from syfthub.database.connection import db_manager
from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.core.config import Settings

logger = logging.getLogger(__name__)

# PostgreSQL advisory lock ID for health monitor cycle exclusion.
# Ensures only one worker runs the health check cycle at a time in
# multi-worker deployments (e.g., uvicorn --workers 4).
HEALTH_MONITOR_LOCK_ID = 839201


@dataclass
class EndpointHealthInfo:
    """Data class for endpoint health check information."""

    id: int
    slug: str  # Endpoint slug for health check URL
    endpoint_type: str  # "model" or "data_source"
    is_active: bool
    connect: list[dict[str, Any]]
    owner_domain: Optional[str]  # None if owner has no domain configured
    owner_id: int  # ID of the owning user
    owner_type: str  # Always "user"
    # Per-endpoint health fields (reported by client via POST /endpoints/health)
    health_status: Optional[str] = None
    health_checked_at: Optional[datetime] = None
    health_ttl_seconds: Optional[int] = None


class EndpointHealthMonitor:
    """Background task for monitoring endpoint health.

    This class manages a periodic health check cycle that:
    1. Queries all endpoints with their owner's domain and per-endpoint health
    2. Evaluates health from the client-reported per-endpoint status
    3. Updates is_active status based on health signals

    Attributes:
        enabled: Whether health monitoring is enabled
        interval: Seconds between health check cycles
        failure_threshold: Consecutive failures before marking inactive
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the health monitor with settings.

        Args:
            settings: Application settings containing health check configuration
        """
        self.enabled = settings.health_check_enabled
        self.interval = settings.health_check_interval_seconds
        self.failure_threshold = settings.health_check_failure_threshold
        # ``getattr`` with defaults lets older test fixtures (which build
        # ``Settings`` from MagicMock) instantiate the monitor without
        # configuring the uptime fields. Production ``Settings`` always
        # supplies real integers.
        bucket = getattr(settings, "uptime_bucket_seconds", 1800)
        retention = getattr(settings, "uptime_retention_days", 90)
        self.bucket_seconds = max(1, bucket) if isinstance(bucket, int) else 1800
        self.uptime_retention_days = retention if isinstance(retention, int) else 90
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        # Tracks the most recent date we ran the uptime retention sweep so we
        # do it at most once per UTC day across cycles.
        self._last_retention_sweep_date: Optional[str] = None
        # Note: Consecutive failure tracking is stored in the database
        # (endpoints.consecutive_failure_count) for multi-worker safety

    def _try_acquire_cycle_lock(self, session: Session) -> bool:
        """Try to acquire a PostgreSQL advisory lock for this health check cycle.

        Uses pg_try_advisory_lock to ensure only one worker runs the health
        check at a time in multi-worker deployments. The lock is automatically
        released when the session is closed.

        For non-PostgreSQL databases (e.g., SQLite in development), always
        returns True since dev environments run a single worker.

        Args:
            session: Database session to use for lock acquisition

        Returns:
            True if the lock was acquired (or not needed), False otherwise
        """
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect != "postgresql":
            return True

        try:
            result = session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": HEALTH_MONITOR_LOCK_ID},
            )
            acquired = result.scalar()
            return bool(acquired)
        except Exception as e:
            logger.warning(f"Failed to acquire advisory lock: {e}")
            return False

    def _get_endpoints_for_health_check(
        self, session: Session
    ) -> list[EndpointHealthInfo]:
        """Query all endpoints with their owner's domain and per-endpoint health.

        This method joins endpoints with their owning user to get the domain
        and client-reported per-endpoint health fields needed for the health
        check cycle.

        Endpoints without owner domains are included and will be marked as
        unhealthy (is_active=False) during the health check cycle.

        Args:
            session: Database session to use for the query

        Returns:
            List of EndpointHealthInfo objects containing endpoint data,
            owner domain, and per-endpoint health fields
        """
        # Query endpoints joined with their owning user
        user_endpoints_stmt = select(
            EndpointModel.id,
            EndpointModel.slug,
            EndpointModel.type,
            EndpointModel.is_active,
            EndpointModel.connect,
            UserModel.domain,
            label("owner_id", UserModel.id),
            EndpointModel.health_status,
            EndpointModel.health_checked_at,
            EndpointModel.health_ttl_seconds,
        ).join(UserModel, EndpointModel.user_id == UserModel.id)

        endpoints: list[EndpointHealthInfo] = []

        user_results = session.execute(user_endpoints_stmt).all()
        for row in user_results:
            (
                endpoint_id,
                slug,
                endpoint_type,
                is_active,
                connect,
                domain,
                owner_id,
                health_status,
                health_checked_at,
                health_ttl_seconds,
            ) = row
            # Include endpoints with connections (even if domain is None)
            # Endpoints without domain will be marked unhealthy in health check
            if connect:
                endpoints.append(
                    EndpointHealthInfo(
                        id=endpoint_id,
                        slug=slug,
                        endpoint_type=endpoint_type,
                        is_active=is_active,
                        connect=connect,
                        owner_domain=domain,  # May be None
                        owner_id=owner_id,
                        owner_type="user",
                        health_status=health_status,
                        health_checked_at=health_checked_at,
                        health_ttl_seconds=health_ttl_seconds,
                    )
                )

        return endpoints

    def _check_per_endpoint_health(
        self,
        endpoint: EndpointHealthInfo,
        now: datetime,
    ) -> bool | None:
        """Check per-endpoint health reported via POST /endpoints/health.

        Returns True/False if a fresh per-endpoint health signal exists,
        or None if no fresh signal is available (no report, or the report has
        expired) — in which case the caller treats the endpoint as unhealthy.
        """
        if (
            endpoint.health_checked_at is not None
            and endpoint.health_ttl_seconds is not None
        ):
            health_expires_at = endpoint.health_checked_at + timedelta(
                seconds=endpoint.health_ttl_seconds
            )
            if health_expires_at > now:
                is_healthy = endpoint.health_status == "healthy"
                logger.debug(
                    f"Endpoint {endpoint.id}: fresh per-endpoint health "
                    f"(status={endpoint.health_status}, "
                    f"expires={health_expires_at})"
                )
                return is_healthy
        return None

    def _check_endpoint_health(
        self,
        endpoint: EndpointHealthInfo,
    ) -> tuple[int, bool]:
        """Determine if an endpoint is healthy from client-reported health.

        Per-endpoint health (client-reported via POST /endpoints/health):
        if health_checked_at + health_ttl_seconds > now, trust health_status.
        Otherwise — no report, or the report has expired — mark unhealthy.

        Args:
            endpoint: The endpoint information to evaluate

        Returns:
            Tuple of (endpoint_id, is_healthy)
        """
        now = datetime.now(timezone.utc)

        # Check if owner has a domain configured
        if not endpoint.owner_domain:
            logger.debug(
                f"Endpoint {endpoint.id}: no owner domain configured (unhealthy)"
            )
            return (endpoint.id, False)

        # Per-endpoint health (client-reported)
        is_healthy = self._check_per_endpoint_health(endpoint, now)
        if is_healthy is not None:
            return (endpoint.id, is_healthy)

        # No fresh per-endpoint health signal — mark unhealthy
        logger.debug(f"Endpoint {endpoint.id}: no fresh health signal (unhealthy)")
        return (endpoint.id, False)

    def _update_endpoint_health_status(
        self, session: Session, endpoint_id: int, is_healthy: bool
    ) -> tuple[bool, int] | None:
        """Atomically update endpoint health status with failure tracking.

        Uses a single atomic UPDATE with CASE expressions to:
        1. Reset consecutive_failure_count to 0 if healthy
        2. Increment consecutive_failure_count if unhealthy
        3. Set is_active=True if healthy
        4. Set is_active=False only if failure count reaches threshold

        This is multi-worker safe because all state is managed in the database
        atomically, not in memory.

        Args:
            session: Database session to use for the update
            endpoint_id: ID of the endpoint to update
            is_healthy: Whether the endpoint is currently healthy

        Returns:
            Tuple of (new_is_active, new_failure_count) if successful,
            None if the endpoint was not found
        """
        try:
            # Build atomic UPDATE with CASE expressions
            # Note: The CASE for is_active checks (count + 1) >= threshold because
            # the increment happens in the same statement
            stmt = (
                update(EndpointModel)
                .where(EndpointModel.id == endpoint_id)
                .values(
                    consecutive_failure_count=case(
                        (literal(is_healthy), 0),
                        else_=EndpointModel.consecutive_failure_count + 1,  # type: ignore[operator]
                    ),
                    is_active=case(
                        (literal(is_healthy), True),
                        (
                            EndpointModel.consecutive_failure_count + 1  # type: ignore[operator]
                            >= self.failure_threshold,
                            False,
                        ),
                        else_=EndpointModel.is_active,
                    ),
                )
                .returning(
                    EndpointModel.is_active, EndpointModel.consecutive_failure_count
                )
            )
            result = session.execute(stmt)
            row = result.fetchone()
            session.commit()

            if row:
                is_active: bool = row[0]  # type: ignore[assignment]
                failure_count: int = row[1]  # type: ignore[assignment]
                return (is_active, failure_count)
            return None
        except Exception as e:
            logger.error(f"Failed to update endpoint {endpoint_id} health status: {e}")
            session.rollback()
            return None

    def _current_bucket_start(self, now: datetime) -> datetime:
        """Return the UTC bucket boundary that ``now`` falls into."""
        epoch = int(now.timestamp())
        floored = (epoch // self.bucket_seconds) * self.bucket_seconds
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def _emit_uptime_sample(
        self,
        session: Session,
        endpoint_id: int,
        is_healthy: bool,
        now: datetime,
    ) -> None:
        """Persist one uptime sample for this cycle, swallowing errors.

        The sample is bucketed by ``self.bucket_seconds`` so a single bucket
        accumulates many monitor cycles (e.g. 60 cycles per 30-minute bucket
        at the default 30s interval).
        """
        from syfthub.repositories.endpoint import EndpointRepository

        try:
            repo = EndpointRepository(session)
            repo.upsert_uptime_sample(
                endpoint_id=endpoint_id,
                bucket_start=self._current_bucket_start(now),
                is_healthy=is_healthy,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                f"Failed to record uptime sample for endpoint {endpoint_id}: {e}"
            )

    def _maybe_run_uptime_retention(self, session: Session, now: datetime) -> None:
        """Delete uptime samples older than the configured retention window.

        Runs at most once per UTC day to keep the cost bounded. The first
        cycle of each day pays the deletion cost; subsequent cycles skip it.
        """
        if self.uptime_retention_days <= 0:
            return
        today = now.date().isoformat()
        if self._last_retention_sweep_date == today:
            return

        try:
            from syfthub.repositories.endpoint import EndpointRepository

            repo = EndpointRepository(session)
            removed = repo.delete_uptime_samples_older_than(self.uptime_retention_days)
            session.commit()
            self._last_retention_sweep_date = today
            if removed:
                logger.info(
                    f"Uptime retention sweep removed {removed} old sample(s) "
                    f"(retention: {self.uptime_retention_days} days)"
                )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Uptime retention sweep failed: {e}")
            session.rollback()

    async def run_health_check_cycle(self) -> None:
        """Run one health check cycle, offloaded to a worker thread.

        The cycle body is fully synchronous (blocking SQLAlchemy: advisory lock,
        full endpoint scan, per-row commits). Running it inline would block the
        shared event loop for the whole cycle, so it is dispatched to a thread.
        """
        await asyncio.to_thread(self._run_health_check_cycle_sync)

    def _run_health_check_cycle_sync(self) -> None:
        """Run one complete health check cycle for all endpoints.

        This method:
        1. Queries all endpoints with their owner's domain and per-endpoint health
        2. Evaluates each endpoint from the client-reported per-endpoint health
        3. Atomically updates is_active status and failure counts in the database
           (multi-worker safe - no in-memory state)
        """
        session = db_manager.get_session()
        try:
            # Acquire advisory lock to prevent multiple workers from running
            # the health check cycle simultaneously (prevents flapping)
            if not self._try_acquire_cycle_lock(session):
                logger.debug(
                    "Skipping health check cycle - another worker holds the lock"
                )
                return

            # Once per UTC day, sweep old uptime samples. Lock-holder only,
            # so this runs from a single worker process per day.
            self._maybe_run_uptime_retention(session, datetime.now(timezone.utc))

            # Get all endpoints that can be health checked
            endpoints = self._get_endpoints_for_health_check(session)

            if not endpoints:
                logger.debug("No endpoints to health check")
                return

            logger.debug(f"Starting health check for {len(endpoints)} endpoints")

            # Build a map of endpoint_id -> old_is_active for state change detection
            old_status_map = {ep.id: ep.is_active for ep in endpoints}

            # Evaluate each endpoint's health (no I/O — purely signal-based)
            now = datetime.now(timezone.utc)
            state_changes = 0
            for endpoint in endpoints:
                endpoint_id, is_healthy = self._check_endpoint_health(endpoint)

                # Get the old status for comparison
                old_is_active = old_status_map.get(endpoint_id, True)

                # Atomically update failure count and status in database
                update_result = self._update_endpoint_health_status(
                    session, endpoint_id, is_healthy
                )

                if update_result is None:
                    # Endpoint was deleted between query and update
                    continue

                # Record one uptime sample per cycle. Use a fresh session
                # transaction (the failure-counter update above already
                # committed) so an error here cannot poison the next loop.
                self._emit_uptime_sample(session, endpoint_id, is_healthy, now)
                try:
                    session.commit()
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(
                        f"Failed to commit uptime sample for endpoint "
                        f"{endpoint_id}: {e}"
                    )
                    session.rollback()

                new_is_active, failure_count = update_result

                # Log state changes
                if old_is_active != new_is_active:
                    state_changes += 1
                    if new_is_active:
                        logger.info(
                            f"Endpoint {endpoint_id} recovered, now active "
                            f"(failure count reset to 0)"
                        )
                    else:
                        logger.info(
                            f"Endpoint {endpoint_id} marked inactive after "
                            f"{failure_count} consecutive failures "
                            f"(threshold: {self.failure_threshold})"
                        )
                elif not is_healthy and failure_count < self.failure_threshold:
                    # Still accumulating failures
                    logger.debug(
                        f"Endpoint {endpoint_id} health check failed "
                        f"({failure_count}/{self.failure_threshold})"
                    )

            if state_changes > 0:
                logger.info(f"Updated {state_changes} endpoint(s) status")

        finally:
            session.close()

    async def start(self) -> None:
        """Start the health monitoring background loop.

        This method runs indefinitely, performing health check cycles
        at the configured interval until stop() is called.
        """
        if not self.enabled:
            logger.info("Endpoint health monitoring is disabled")
            return

        self._running = True
        logger.info(
            f"Starting endpoint health monitor "
            f"(interval: {self.interval}s, "
            f"failure_threshold: {self.failure_threshold})"
        )

        while self._running:
            cycle_start = time.monotonic()
            try:
                await self.run_health_check_cycle()
            except asyncio.CancelledError:
                logger.info("Health check cycle cancelled")
                break
            except Exception as e:
                logger.error(f"Health check cycle failed: {e}", exc_info=True)

            # Drift-correcting sleep: subtract time spent in the cycle so the
            # next cycle starts roughly self.interval seconds after the last one began.
            elapsed = time.monotonic() - cycle_start
            sleep_for = max(0.0, self.interval - elapsed)
            try:
                await asyncio.sleep(sleep_for)
            except asyncio.CancelledError:
                logger.info("Health monitor sleep cancelled")
                break

        logger.info("Endpoint health monitor stopped")

    async def stop(self) -> None:
        """Stop the health monitoring background loop.

        This method signals the monitoring loop to stop and waits
        for any pending operations to complete.
        """
        logger.info("Stopping endpoint health monitor...")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
