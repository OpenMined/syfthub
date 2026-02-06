"""
Tests for endpoint synchronization with SyftHub.

This module tests the _sync_endpoints() method using mocked SyftHub client.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from syfthub_api import (
    AuthenticationError,
    Document,
    SyftAPI,
    SyncError,
)


class TestSyncEndpoints:
    """Tests for the _sync_endpoints method."""

    @pytest.mark.asyncio
    async def test_sync_authenticates_with_syfthub(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that sync authenticates with SyftHub."""
        app._skip_sync = False

        @app.datasource(slug="test", name="Test", description="Test endpoint")
        async def test_fn(query: str) -> list[Document]:
            return []

        await app._sync_endpoints()

        # Verify login was called with correct credentials
        mock_syfthub_client.auth.login.assert_called_once_with(
            username="testuser", password="testpassword"
        )

    @pytest.mark.asyncio
    async def test_sync_updates_user_domain(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that sync updates user domain to space URL."""
        app._skip_sync = False

        @app.datasource(slug="test", name="Test", description="Test endpoint")
        async def test_fn(query: str) -> list[Document]:
            return []

        await app._sync_endpoints()

        # Verify domain was updated
        mock_syfthub_client.users.update.assert_called_once_with(domain="http://localhost:8001")

    @pytest.mark.asyncio
    async def test_sync_sends_endpoints_to_syfthub(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that sync sends endpoint definitions to SyftHub."""
        app._skip_sync = False

        @app.datasource(slug="my-data", name="My Data", description="Data source")
        async def data_fn(query: str) -> list[Document]:
            return []

        await app._sync_endpoints()

        # Verify sync was called with endpoint data
        mock_syfthub_client.my_endpoints.sync.assert_called_once()
        call_args = mock_syfthub_client.my_endpoints.sync.call_args
        endpoints = call_args.kwargs["endpoints"]

        assert len(endpoints) == 1
        assert endpoints[0]["slug"] == "my-data"
        assert endpoints[0]["name"] == "My Data"
        assert endpoints[0]["type"] == "data_source"
        assert endpoints[0]["description"] == "Data source"

    @pytest.mark.asyncio
    async def test_sync_multiple_endpoints(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test syncing multiple endpoints."""
        app._skip_sync = False

        @app.datasource(slug="ds1", name="DS1", description="First")
        async def ds1(query: str) -> list[Document]:
            return []

        @app.model(slug="model1", name="Model1", description="Second")
        async def model1(messages: list) -> str:
            return ""

        await app._sync_endpoints()

        call_args = mock_syfthub_client.my_endpoints.sync.call_args
        endpoints = call_args.kwargs["endpoints"]

        assert len(endpoints) == 2
        assert endpoints[0]["type"] == "data_source"
        assert endpoints[1]["type"] == "model"

    @pytest.mark.asyncio
    async def test_sync_no_endpoints_skips_sync_call(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that sync with no endpoints skips the sync API call."""
        app._skip_sync = False

        await app._sync_endpoints()

        # Auth should still happen
        mock_syfthub_client.auth.login.assert_called_once()
        # But sync should not be called when there are no endpoints
        mock_syfthub_client.my_endpoints.sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_auth_failure_raises_authentication_error(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that authentication failure raises AuthenticationError."""
        app._skip_sync = False
        mock_syfthub_client.auth.login.side_effect = Exception("Invalid credentials")

        @app.datasource(slug="test", name="Test", description="Test")
        async def test_fn(query: str) -> list[Document]:
            return []

        with pytest.raises(AuthenticationError, match="Failed to authenticate"):
            await app._sync_endpoints()

    @pytest.mark.asyncio
    async def test_sync_failure_raises_sync_error(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that sync failure raises SyncError."""
        app._skip_sync = False
        mock_syfthub_client.my_endpoints.sync.side_effect = Exception("Sync failed")

        @app.datasource(slug="test", name="Test", description="Test")
        async def test_fn(query: str) -> list[Document]:
            return []

        with pytest.raises(SyncError, match="Failed to sync endpoints"):
            await app._sync_endpoints()

    @pytest.mark.asyncio
    async def test_sync_preserves_original_exception_as_cause(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that original exception is preserved as cause."""
        app._skip_sync = False
        original_error = ValueError("Original error")
        mock_syfthub_client.auth.login.side_effect = original_error

        @app.datasource(slug="test", name="Test", description="Test")
        async def test_fn(query: str) -> list[Document]:
            return []

        with pytest.raises(AuthenticationError) as exc_info:
            await app._sync_endpoints()

        assert exc_info.value.cause is original_error


class TestRunMethod:
    """Tests for the run() method."""

    @pytest.mark.asyncio
    async def test_run_skips_sync_when_flag_set(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that run() skips sync when _skip_sync is True."""
        app._skip_sync = True

        # Mock uvicorn to avoid actually starting the server
        with patch("syfthub_api.app.uvicorn") as mock_uvicorn:
            mock_server = AsyncMock()
            mock_uvicorn.Server.return_value = mock_server

            # Create a task that we can cancel
            import asyncio

            async def run_with_timeout() -> None:
                try:
                    await asyncio.wait_for(app.run(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

            await run_with_timeout()

            # Sync should not have been called
            mock_syfthub_client.auth.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_calls_sync_when_flag_not_set(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that run() calls sync when _skip_sync is False."""
        app._skip_sync = False

        @app.datasource(slug="test", name="Test", description="Test")
        async def test_fn(query: str) -> list[Document]:
            return []

        # Mock uvicorn to avoid actually starting the server
        with patch("syfthub_api.app.uvicorn") as mock_uvicorn:
            mock_server = AsyncMock()
            mock_uvicorn.Server.return_value = mock_server

            import asyncio

            async def run_with_timeout() -> None:
                try:
                    await asyncio.wait_for(app.run(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

            await run_with_timeout()

            # Sync should have been called
            mock_syfthub_client.auth.login.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_uses_custom_host_and_port(
        self, app: SyftAPI, mock_syfthub_client: MagicMock
    ) -> None:
        """Test that run() uses custom host and port."""
        app._skip_sync = True

        with patch("syfthub_api.app.uvicorn") as mock_uvicorn:
            mock_server = AsyncMock()
            mock_uvicorn.Server.return_value = mock_server

            import asyncio

            async def run_with_timeout() -> None:
                try:
                    await asyncio.wait_for(app.run(host="127.0.0.1", port=9000), timeout=0.1)
                except asyncio.TimeoutError:
                    pass

            await run_with_timeout()

            # Check uvicorn.Config was called with correct args
            mock_uvicorn.Config.assert_called_once()
            call_args = mock_uvicorn.Config.call_args
            assert call_args.kwargs["host"] == "127.0.0.1"
            assert call_args.kwargs["port"] == 9000
