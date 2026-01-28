"""Endpoint health monitoring background job.

This module provides a background task that periodically checks the health
of all registered endpoints using a hybrid approach:

1. For endpoints with fresh heartbeats (user or org): Skip HTTP check, assume healthy
2. For endpoints with stale/missing heartbeats: Make HTTP verification call
3. If HTTP verification succeeds for stale heartbeat: Refresh with grace period

If an endpoint becomes unreachable, its is_active status is set to False.
If a previously inactive endpoint becomes reachable, its is_active status
is restored to True.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.sql import label

from syfthub.core.url_builder import build_connection_url, get_first_enabled_connection
from syfthub.database.connection import db_manager
from syfthub.models.endpoint import EndpointModel
from syfthub.models.organization import OrganizationModel
from syfthub.models.user import UserModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class EndpointHealthInfo:
    """Data class for endpoint health check information."""

    id: int
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
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    def _build_health_check_url(
        self, owner_domain: str, connect: list[dict[str, Any]]
    ) -> Optional[str]:
        """Build URL for health check from endpoint connection config.

        Checks the base domain to verify the server is reachable,
        rather than hitting the specific endpoint path.

        Args:
            owner_domain: The domain of the endpoint owner (user or organization)
            connect: List of connection configurations from the endpoint

        Returns:
            The base URL to check, or None if no valid connection is available
        """
        connection = get_first_enabled_connection(connect)
        if not connection:
            return None

        conn_type = connection.get("type", "rest_api")

        # Check the base domain only, not the specific endpoint path
        return build_connection_url(owner_domain, conn_type, path=None)

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
            EndpointModel.is_active,
            EndpointModel.connect,
            UserModel.domain,
            label("owner_id", UserModel.id),
            UserModel.heartbeat_expires_at,
        ).join(UserModel, EndpointModel.user_id == UserModel.id)

        # Query endpoints with organization domain (org-owned endpoints)
        org_endpoints_stmt = select(
            EndpointModel.id,
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
            endpoint_id, is_active, connect, domain, owner_id, heartbeat_expires_at = (
                row
            )
            # Include ALL endpoints for health checking
            # Endpoints without domain or connect will be marked unhealthy
            endpoints.append(
                EndpointHealthInfo(
                    id=endpoint_id,
                    is_active=is_active,
                    connect=connect or [],  # Ensure it's always a list
                    owner_domain=domain,  # May be None
                    owner_id=owner_id,
                    owner_type="user",
                    heartbeat_expires_at=heartbeat_expires_at,
                )
            )

        # Execute organization endpoints query
        org_results = session.execute(org_endpoints_stmt).all()
        for row in org_results:
            endpoint_id, is_active, connect, domain, owner_id, heartbeat_expires_at = (
                row
            )
            # Include ALL endpoints for health checking
            # Endpoints without domain or connect will be marked unhealthy
            endpoints.append(
                EndpointHealthInfo(
                    id=endpoint_id,
                    is_active=is_active,
                    connect=connect or [],  # Ensure it's always a list
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
    ) -> tuple[int, bool, bool]:
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
            Tuple of (endpoint_id, is_healthy, state_changed)
        """
        async with semaphore:
            now = datetime.now(timezone.utc)

            # Check if owner has a domain configured
            if not endpoint.owner_domain:
                # No domain configured - endpoint cannot be reached
                is_healthy = False
                logger.debug(
                    f"Endpoint {endpoint.id} health check: no owner domain configured "
                    f"(unhealthy)"
                )
                state_changed = endpoint.is_active != is_healthy
                return (endpoint.id, is_healthy, state_changed)

            # Check if heartbeat is fresh (applies to both users and organizations)
            if endpoint.heartbeat_expires_at and endpoint.heartbeat_expires_at > now:
                # Heartbeat is fresh -> assume healthy, skip HTTP check
                is_healthy = True
                logger.debug(
                    f"Endpoint {endpoint.id} has fresh heartbeat "
                    f"(expires {endpoint.heartbeat_expires_at}), skipping HTTP check"
                )
                state_changed = endpoint.is_active != is_healthy
                return (endpoint.id, is_healthy, state_changed)

            # Heartbeat is stale/missing -> need HTTP verification
            url = self._build_health_check_url(endpoint.owner_domain, endpoint.connect)
            if not url:
                # No valid URL to check (no enabled connections) - mark as unhealthy
                is_healthy = False
                logger.debug(
                    f"Endpoint {endpoint.id} health check: no valid connection URL "
                    f"(unhealthy)"
                )
                state_changed = endpoint.is_active != is_healthy
                return (endpoint.id, is_healthy, state_changed)

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

            except httpx.TimeoutException:
                is_healthy = False
                logger.debug(f"Endpoint {endpoint.id} health check: {url} -> timeout")
            except httpx.RequestError as e:
                is_healthy = False
                logger.debug(
                    f"Endpoint {endpoint.id} health check: {url} -> error: {e}"
                )

            state_changed = endpoint.is_active != is_healthy
            return (endpoint.id, is_healthy, state_changed)

    def _refresh_heartbeat_expiry(
        self, session: Session, owner_id: int, owner_type: str
    ) -> bool:
        """Refresh heartbeat expiry with grace period after successful HTTP check.

        This is called when HTTP verification succeeds for a user or organization
        with a stale or missing heartbeat. It gives them a short grace period
        before the next HTTP check is required.

        Args:
            session: Database session to use for the update
            owner_id: ID of the owner (user or organization) to refresh
            owner_type: Type of owner ("user" or "organization")

        Returns:
            True if the heartbeat was successfully refreshed, False otherwise
        """
        try:
            if owner_type == "user":
                owner = session.get(UserModel, owner_id)
            else:
                owner = session.get(OrganizationModel, owner_id)

            if not owner:
                logger.warning(
                    f"Cannot refresh heartbeat: {owner_type} {owner_id} not found"
                )
                return False

            owner.heartbeat_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=self.grace_period
            )
            session.commit()
            return True
        except Exception as e:
            logger.error(
                f"Failed to refresh heartbeat for {owner_type} {owner_id}: {e}"
            )
            session.rollback()
            return False

    def _update_endpoint_status(
        self, session: Session, endpoint_id: int, is_active: bool
    ) -> bool:
        """Update the is_active status of an endpoint.

        Args:
            session: Database session to use for the update
            endpoint_id: ID of the endpoint to update
            is_active: New is_active value

        Returns:
            True if update was successful, False otherwise
        """
        try:
            endpoint = session.get(EndpointModel, endpoint_id)
            if endpoint:
                endpoint.is_active = is_active
                session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to update endpoint {endpoint_id} status: {e}")
            session.rollback()
            return False

    async def run_health_check_cycle(self) -> None:
        """Run one complete health check cycle for all endpoints.

        This method uses a hybrid approach:
        1. Queries all endpoints with their owner's domain and heartbeat info
        2. For user endpoints with fresh heartbeats: Skip HTTP, assume healthy
        3. For stale/missing heartbeats or org endpoints: Make HTTP check
        4. If HTTP succeeds for stale user: Refresh heartbeat with grace period
        5. Updates is_active status for endpoints whose state changed
        """
        session = db_manager.get_session()
        try:
            # Get all endpoints that can be health checked
            endpoints = self._get_endpoints_for_health_check(session)

            if not endpoints:
                logger.debug("No endpoints to health check")
                return

            logger.debug(f"Starting health check for {len(endpoints)} endpoints")

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

            # Process results and update changed endpoints
            updated_count = 0
            for result in results:
                if isinstance(result, BaseException):
                    logger.error(f"Health check task failed: {result}")
                    continue

                # Result is tuple[int, bool, bool] at this point
                endpoint_id, is_healthy, state_changed = result
                if state_changed:
                    status_str = "active" if is_healthy else "inactive"
                    logger.info(
                        f"Endpoint {endpoint_id} status changed to {status_str}"
                    )
                    if self._update_endpoint_status(session, endpoint_id, is_healthy):
                        updated_count += 1

            if updated_count > 0:
                logger.info(f"Updated {updated_count} endpoint(s) status")

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
            f"max_concurrent: {self.max_concurrent})"
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
