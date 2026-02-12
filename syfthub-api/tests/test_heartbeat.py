"""
Tests for the HeartbeatManager class.

This module tests the heartbeat functionality including:
- Starting and stopping the heartbeat manager
- Retry logic on failure
- Interval calculation based on server response
- Graceful cancellation
- Integration with SyftAPI
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syfthub_api import HeartbeatManager, SyftAPI


class TestHeartbeatManager:
    """Tests for HeartbeatManager class."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock SyftHubClient."""
        client = MagicMock()

        # Mock heartbeat response
        mock_response = MagicMock()
        mock_response.status = "ok"
        mock_response.received_at = datetime.now(timezone.utc)
        mock_response.expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)
        mock_response.domain = "myspace.example.com"
        mock_response.ttl_seconds = 300

        client.users.send_heartbeat.return_value = mock_response
        return client

    @pytest.fixture
    def heartbeat_manager(self, mock_client: MagicMock) -> HeartbeatManager:
        """Create a HeartbeatManager instance for testing."""
        return HeartbeatManager(
            client=mock_client,
            space_url="https://myspace.example.com",
            ttl_seconds=300,
            interval_multiplier=0.8,
            max_retries=3,
            retry_delay_seconds=0.1,  # Short delay for fast tests
        )

    @pytest.mark.asyncio
    async def test_start_and_stop(
        self,
        heartbeat_manager: HeartbeatManager,
        mock_client: MagicMock,
    ) -> None:
        """Test that heartbeat manager can start and stop cleanly."""
        # Start the manager
        await heartbeat_manager.start()

        assert heartbeat_manager.is_running
        assert heartbeat_manager._task is not None

        # Give it time to send at least one heartbeat
        await asyncio.sleep(0.1)

        # Stop the manager
        await heartbeat_manager.stop()

        assert not heartbeat_manager.is_running
        assert heartbeat_manager._task is None

        # Verify heartbeat was sent
        mock_client.users.send_heartbeat.assert_called()

    @pytest.mark.asyncio
    async def test_double_start_raises_error(
        self,
        heartbeat_manager: HeartbeatManager,
    ) -> None:
        """Test that starting twice raises RuntimeError."""
        await heartbeat_manager.start()

        with pytest.raises(RuntimeError, match="already running"):
            await heartbeat_manager.start()

        await heartbeat_manager.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(
        self,
        heartbeat_manager: HeartbeatManager,
    ) -> None:
        """Test that stopping when not running is a no-op."""
        # Should not raise
        await heartbeat_manager.stop()
        await heartbeat_manager.stop()

    @pytest.mark.asyncio
    async def test_first_heartbeat_sent_immediately(
        self,
        heartbeat_manager: HeartbeatManager,
        mock_client: MagicMock,
    ) -> None:
        """Test that first heartbeat is sent immediately on start."""
        await heartbeat_manager.start()

        # Small delay to let the first heartbeat be sent
        await asyncio.sleep(0.05)

        await heartbeat_manager.stop()

        # First heartbeat should have been sent
        assert mock_client.users.send_heartbeat.call_count >= 1

    @pytest.mark.asyncio
    async def test_heartbeat_called_with_correct_params(
        self,
        heartbeat_manager: HeartbeatManager,
        mock_client: MagicMock,
    ) -> None:
        """Test that heartbeat is called with correct URL and TTL."""
        await heartbeat_manager.start()
        await asyncio.sleep(0.05)
        await heartbeat_manager.stop()

        mock_client.users.send_heartbeat.assert_called_with(
            url="https://myspace.example.com",
            ttl_seconds=300,
        )

    @pytest.mark.asyncio
    async def test_retry_on_failure(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that heartbeat retries on failure."""
        # First two calls fail, third succeeds
        mock_response = MagicMock()
        mock_response.ttl_seconds = 300
        mock_client.users.send_heartbeat.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            mock_response,
        ]

        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://myspace.example.com",
            ttl_seconds=300,
            max_retries=3,
            retry_delay_seconds=0.01,  # Very short for tests
        )

        await manager.start()
        await asyncio.sleep(0.1)  # Wait for retries
        await manager.stop()

        # Should have been called 3 times (2 failures + 1 success)
        assert mock_client.users.send_heartbeat.call_count == 3

    @pytest.mark.asyncio
    async def test_interval_from_server_response(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that interval is calculated from server response TTL."""
        # Server returns effective TTL of 600
        mock_response = MagicMock()
        mock_response.ttl_seconds = 600
        mock_client.users.send_heartbeat.return_value = mock_response

        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://myspace.example.com",
            ttl_seconds=300,  # Request 300
            interval_multiplier=0.8,
        )

        # Test internal method
        interval = await manager._send_heartbeat_with_retry()

        # Expected: 600 * 0.8 = 480
        assert interval == 480.0

    @pytest.mark.asyncio
    async def test_send_heartbeat_once(
        self,
        heartbeat_manager: HeartbeatManager,
        mock_client: MagicMock,
    ) -> None:
        """Test send_heartbeat_once method."""
        result = await heartbeat_manager.send_heartbeat_once()

        assert result is True
        mock_client.users.send_heartbeat.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_heartbeat_once_failure(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test send_heartbeat_once returns False on failure."""
        mock_client.users.send_heartbeat.side_effect = Exception("Error")

        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://myspace.example.com",
        )

        result = await manager.send_heartbeat_once()

        assert result is False

    @pytest.mark.asyncio
    async def test_graceful_shutdown_during_sleep(
        self,
        mock_client: MagicMock,
    ) -> None:
        """Test that manager shuts down gracefully when cancelled during sleep."""
        mock_response = MagicMock()
        mock_response.ttl_seconds = 10  # 10 second TTL
        mock_client.users.send_heartbeat.return_value = mock_response

        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://myspace.example.com",
            interval_multiplier=0.8,  # Will sleep for 8 seconds
        )

        await manager.start()
        await asyncio.sleep(0.05)  # Let first heartbeat complete

        # Stop while potentially sleeping
        await manager.stop()

        assert not manager.is_running


class TestHeartbeatManagerConfig:
    """Tests for HeartbeatManager configuration."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        mock_client = MagicMock()
        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://example.com",
        )

        assert manager._ttl_seconds == 300
        assert manager._interval_multiplier == 0.8
        assert manager._max_retries == 3
        assert manager._retry_delay_seconds == 5.0
        assert manager._default_interval == 240.0  # 300 * 0.8

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        mock_client = MagicMock()
        manager = HeartbeatManager(
            client=mock_client,
            space_url="https://example.com",
            ttl_seconds=600,
            interval_multiplier=0.5,
            max_retries=5,
            retry_delay_seconds=10.0,
        )

        assert manager._ttl_seconds == 600
        assert manager._interval_multiplier == 0.5
        assert manager._max_retries == 5
        assert manager._retry_delay_seconds == 10.0
        assert manager._default_interval == 300.0  # 600 * 0.5


