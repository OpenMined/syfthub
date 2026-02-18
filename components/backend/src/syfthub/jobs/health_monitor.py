"""Endpoint health monitoring background job.

This module provides a background task that periodically checks the health
of all registered endpoints using a hybrid approach:

1. For endpoints with fresh heartbeats (user or org): Skip HTTP check, assume healthy
2. For endpoints with stale/missing heartbeats: Make HTTP verification call
3. If HTTP verification succeeds for stale heartbeat: Refresh with grace period

If an endpoint becomes unreachable, its is_active status is set to False.
If a previously inactive endpoint becomes reachable, its is_active status
is restored to True.

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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import case, or_, select, text, update
from sqlalchemy.sql import label
from sqlalchemy.sql.expression import literal

from syfthub.core.url_builder import build_connection_url
from syfthub.database.connection import db_manager
from syfthub.models.endpoint import EndpointModel
from syfthub.models.organization import OrganizationModel
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
    owner_id: int  # ID of the owner (user or organization)
    owner_type: str  # "user" or "organization"
    heartbeat_expires_at: Optional[datetime]  # When heartbeat expires


class EndpointHealthMonitor:
    """Background task for monitoring endpoint health.

    This class manages a periodic health check cycle that:
    1. Queries all endpoints with their owner's domain
    2. Makes HTTP requests to each endpoint's connection URL
    3. Updates is_active status based on reachability

    Attributes:
        enabled: Whether health monitoring is enabled
        interval: Seconds between health check cycles
        timeout: Timeout for individual health check requests
        max_concurrent: Maximum concurrent health check requests
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize the health monitor with settings.

        Args:
            settings: Application settings containing health check configuration
        """
        self.enabled = settings.health_check_enabled
        self.interval = settings.health_check_interval_seconds
        self.timeout = settings.health_check_timeout_seconds
        self.max_concurrent = settings.health_check_max_concurrent
        self.grace_period = settings.heartbeat_grace_period_seconds
        self.failure_threshold = settings.health_check_failure_threshold
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
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

    def _build_health_check_url(
        self, owner_domain: str, endpoint_type: str, slug: str
    ) -> Optional[str]:
        """Build URL for endpoint-specific health check.

        Constructs the health check URL based on the endpoint type:
        - model → /api/v1/models/{slug}/health
        - data_source → /api/v1/datasets/{slug}/health

        These endpoints are exposed by SyftAI-Space nodes and verify that
        the specific endpoint exists and is operational, not just that
        the server is reachable.

        Args:
            owner_domain: The domain of the endpoint owner (user or organization)
            endpoint_type: The type of endpoint ("model" or "data_source")
            slug: The endpoint slug for the health check URL

        Returns:
            The health check URL, or None if domain is not provided
        """
        if not owner_domain:
            return None

        # Build endpoint-specific health check path based on type
        if endpoint_type == "model":
            health_path = f"/api/v1/models/{slug}/health"
        elif endpoint_type == "data_source":
            health_path = f"/api/v1/datasets/{slug}/health"
        else:
            # Fallback to general health endpoint for unknown types
            health_path = "/api/v1/health"

        return build_connection_url(owner_domain, "https", path=health_path)

    def _get_endpoints_for_health_check(
        self, session: Session
    ) -> list[EndpointHealthInfo]:
        """Query all endpoints with their owner's domain and heartbeat info.

        This method performs a query that joins endpoints with their owners
        (either users or organizations) to get the domain and heartbeat
        information needed for hybrid health checking.

        For user-owned endpoints, heartbeat_expires_at is included to enable
        skipping HTTP checks when heartbeat is fresh.

        Endpoints without owner domains are included and will be marked as
        unhealthy (is_active=False) during the health check cycle.

        Args:
            session: Database session to use for the query

        Returns:
            List of EndpointHealthInfo objects containing endpoint data,
            owner domain, and heartbeat information
        """
        # Query endpoints with user domain and heartbeat info (user-owned endpoints)
        user_endpoints_stmt = select(
            EndpointModel.id,
            EndpointModel.slug,
            EndpointModel.type,
            EndpointModel.is_active,
            EndpointModel.connect,
            UserModel.domain,
            label("owner_id", UserModel.id),
            UserModel.heartbeat_expires_at,
        ).join(UserModel, EndpointModel.user_id == UserModel.id)

        # Query endpoints with organization domain (org-owned endpoints)
        org_endpoints_stmt = select(
            EndpointModel.id,
            EndpointModel.slug,
            EndpointModel.type,
            EndpointModel.is_active,
            EndpointModel.connect,
            OrganizationModel.domain,
            label("owner_id", OrganizationModel.id),
            OrganizationModel.heartbeat_expires_at,
        ).join(OrganizationModel, EndpointModel.organization_id == OrganizationModel.id)

        endpoints: list[EndpointHealthInfo] = []

        # Execute user endpoints query
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
                heartbeat_expires_at,
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
                        heartbeat_expires_at=heartbeat_expires_at,
                    )
                )

        # Execute organization endpoints query
        org_results = session.execute(org_endpoints_stmt).all()
        for row in org_results:
            (
                endpoint_id,
                slug,
                endpoint_type,
                is_active,
                connect,
                domain,
                owner_id,
                heartbeat_expires_at,
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
                        owner_type="organization",
                        heartbeat_expires_at=heartbeat_expires_at,
                    )
                )

        return endpoints

    async def _check_endpoint_health(
        self,
        endpoint: EndpointHealthInfo,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
        session: Session,
    ) -> tuple[int, bool]:
        """Check if a single endpoint is healthy using hybrid approach.

        For user-owned endpoints with fresh heartbeats, skips HTTP check.
        For stale/missing heartbeats or org endpoints, makes HTTP verification.
        If HTTP verification succeeds for stale heartbeat, refreshes with grace period.

        Args:
            endpoint: The endpoint information to check
            semaphore: Semaphore to limit concurrent requests
            client: Async HTTP client to use for the request
            session: Database session for heartbeat refresh

        Returns:
            Tuple of (endpoint_id, is_healthy)
            - endpoint_id: ID of the endpoint checked
            - is_healthy: Whether the endpoint is currently healthy
        """
        async with semaphore:
            now = datetime.now(timezone.utc)

            # Check if owner has a domain configured
            if not endpoint.owner_domain:
                # No domain configured - endpoint cannot be reached
                logger.debug(
                    f"Endpoint {endpoint.id} health check: no owner domain configured "
                    f"(unhealthy)"
                )
                return (endpoint.id, False)

            # Check if heartbeat is fresh (applies to both users and organizations)
            if endpoint.heartbeat_expires_at and endpoint.heartbeat_expires_at > now:
                # Heartbeat is fresh -> assume healthy, skip HTTP check
                logger.debug(
                    f"Endpoint {endpoint.id} has fresh heartbeat "
                    f"(expires {endpoint.heartbeat_expires_at}), skipping HTTP check"
                )
                return (endpoint.id, True)

            # Heartbeat is stale/missing -> need HTTP verification
            url = self._build_health_check_url(
                endpoint.owner_domain, endpoint.endpoint_type, endpoint.slug
            )
            if not url:
                # No valid URL to check, assume current state
                return (endpoint.id, endpoint.is_active)

            try:
                # Make a simple GET request to check connectivity
                response = await client.get(url, timeout=self.timeout)
                # Only 2xx and 3xx responses are considered healthy
                # 4xx (client errors like 404) and 5xx (server errors) are unhealthy
                is_healthy = response.status_code < 400
                logger.debug(
                    f"Endpoint {endpoint.id} health check: {url} -> {response.status_code} "
                    f"({'healthy' if is_healthy else 'unhealthy'})"
                )

                # If healthy, refresh heartbeat with grace period
                if is_healthy:
                    self._refresh_heartbeat_expiry(
                        session, endpoint.owner_id, endpoint.owner_type
                    )
                    logger.debug(
                        f"Endpoint {endpoint.id} HTTP check passed, "
                        f"refreshed heartbeat with {self.grace_period}s grace period"
                    )

                return (endpoint.id, is_healthy)

            except httpx.TimeoutException:
                logger.debug(f"Endpoint {endpoint.id} health check: {url} -> timeout")
                return (endpoint.id, False)
            except httpx.RequestError as e:
                logger.debug(
                    f"Endpoint {endpoint.id} health check: {url} -> error: {e}"
                )
                return (endpoint.id, False)

    def _refresh_heartbeat_expiry(
        self, session: Session, owner_id: int, owner_type: str
    ) -> bool:
        """Atomically refresh heartbeat expiry, only if it extends the current value.

        This is called when HTTP verification succeeds for a user or organization
        with a stale or missing heartbeat. Uses a conditional UPDATE to ensure
        we only extend the expiry, never shorten it (prevents race condition with
        concurrent heartbeat updates from the client).

        Args:
            session: Database session to use for the update
            owner_id: ID of the owner (user or organization) to refresh
            owner_type: Type of owner ("user" or "organization")

        Returns:
            True if the heartbeat was updated, False if no update was needed
            (either owner not found or current expiry is already longer)
        """
        try:
            model = UserModel if owner_type == "user" else OrganizationModel
            new_expiry = datetime.now(timezone.utc) + timedelta(
                seconds=self.grace_period
            )

            # Atomic conditional UPDATE: only set expiry if new value is larger
            # This prevents overwriting a fresher heartbeat from the client
            stmt = (
                update(model)
                .where(model.id == owner_id)
                .where(
                    or_(
                        model.heartbeat_expires_at.is_(None),  # type: ignore[attr-defined]
                        model.heartbeat_expires_at < new_expiry,  # type: ignore[operator]
                    )
                )
                .values(heartbeat_expires_at=new_expiry)
            )
            result = session.execute(stmt)
            session.commit()
            return bool(result.rowcount > 0)  # type: ignore[attr-defined]
        except Exception as e:
            logger.error(
                f"Failed to refresh heartbeat for {owner_type} {owner_id}: {e}"
            )
            session.rollback()
            return False

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

        Uses Core-level UPDATE to bypass the ORM's onupdate hook on updated_at.
        Health monitor status changes should not modify the updated_at timestamp.

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

    async def run_health_check_cycle(self) -> None:
        """Run one complete health check cycle for all endpoints.

        This method uses a hybrid approach:
        1. Queries all endpoints with their owner's domain and heartbeat info
        2. For user endpoints with fresh heartbeats: Skip HTTP, assume healthy
        3. For stale/missing heartbeats or org endpoints: Make HTTP check
        4. If HTTP succeeds for stale user: Refresh heartbeat with grace period
        5. Atomically updates is_active status and failure counts in the database
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

            # Get all endpoints that can be health checked
            endpoints = self._get_endpoints_for_health_check(session)

            if not endpoints:
                logger.debug("No endpoints to health check")
                return

            logger.debug(f"Starting health check for {len(endpoints)} endpoints")

            # Build a map of endpoint_id -> old_is_active for state change detection
            old_status_map = {ep.id: ep.is_active for ep in endpoints}

            # Create semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent)

            # Check all endpoints concurrently
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(self.timeout),
            ) as client:
                tasks = [
                    self._check_endpoint_health(endpoint, semaphore, client, session)
                    for endpoint in endpoints
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results and update endpoints atomically
            state_changes = 0
            for result in results:
                if isinstance(result, BaseException):
                    logger.error(f"Health check task failed: {result}")
                    continue

                # Result is tuple[int, bool] - simple!
                endpoint_id, is_healthy = result

                # Get the old status for comparison
                old_is_active = old_status_map.get(endpoint_id, True)

                # Atomically update failure count and status in database
                update_result = self._update_endpoint_health_status(
                    session, endpoint_id, is_healthy
                )

                if update_result is None:
                    # Endpoint was deleted between query and update
                    continue

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
            f"(interval: {self.interval}s, timeout: {self.timeout}s, "
            f"max_concurrent: {self.max_concurrent}, "
            f"failure_threshold: {self.failure_threshold})"
        )

        while self._running:
            try:
                await self.run_health_check_cycle()
            except asyncio.CancelledError:
                logger.info("Health check cycle cancelled")
                break
            except Exception as e:
                logger.error(f"Health check cycle failed: {e}", exc_info=True)

            # Wait for the next cycle
            try:
                await asyncio.sleep(self.interval)
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
