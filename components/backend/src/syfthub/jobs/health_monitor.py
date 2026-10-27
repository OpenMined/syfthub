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
    skip the cycle gracefully. The lock is released explicitly when
    the database session closes, including on worker crashes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Iterator, Optional

from sqlalchemy import case, select, update
from sqlalchemy.sql import label

from syfthub.database.connection import db_manager
from syfthub.models.endpoint import EndpointModel
from syfthub.models.satellite import SatelliteModel
from syfthub.models.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.core.config import Settings

logger = logging.getLogger(__name__)

# PostgreSQL advisory lock ID for health monitor cycle exclusion.
# Ensures only one worker runs the health check cycle at a time in
# multi-worker deployments (e.g., uvicorn --workers 4).
HEALTH_MONITOR_LOCK_ID = 839201

# Endpoints per bulk UPDATE. Keeps the IN list bounded on large catalogues.
_UPDATE_CHUNK = 500


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    """Yield ``items`` in consecutive slices of at most ``size``."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


@dataclass
class EndpointHealthInfo:
    """Data class for endpoint health check information."""

    id: int
    slug: str  # Endpoint slug for health check URL
    endpoint_type: str  # "model" or "data_source"
    is_active: bool
    connect: list[dict[str, Any]]
    # Origin of the satellite serving this endpoint; None when it has none.
    base_url: Optional[str]
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

    def _get_endpoints_for_health_check(
        self, session: Session
    ) -> list[EndpointHealthInfo]:
        """Query all endpoints with their serving origin and per-endpoint health.

        The origin comes from the satellite serving each endpoint, not from the
        owning account — one account can serve endpoints from several hosts.

        Endpoints with no serving satellite are included and will be marked
        unhealthy (is_active=False): there is no origin, so nothing can reach
        them. The satellite join is therefore an OUTER join.

        Args:
            session: Database session to use for the query

        Returns:
            List of EndpointHealthInfo objects containing endpoint data, the
            serving origin, and per-endpoint health fields
        """
        # Query endpoints joined with their owning user
        user_endpoints_stmt = (
            select(
                EndpointModel.id,
                EndpointModel.slug,
                EndpointModel.type,
                EndpointModel.is_active,
                EndpointModel.connect,
                SatelliteModel.base_url,
                label("owner_id", UserModel.id),
                EndpointModel.health_status,
                EndpointModel.health_checked_at,
                EndpointModel.health_ttl_seconds,
            )
            .join(UserModel, EndpointModel.user_id == UserModel.id)
            .outerjoin(SatelliteModel, EndpointModel.space_id == SatelliteModel.id)
        )

        endpoints: list[EndpointHealthInfo] = []

        user_results = session.execute(user_endpoints_stmt).all()
        for row in user_results:
            (
                endpoint_id,
                slug,
                endpoint_type,
                is_active,
                connect,
                base_url,
                owner_id,
                health_status,
                health_checked_at,
                health_ttl_seconds,
            ) = row
            # Include endpoints with connections (even if there is no origin);
            # those are marked unhealthy during the health check
            if connect:
                endpoints.append(
                    EndpointHealthInfo(
                        id=endpoint_id,
                        slug=slug,
                        endpoint_type=endpoint_type,
                        is_active=is_active,
                        connect=connect,
                        base_url=base_url,  # May be None
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
        now: Optional[datetime] = None,
    ) -> tuple[int, bool]:
        """Determine if an endpoint is healthy from client-reported health.

        Per-endpoint health (client-reported via POST /endpoints/health):
        if health_checked_at + health_ttl_seconds > now, trust health_status.
        Otherwise — no report, or the report has expired — mark unhealthy.

        Args:
            endpoint: The endpoint information to evaluate
            now: The instant the endpoint's health fields were read. The
                cycle passes one clock for its whole snapshot; defaults to
                the current time for ad-hoc callers.

        Returns:
            Tuple of (endpoint_id, is_healthy)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # No serving satellite means no origin, so nothing can reach it.
        if not endpoint.base_url:
            logger.debug(f"Endpoint {endpoint.id}: no serving satellite (unhealthy)")
            return (endpoint.id, False)

        # Per-endpoint health (client-reported)
        is_healthy = self._check_per_endpoint_health(endpoint, now)
        if is_healthy is not None:
            return (endpoint.id, is_healthy)

        # No fresh per-endpoint health signal — mark unhealthy
        logger.debug(f"Endpoint {endpoint.id}: no fresh health signal (unhealthy)")
        return (endpoint.id, False)

    def _update_health_statuses(
        self, session: Session, verdicts: dict[int, bool]
    ) -> dict[int, tuple[bool, int]]:
        """Apply one cycle's verdicts to every endpoint in two bulk UPDATEs.

        Healthy endpoints reset ``consecutive_failure_count`` and become
        active; unhealthy ones increment it and are deactivated once the
        count reaches ``failure_threshold``. Both statements run in one
        transaction, so a cycle costs one commit instead of one per endpoint,
        which is what let the production cycle drift from 30 s to over a
        minute.

        Multi-worker safe: all state lives in the database. The CASE for
        ``is_active`` compares ``count + 1`` because the increment happens
        in the same statement.

        Args:
            session: Database session to use for the update
            verdicts: ``{endpoint_id: is_healthy}`` for this cycle

        Returns:
            ``{endpoint_id: (new_is_active, new_failure_count)}`` for every
            row the UPDATEs touched. Endpoints deleted between the snapshot
            and the update are simply absent. Empty when the database
            rejected the transaction (it is rolled back).
        """
        healthy_ids = [eid for eid, ok in verdicts.items() if ok]
        unhealthy_ids = [eid for eid, ok in verdicts.items() if not ok]
        returning = (
            EndpointModel.id,
            EndpointModel.is_active,
            EndpointModel.consecutive_failure_count,
        )
        results: dict[int, tuple[bool, int]] = {}
        try:
            for chunk in _chunks(healthy_ids, _UPDATE_CHUNK):
                stmt = (
                    update(EndpointModel)
                    .where(EndpointModel.id.in_(chunk))  # type: ignore[attr-defined]
                    .values(consecutive_failure_count=0, is_active=True)
                    .returning(*returning)
                    .execution_options(synchronize_session=False)
                )
                for row in session.execute(stmt):
                    results[int(row[0])] = (bool(row[1]), int(row[2]))
            for chunk in _chunks(unhealthy_ids, _UPDATE_CHUNK):
                stmt = (
                    update(EndpointModel)
                    .where(EndpointModel.id.in_(chunk))  # type: ignore[attr-defined]
                    .values(
                        consecutive_failure_count=EndpointModel.consecutive_failure_count  # type: ignore[operator]
                        + 1,
                        is_active=case(
                            (
                                EndpointModel.consecutive_failure_count + 1  # type: ignore[operator]
                                >= self.failure_threshold,
                                False,
                            ),
                            else_=EndpointModel.is_active,
                        ),
                    )
                    .returning(*returning)
                    .execution_options(synchronize_session=False)
                )
                for row in session.execute(stmt):
                    results[int(row[0])] = (bool(row[1]), int(row[2]))
            session.commit()
            return results
        except Exception as e:
            logger.error(f"Failed to update endpoint health statuses: {e}")
            session.rollback()
            return {}

    def _current_bucket_start(self, now: datetime) -> datetime:
        """Return the UTC bucket boundary that ``now`` falls into."""
        epoch = int(now.timestamp())
        floored = (epoch // self.bucket_seconds) * self.bucket_seconds
        return datetime.fromtimestamp(floored, tz=timezone.utc)

    def _emit_uptime_samples(
        self,
        session: Session,
        samples: list[tuple[int, bool, bool]],
        now: datetime,
    ) -> None:
        """Persist this cycle's uptime samples in one transaction, swallowing errors.

        Each tuple is ``(endpoint_id, reported_healthy, is_active)``: what the
        client reported, and what the Hub concluded after the consecutive-
        failure rule. The chart draws the latter, so one missed report does
        not paint a day red; the former is kept for diagnosis.

        Samples are bucketed by ``self.bucket_seconds`` so a single bucket
        accumulates many monitor cycles (e.g. 60 cycles per 30-minute bucket
        at the default 30s interval).
        """
        from syfthub.repositories.endpoint import EndpointRepository

        if not samples:
            return
        bucket_start = self._current_bucket_start(now)
        try:
            repo = EndpointRepository(session)
            repo.upsert_uptime_samples(
                [
                    (endpoint_id, bucket_start, is_healthy, is_active)
                    for endpoint_id, is_healthy, is_active in samples
                ]
            )
            session.commit()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Failed to record {len(samples)} uptime sample(s): {e}")
            session.rollback()

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
        # The advisory lock keeps one worker per cycle across the deployment
        # (prevents flapping). It lives on this connection for the whole
        # cycle and is released on exit; see ``DatabaseManager.locked_session``.
        with db_manager.locked_session(HEALTH_MONITOR_LOCK_ID) as session:
            if session is None:
                logger.debug(
                    "Skipping health check cycle - another worker holds the lock"
                )
                return

            # One clock for the whole cycle, taken before the snapshot: every
            # endpoint is judged against the moment its health fields were
            # read. Taking a fresh ``now`` per endpoint used to age the
            # snapshot by however long the cycle had already run, so on a
            # slow cycle endpoints late in the list looked stale although
            # newer reports had already landed.
            now = datetime.now(timezone.utc)

            # Once per UTC day, sweep old uptime samples. Lock-holder only,
            # so this runs from a single worker process per day.
            self._maybe_run_uptime_retention(session, now)

            # Get all endpoints that can be health checked
            endpoints = self._get_endpoints_for_health_check(session)

            if not endpoints:
                logger.debug("No endpoints to health check")
                return

            logger.debug(f"Starting health check for {len(endpoints)} endpoints")

            # Build a map of endpoint_id -> old_is_active for state change detection
            old_status_map = {ep.id: ep.is_active for ep in endpoints}

            # Evaluate each endpoint's health (no I/O — purely signal-based)
            verdicts: dict[int, bool] = {}
            for endpoint in endpoints:
                endpoint_id, is_healthy = self._check_endpoint_health(endpoint, now)
                verdicts[endpoint_id] = is_healthy

            # Two bulk statements, one commit: failure counts and is_active.
            # Endpoints deleted since the snapshot are absent from the result.
            results = self._update_health_statuses(session, verdicts)

            # One uptime sample per endpoint per cycle, in its own transaction
            # so a telemetry error cannot undo the status update above.
            self._emit_uptime_samples(
                session,
                [
                    (endpoint_id, verdicts[endpoint_id], new_is_active)
                    for endpoint_id, (new_is_active, _) in results.items()
                ],
                now,
            )

            state_changes = 0
            for endpoint_id, (new_is_active, failure_count) in results.items():
                is_healthy = verdicts[endpoint_id]
                old_is_active = old_status_map.get(endpoint_id, True)

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