class TestSyftAPIHeartbeatIntegration:
    """Tests for heartbeat integration with SyftAPI."""

    @pytest.mark.asyncio
    async def test_heartbeat_starts_after_sync(
        self,
        mock_syfthub_client: MagicMock,
    ) -> None:
        """Test that heartbeat starts after sync when enabled."""
        # Setup heartbeat response
        mock_heartbeat_response = MagicMock()
        mock_heartbeat_response.ttl_seconds = 300
        mock_heartbeat_response.status = "ok"
        mock_heartbeat_response.received_at = datetime.now(timezone.utc)
        mock_heartbeat_response.expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=300
        )
        mock_heartbeat_response.domain = "localhost:8001"
        mock_syfthub_client.users.send_heartbeat.return_value = mock_heartbeat_response

        app = SyftAPI(heartbeat_enabled=True)

        # Run sync
        await app._sync_endpoints()

        assert app._client is not None

        # Start heartbeat
        await app._start_heartbeat()

        assert app._heartbeat_manager is not None
        assert app._heartbeat_manager.is_running

        # Cleanup
        await app._stop_heartbeat()

    @pytest.mark.asyncio
    async def test_heartbeat_disabled(
        self,
        mock_syfthub_client: MagicMock,
    ) -> None:
        """Test that heartbeat doesn't start when disabled."""
        app = SyftAPI(heartbeat_enabled=False)

        await app._sync_endpoints()
        await app._start_heartbeat()

        # Heartbeat manager should not be created
        assert app._heartbeat_manager is None

    @pytest.mark.asyncio
    async def test_heartbeat_config_from_constructor(
        self,
        mock_syfthub_client: MagicMock,
    ) -> None:
        """Test that heartbeat config is passed from constructor."""
        mock_heartbeat_response = MagicMock()
        mock_heartbeat_response.ttl_seconds = 600
        mock_syfthub_client.users.send_heartbeat.return_value = mock_heartbeat_response

        app = SyftAPI(
            heartbeat_enabled=True,
            heartbeat_ttl_seconds=600,
            heartbeat_interval_multiplier=0.5,
        )

        assert app._heartbeat_ttl_seconds == 600
        assert app._heartbeat_interval_multiplier == 0.5

        await app._sync_endpoints()
        await app._start_heartbeat()

        assert app._heartbeat_manager is not None
        assert app._heartbeat_manager._ttl_seconds == 600
        assert app._heartbeat_manager._interval_multiplier == 0.5

        await app._stop_heartbeat()

    @pytest.mark.asyncio
    async def test_heartbeat_stop_is_idempotent(
        self,
        mock_syfthub_client: MagicMock,
    ) -> None:
        """Test that stopping heartbeat multiple times is safe."""
        app = SyftAPI(heartbeat_enabled=False)

        # Should not raise when called multiple times
        await app._stop_heartbeat()
        await app._stop_heartbeat()
        await app._stop_heartbeat()

    @pytest.mark.asyncio
    async def test_heartbeat_not_started_without_client(self) -> None:
        """Test that heartbeat doesn't start if client is not set."""
        app = SyftAPI(heartbeat_enabled=True)

        # Client is None (no sync happened)
        assert app._client is None

        await app._start_heartbeat()

        # Manager should not be created
        assert app._heartbeat_manager is None


