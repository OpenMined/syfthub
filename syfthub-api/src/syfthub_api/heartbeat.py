"""
Heartbeat manager for SyftAI Spaces.

This module provides the HeartbeatManager class that handles periodic heartbeat
requests to SyftHub, signaling that this space is alive and available.

Example:
    from syfthub_sdk import SyftHubClient
    from syfthub_api.heartbeat import HeartbeatManager

    client = SyftHubClient(base_url="https://hub.syft.com")
    client.auth.login(username="user", password="pass")

    manager = HeartbeatManager(
        client=client,
        space_url="https://myspace.example.com",
        ttl_seconds=300,
    )

    await manager.start()  # Starts background heartbeat loop
    # ... app runs ...
    await manager.stop()   # Graceful shutdown
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from syfthub_sdk import SyftHubClient

logger = logging.getLogger(__name__)


class HeartbeatManager:
    """
    Manages periodic heartbeat requests to SyftHub.

    The heartbeat mechanism allows SyftAI Spaces to signal their availability
    to SyftHub. The manager sends heartbeats at regular intervals (based on
    the server-returned TTL) and handles retries on failure.

    Attributes:
        client: Authenticated SyftHubClient instance.
        space_url: Full URL of this SyftAI Space.
        ttl_seconds: Requested TTL for heartbeats (server may cap this).
        interval_multiplier: Send heartbeat at TTL * multiplier (e.g., 0.8 = 80%).
        max_retries: Maximum retry attempts on failure.
        retry_delay_seconds: Initial delay between retries (exponential backoff).

    Example:
        manager = HeartbeatManager(
            client=authenticated_client,
            space_url="https://myspace.example.com",
        )
        await manager.start()
    """

    def __init__(
        self,
        client: SyftHubClient,
        space_url: str,
        ttl_seconds: int = 300,
        interval_multiplier: float = 0.8,
        max_retries: int = 3,
        retry_delay_seconds: float = 5.0,
    ) -> None:
        """
        Initialize the HeartbeatManager.

        Args:
            client: Authenticated SyftHubClient instance.
            space_url: Full URL of this SyftAI Space (e.g., "https://myspace.example.com").
            ttl_seconds: Requested TTL in seconds (1-3600, server caps at 600).
            interval_multiplier: Send heartbeat at TTL * multiplier. Default 0.8 means
                               send at 80% of TTL (e.g., every 240s for 300s TTL).
            max_retries: Maximum retry attempts on failure before giving up.
            retry_delay_seconds: Initial delay between retries (uses exponential backoff).
        """
        self._client = client
        self._space_url = space_url
        self._ttl_seconds = ttl_seconds
        self._interval_multiplier = interval_multiplier
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._default_interval = ttl_seconds * interval_multiplier

    @property
    def is_running(self) -> bool:
        """Check if the heartbeat loop is currently running."""
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """
        Start the heartbeat background task.

        This method starts a background asyncio task that periodically sends
        heartbeats to SyftHub. The first heartbeat is sent immediately.

        Raises:
            RuntimeError: If the heartbeat manager is already running.
        """
        if self.is_running:
            raise RuntimeError("HeartbeatManager is already running")

        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            f"Heartbeat manager started (TTL={self._ttl_seconds}s, "
            f"interval={self._default_interval:.0f}s)"
        )

    async def stop(self) -> None:
        """
        Stop the heartbeat background task gracefully.

        This method signals the heartbeat loop to stop and waits for it to
        complete. Any in-progress sleep will be cancelled.
        """
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Heartbeat manager stopped")

    async def _heartbeat_loop(self) -> None:
        """
        Main loop that sends heartbeats periodically.

        The loop sends an initial heartbeat immediately, then sleeps for
        the calculated interval before sending the next one. The interval
        is dynamically adjusted based on the server's response.
        """
        # Send first heartbeat immediately
        interval = await self._send_heartbeat_with_retry()

        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                interval = await self._send_heartbeat_with_retry()
            except asyncio.CancelledError:
                logger.debug("Heartbeat loop cancelled")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in heartbeat loop: {e}")
                # Continue with default interval on unexpected errors
                interval = self._default_interval

    async def _send_heartbeat_with_retry(self) -> float:
        """
        Send a heartbeat with retry logic and return the next interval.

        This method attempts to send a heartbeat, retrying with exponential
        backoff on failure. If all retries fail, it logs an error and returns
        the default interval.

        Returns:
            The next sleep interval in seconds, calculated from the server's
            response TTL or the default if the request failed.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = await asyncio.to_thread(
                    self._client.users.send_heartbeat,
                    url=self._space_url,
                    ttl_seconds=self._ttl_seconds,
                )

                # Calculate next interval from server's effective TTL
                effective_ttl = response.ttl_seconds
                next_interval = effective_ttl * self._interval_multiplier

                logger.debug(
                    f"Heartbeat sent successfully (domain={response.domain}, "
                    f"expires_at={response.expires_at}, next_interval={next_interval:.0f}s)"
                )
                return next_interval

            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._retry_delay_seconds * (2**attempt)
                    logger.warning(
                        f"Heartbeat failed (attempt {attempt + 1}/{self._max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        logger.error(
            f"Heartbeat failed after {self._max_retries} attempts: {last_error}. "
            f"Will retry in {self._default_interval:.0f}s"
        )
        return self._default_interval

    async def send_heartbeat_once(self) -> bool:
        """
        Send a single heartbeat without starting the background loop.

        This is useful for testing or when you need to manually trigger
        a heartbeat outside of the automatic loop.

        Returns:
            True if the heartbeat was sent successfully, False otherwise.
        """
        try:
            await asyncio.to_thread(
                self._client.users.send_heartbeat,
                url=self._space_url,
                ttl_seconds=self._ttl_seconds,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False
