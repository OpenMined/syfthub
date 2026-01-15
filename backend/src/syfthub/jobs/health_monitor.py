"""Endpoint health monitoring background job.

This module provides a background task that periodically checks the health
of all registered endpoints by making HTTP requests to their connection URLs.

If an endpoint becomes unreachable, its is_active status is set to False.
If a previously inactive endpoint becomes reachable, its is_active status
is restored to True.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import select

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
    owner_domain: str


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
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    def _build_health_check_url(
        self, owner_domain: str, connect: list[dict[str, Any]]
    ) -> Optional[str]:
        """Build URL for health check from endpoint connection config.

        Args:
            owner_domain: The domain of the endpoint owner (user or organization)
            connect: List of connection configurations from the endpoint

        Returns:
            The full URL to check, or None if no valid connection is available
        """
        connection = get_first_enabled_connection(connect)
        if not connection:
            return None

        conn_type = connection.get("type", "rest_api")
        config = connection.get("config", {})
        path = config.get("url", "") or config.get("path", "")

        return build_connection_url(owner_domain, conn_type, path)

    def _get_endpoints_for_health_check(
        self, session: Session
    ) -> list[EndpointHealthInfo]:
        """Query all endpoints with their owner's domain for health checking.

        This method performs a query that joins endpoints with their owners
        (either users or organizations) to get the domain needed for URL building.

        Args:
            session: Database session to use for the query

        Returns:
            List of EndpointHealthInfo objects containing endpoint data and owner domain
        """
        # Query endpoints with user domain (user-owned endpoints)
        # Use != None which SQLAlchemy translates to IS NOT NULL
        user_endpoints_stmt = (
            select(
                EndpointModel.id,
                EndpointModel.is_active,
                EndpointModel.connect,
                UserModel.domain,
            )
            .join(UserModel, EndpointModel.user_id == UserModel.id)
            .where(UserModel.domain != None)  # noqa: E711
        )

        # Query endpoints with organization domain (org-owned endpoints)
        org_endpoints_stmt = (
            select(
                EndpointModel.id,
                EndpointModel.is_active,
                EndpointModel.connect,
                OrganizationModel.domain,
            )
            .join(
                OrganizationModel, EndpointModel.organization_id == OrganizationModel.id
            )
            .where(OrganizationModel.domain != None)  # noqa: E711
        )

        endpoints: list[EndpointHealthInfo] = []

        # Execute user endpoints query
        user_results = session.execute(user_endpoints_stmt).all()
        for row in user_results:
            endpoint_id, is_active, connect, domain = row
            if connect and domain:
                endpoints.append(
                    EndpointHealthInfo(
                        id=endpoint_id,
                        is_active=is_active,
                        connect=connect,
                        owner_domain=domain,
                    )
                )

        # Execute organization endpoints query
        org_results = session.execute(org_endpoints_stmt).all()
        for row in org_results:
            endpoint_id, is_active, connect, domain = row
            if connect and domain:
                endpoints.append(
                    EndpointHealthInfo(
                        id=endpoint_id,
                        is_active=is_active,
                        connect=connect,
                        owner_domain=domain,
                    )
                )

        return endpoints

    async def _check_endpoint_health(
        self,
        endpoint: EndpointHealthInfo,
        semaphore: asyncio.Semaphore,
        client: httpx.AsyncClient,
    ) -> tuple[int, bool, bool]:
        """Check if a single endpoint is healthy.

        Makes an HTTP GET request to the endpoint's connection URL
        to determine if the server is reachable.

        Args:
            endpoint: The endpoint information to check
            semaphore: Semaphore to limit concurrent requests
            client: Async HTTP client to use for the request

        Returns:
            Tuple of (endpoint_id, is_healthy, state_changed)
        """
        async with semaphore:
            url = self._build_health_check_url(endpoint.owner_domain, endpoint.connect)
            if not url:
                # No valid URL to check, don't change status
                return (endpoint.id, endpoint.is_active, False)

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

        This method:
        1. Queries all endpoints with checkable URLs
        2. Checks each endpoint's health concurrently (with semaphore limit)
        3. Updates the is_active status for endpoints whose state changed
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
                    self._check_endpoint_health(endpoint, semaphore, client)
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