class TestHeartbeatConfigFromEnv:
    """Tests for heartbeat configuration from environment variables."""

    def test_heartbeat_enabled_from_env(self) -> None:
        """Test HEARTBEAT_ENABLED environment variable."""
        with patch.dict(
            "os.environ",
            {
                "SYFTHUB_URL": "http://test.example.com",
                "SYFTHUB_USERNAME": "testuser",
                "SYFTHUB_PASSWORD": "testpassword",
                "SPACE_URL": "http://localhost:8001",
                "HEARTBEAT_ENABLED": "false",
            },
        ):
            app = SyftAPI()
            assert app._heartbeat_enabled is False

    def test_heartbeat_ttl_from_env(self) -> None:
        """Test HEARTBEAT_TTL_SECONDS environment variable."""
        with patch.dict(
            "os.environ",
            {
                "SYFTHUB_URL": "http://test.example.com",
                "SYFTHUB_USERNAME": "testuser",
                "SYFTHUB_PASSWORD": "testpassword",
                "SPACE_URL": "http://localhost:8001",
                "HEARTBEAT_TTL_SECONDS": "600",
            },
        ):
            app = SyftAPI()
            assert app._heartbeat_ttl_seconds == 600

    def test_heartbeat_multiplier_from_env(self) -> None:
        """Test HEARTBEAT_INTERVAL_MULTIPLIER environment variable."""
        with patch.dict(
            "os.environ",
            {
                "SYFTHUB_URL": "http://test.example.com",
                "SYFTHUB_USERNAME": "testuser",
                "SYFTHUB_PASSWORD": "testpassword",
                "SPACE_URL": "http://localhost:8001",
                "HEARTBEAT_INTERVAL_MULTIPLIER": "0.5",
            },
        ):
            app = SyftAPI()
            assert app._heartbeat_interval_multiplier == 0.5

    def test_constructor_overrides_env(self) -> None:
        """Test that constructor arguments override environment variables."""
        with patch.dict(
            "os.environ",
            {
                "SYFTHUB_URL": "http://test.example.com",
                "SYFTHUB_USERNAME": "testuser",
                "SYFTHUB_PASSWORD": "testpassword",
                "SPACE_URL": "http://localhost:8001",
                "HEARTBEAT_ENABLED": "true",
                "HEARTBEAT_TTL_SECONDS": "300",
            },
        ):
            app = SyftAPI(
                heartbeat_enabled=False,
                heartbeat_ttl_seconds=600,
            )
            assert app._heartbeat_enabled is False
            assert app._heartbeat_ttl_seconds == 600
