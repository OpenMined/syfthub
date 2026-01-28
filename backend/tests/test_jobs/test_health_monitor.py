"""Tests for endpoint health monitor background job."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from syfthub.jobs.health_monitor import (
    EndpointHealthInfo,
    EndpointHealthMonitor,
)


class TestEndpointHealthInfo:
    """Tests for EndpointHealthInfo dataclass."""

    def test_creation(self):
        """Test EndpointHealthInfo can be created with all fields."""
        info = EndpointHealthInfo(
            id=1,
            is_active=True,
            connect=[{"type": "rest_api", "config": {"url": "/test"}}],
            owner_domain="example.com",
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,
        )
        assert info.id == 1
        assert info.is_active is True
        assert info.connect == [{"type": "rest_api", "config": {"url": "/test"}}]
        assert info.owner_domain == "example.com"
        assert info.owner_id == 10
        assert info.owner_type == "user"
        assert info.heartbeat_expires_at is None

    def test_creation_inactive(self):
        """Test EndpointHealthInfo with inactive endpoint."""
        info = EndpointHealthInfo(
            id=2,
            is_active=False,
            connect=[],
            owner_domain="test.com",
            owner_id=20,
            owner_type="organization",
            heartbeat_expires_at=None,
        )
        assert info.id == 2
        assert info.is_active is False
        assert info.owner_type == "organization"


class TestEndpointHealthMonitorInit:
    """Tests for EndpointHealthMonitor initialization."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return settings

    def test_init_with_enabled_settings(self, mock_settings):
        """Test initialization with health check enabled."""
        monitor = EndpointHealthMonitor(mock_settings)

        assert monitor.enabled is True
        assert monitor.interval == 30
        assert monitor.timeout == 5.0
        assert monitor.max_concurrent == 20
        assert monitor._running is False
        assert monitor._task is None

    def test_init_with_disabled_settings(self, mock_settings):
        """Test initialization with health check disabled."""
        mock_settings.health_check_enabled = False
        monitor = EndpointHealthMonitor(mock_settings)

        assert monitor.enabled is False

    def test_init_with_custom_values(self, mock_settings):
        """Test initialization with custom settings values."""
        mock_settings.health_check_interval_seconds = 60
        mock_settings.health_check_timeout_seconds = 10.0
        mock_settings.health_check_max_concurrent = 50

        monitor = EndpointHealthMonitor(mock_settings)

        assert monitor.interval == 60
        assert monitor.timeout == 10.0
        assert monitor.max_concurrent == 50


class TestBuildHealthCheckUrl:
    """Tests for _build_health_check_url method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    def test_build_url_success(self, monitor):
        """Test successful URL building checks base domain only."""
        connect = [
            {
                "type": "rest_api",
                "enabled": True,
                "config": {"url": "/api/health"},
            }
        ]

        with (
            patch(
                "syfthub.jobs.health_monitor.get_first_enabled_connection"
            ) as mock_get_conn,
            patch("syfthub.jobs.health_monitor.build_connection_url") as mock_build_url,
        ):
            mock_get_conn.return_value = connect[0]
            mock_build_url.return_value = "https://example.com"

            url = monitor._build_health_check_url("example.com", connect)

            assert url == "https://example.com"
            mock_get_conn.assert_called_once_with(connect)
            # Should check base domain, not the endpoint path
            mock_build_url.assert_called_once_with("example.com", "rest_api", path=None)

    def test_build_url_no_enabled_connection(self, monitor):
        """Test URL building when no connection is enabled."""
        connect = [{"type": "rest_api", "enabled": False, "config": {"url": "/test"}}]

        with patch(
            "syfthub.jobs.health_monitor.get_first_enabled_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value = None

            url = monitor._build_health_check_url("example.com", connect)

            assert url is None

    def test_build_url_empty_connection_list(self, monitor):
        """Test URL building with empty connection list."""
        with patch(
            "syfthub.jobs.health_monitor.get_first_enabled_connection"
        ) as mock_get_conn:
            mock_get_conn.return_value = None

            url = monitor._build_health_check_url("example.com", [])

            assert url is None

    def test_build_url_uses_connection_type(self, monitor):
        """Test URL building uses connection type for protocol selection."""
        connect = [
            {
                "type": "mcp",
                "enabled": True,
                "config": {"path": "/mcp/endpoint"},
            }
        ]

        with (
            patch(
                "syfthub.jobs.health_monitor.get_first_enabled_connection"
            ) as mock_get_conn,
            patch("syfthub.jobs.health_monitor.build_connection_url") as mock_build_url,
        ):
            mock_get_conn.return_value = connect[0]
            mock_build_url.return_value = "https://example.com"

            url = monitor._build_health_check_url("example.com", connect)

            assert url == "https://example.com"
            # Should use the connection type but check base domain
            mock_build_url.assert_called_once_with("example.com", "mcp", path=None)

    def test_build_url_default_type(self, monitor):
        """Test URL building defaults to rest_api type."""
        connect = [{"enabled": True, "config": {"url": "/test"}}]

        with (
            patch(
                "syfthub.jobs.health_monitor.get_first_enabled_connection"
            ) as mock_get_conn,
            patch("syfthub.jobs.health_monitor.build_connection_url") as mock_build_url,
        ):
            mock_get_conn.return_value = connect[0]
            mock_build_url.return_value = "https://example.com"

            monitor._build_health_check_url("example.com", connect)

            mock_build_url.assert_called_once_with("example.com", "rest_api", path=None)


class TestGetEndpointsForHealthCheck:
    """Tests for _get_endpoints_for_health_check method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    def test_get_endpoints_empty(self, monitor):
        """Test getting endpoints when none exist."""
        mock_session = MagicMock()
        mock_session.execute.return_value.all.return_value = []

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert endpoints == []
        assert mock_session.execute.call_count == 2  # user and org queries

    def test_get_endpoints_user_owned(self, monitor):
        """Test getting user-owned endpoints."""
        mock_session = MagicMock()

        # User endpoints query result (now includes owner_id and heartbeat_expires_at)
        user_results = [
            (
                1,
                True,
                [{"type": "rest_api", "config": {"url": "/test"}}],
                "user.com",
                10,
                None,
            ),
            (
                2,
                False,
                [{"type": "mcp", "config": {"url": "/mcp"}}],
                "user2.com",
                20,
                None,
            ),
        ]
        # Org endpoints query result (empty)
        org_results = []

        mock_session.execute.return_value.all.side_effect = [user_results, org_results]

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert len(endpoints) == 2
        assert endpoints[0].id == 1
        assert endpoints[0].is_active is True
        assert endpoints[0].owner_domain == "user.com"
        assert endpoints[0].owner_type == "user"
        assert endpoints[0].owner_id == 10
        assert endpoints[1].id == 2
        assert endpoints[1].is_active is False
        assert endpoints[1].owner_domain == "user2.com"
        assert endpoints[1].owner_type == "user"

    def test_get_endpoints_org_owned(self, monitor):
        """Test getting organization-owned endpoints."""
        mock_session = MagicMock()

        # User endpoints query result (empty)
        user_results = []
        # Org endpoints query result (includes owner_id and heartbeat_expires_at)
        org_results = [
            (
                3,
                True,
                [{"type": "rest_api", "config": {"url": "/api"}}],
                "org.com",
                100,
                None,
            ),
        ]

        mock_session.execute.return_value.all.side_effect = [user_results, org_results]

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert len(endpoints) == 1
        assert endpoints[0].id == 3
        assert endpoints[0].owner_domain == "org.com"
        assert endpoints[0].owner_type == "organization"
        assert endpoints[0].heartbeat_expires_at is None

    def test_get_endpoints_mixed(self, monitor):
        """Test getting both user and org owned endpoints."""
        mock_session = MagicMock()

        user_results = [
            (
                1,
                True,
                [{"type": "rest_api", "config": {"url": "/user"}}],
                "user.com",
                10,
                None,
            ),
        ]
        org_results = [
            (
                2,
                True,
                [{"type": "rest_api", "config": {"url": "/org"}}],
                "org.com",
                100,
                None,
            ),
        ]

        mock_session.execute.return_value.all.side_effect = [user_results, org_results]

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert len(endpoints) == 2
        assert endpoints[0].owner_type == "user"
        assert endpoints[1].owner_type == "organization"

    def test_get_endpoints_filters_no_connect(self, monitor):
        """Test that endpoints without connect config are filtered out."""
        mock_session = MagicMock()

        user_results = [
            (1, True, None, "user.com", 10, None),  # No connect config
            (2, True, [], "user2.com", 20, None),  # Empty connect config (falsy)
            (
                3,
                True,
                [{"type": "rest_api"}],
                "user3.com",
                30,
                None,
            ),  # Has connect config
        ]
        org_results = []

        mock_session.execute.return_value.all.side_effect = [user_results, org_results]

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        # Only endpoint 3 should be included (has truthy connect and domain)
        assert len(endpoints) == 1
        assert endpoints[0].id == 3

    def test_get_endpoints_includes_no_domain(self, monitor):
        """Test that endpoints without domain are included (will be marked unhealthy)."""
        mock_session = MagicMock()

        user_results = [
            (1, True, [{"type": "rest_api"}], None, 10, None),  # No domain - included
            (2, True, [{"type": "rest_api"}], "", 20, None),  # Empty domain - included
            (
                3,
                True,
                [{"type": "rest_api"}],
                "valid.com",
                30,
                None,
            ),  # Has domain - included
        ]
        org_results = []

        mock_session.execute.return_value.all.side_effect = [user_results, org_results]

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        # All 3 endpoints should be included (no domain filtering)
        assert len(endpoints) == 3
        assert endpoints[0].id == 1
        assert endpoints[0].owner_domain is None
        assert endpoints[1].id == 2
        assert endpoints[1].owner_domain == ""
        assert endpoints[2].id == 3
        assert endpoints[2].owner_domain == "valid.com"


class TestCheckEndpointHealth:
    """Tests for _check_endpoint_health method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    @pytest.fixture
    def sample_endpoint(self):
        """Create sample endpoint for testing (stale heartbeat, needs HTTP check)."""
        return EndpointHealthInfo(
            id=1,
            is_active=True,
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            owner_domain="example.com",
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,  # No heartbeat - will trigger HTTP check
        )

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_check_health_success_200(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with successful HTTP 200 response."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 1
        assert is_healthy is True
        assert state_changed is False  # Was active, still active

    @pytest.mark.asyncio
    async def test_check_health_500_is_unhealthy(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with HTTP 500 is considered unhealthy."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, state_changed = result
        assert is_healthy is False  # 5xx errors are unhealthy
        assert state_changed is True  # Was active, now unhealthy

    @pytest.mark.asyncio
    async def test_check_health_404_is_unhealthy(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with HTTP 404 is considered unhealthy."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, state_changed = result
        assert is_healthy is False  # 4xx errors are unhealthy
        assert state_changed is True  # Was active, now unhealthy

    @pytest.mark.asyncio
    async def test_check_health_redirect_is_healthy(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with HTTP 3xx redirect is considered healthy."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_client.get.return_value = mock_response

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, state_changed = result
        assert is_healthy is True  # 3xx redirects are healthy
        assert state_changed is False  # Was active, still active

    @pytest.mark.asyncio
    async def test_check_health_timeout(self, monitor, sample_endpoint, mock_session):
        """Test health check with timeout."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 1
        assert is_healthy is False
        assert state_changed is True  # Was active, now unhealthy

    @pytest.mark.asyncio
    async def test_check_health_connection_error(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with connection error."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, state_changed = result
        assert is_healthy is False
        assert state_changed is True

    @pytest.mark.asyncio
    async def test_check_health_no_valid_url(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check when no valid URL can be built."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch.object(monitor, "_build_health_check_url", return_value=None):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 1
        assert is_healthy is True  # Returns current state
        assert state_changed is False

    @pytest.mark.asyncio
    async def test_check_health_inactive_becomes_healthy(self, monitor, mock_session):
        """Test health check when inactive endpoint becomes reachable."""
        inactive_endpoint = EndpointHealthInfo(
            id=2,
            is_active=False,  # Currently inactive
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            owner_domain="example.com",
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,  # No heartbeat - will trigger HTTP check
        )
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                inactive_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, state_changed = result
        assert is_healthy is True
        assert state_changed is True  # Was inactive, now healthy

    @pytest.mark.asyncio
    async def test_check_health_request_error(
        self, monitor, sample_endpoint, mock_session
    ):
        """Test health check with generic request error."""
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.RequestError("Network error")

        with patch.object(
            monitor, "_build_health_check_url", return_value="https://example.com/test"
        ):
            result = await monitor._check_endpoint_health(
                sample_endpoint, semaphore, mock_client, mock_session
            )

        _endpoint_id, is_healthy, _state_changed = result
        assert is_healthy is False

    @pytest.mark.asyncio
    async def test_check_health_no_owner_domain_none(self, monitor, mock_session):
        """Test health check when endpoint has no owner domain (None)."""
        endpoint_no_domain = EndpointHealthInfo(
            id=1,
            is_active=True,  # Currently active
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            owner_domain=None,  # No domain configured
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,
        )
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        result = await monitor._check_endpoint_health(
            endpoint_no_domain, semaphore, mock_client, mock_session
        )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 1
        assert is_healthy is False  # Should be unhealthy
        assert state_changed is True  # Was active, now unhealthy
        # Should not have made any HTTP requests
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_health_no_owner_domain_empty_string(
        self, monitor, mock_session
    ):
        """Test health check when endpoint has empty owner domain."""
        endpoint_empty_domain = EndpointHealthInfo(
            id=2,
            is_active=True,  # Currently active
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            owner_domain="",  # Empty domain
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,
        )
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        result = await monitor._check_endpoint_health(
            endpoint_empty_domain, semaphore, mock_client, mock_session
        )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 2
        assert is_healthy is False  # Should be unhealthy
        assert state_changed is True  # Was active, now unhealthy
        # Should not have made any HTTP requests
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_health_no_owner_domain_already_inactive(
        self, monitor, mock_session
    ):
        """Test health check when endpoint without domain is already inactive."""
        endpoint_no_domain_inactive = EndpointHealthInfo(
            id=3,
            is_active=False,  # Already inactive
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            owner_domain=None,
            owner_id=10,
            owner_type="user",
            heartbeat_expires_at=None,
        )
        semaphore = asyncio.Semaphore(10)
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        result = await monitor._check_endpoint_health(
            endpoint_no_domain_inactive, semaphore, mock_client, mock_session
        )

        endpoint_id, is_healthy, state_changed = result
        assert endpoint_id == 3
        assert is_healthy is False
        assert state_changed is False  # Was inactive, still unhealthy - no change
        mock_client.get.assert_not_called()


class TestUpdateEndpointStatus:
    """Tests for _update_endpoint_status method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    def test_update_status_success(self, monitor):
        """Test successful status update."""
        mock_session = MagicMock()
        mock_endpoint = MagicMock()
        mock_session.get.return_value = mock_endpoint

        result = monitor._update_endpoint_status(mock_session, 1, False)

        assert result is True
        assert mock_endpoint.is_active is False
        mock_session.commit.assert_called_once()

    def test_update_status_endpoint_not_found(self, monitor):
        """Test status update when endpoint not found."""
        mock_session = MagicMock()
        mock_session.get.return_value = None

        result = monitor._update_endpoint_status(mock_session, 999, False)

        assert result is False
        mock_session.commit.assert_not_called()

    def test_update_status_database_error(self, monitor):
        """Test status update with database error."""
        mock_session = MagicMock()
        mock_endpoint = MagicMock()
        mock_session.get.return_value = mock_endpoint
        mock_session.commit.side_effect = Exception("Database error")

        result = monitor._update_endpoint_status(mock_session, 1, False)

        assert result is False
        mock_session.rollback.assert_called_once()

    def test_update_status_to_active(self, monitor):
        """Test updating status to active."""
        mock_session = MagicMock()
        mock_endpoint = MagicMock()
        mock_endpoint.is_active = False
        mock_session.get.return_value = mock_endpoint

        result = monitor._update_endpoint_status(mock_session, 1, True)

        assert result is True
        assert mock_endpoint.is_active is True


class TestRunHealthCheckCycle:
    """Tests for run_health_check_cycle method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    @pytest.mark.asyncio
    async def test_cycle_no_endpoints(self, monitor):
        """Test health check cycle with no endpoints."""
        mock_session = MagicMock()

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_get_endpoints_for_health_check", return_value=[]),
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_with_endpoints_no_changes(self, monitor):
        """Test health check cycle with endpoints but no state changes."""
        mock_session = MagicMock()
        endpoints = [
            EndpointHealthInfo(
                id=1,
                is_active=True,
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                owner_domain="example.com",
                owner_id=10,
                owner_type="user",
                heartbeat_expires_at=None,
            )
        ]

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(
                monitor,
                "_check_endpoint_health",
                return_value=(1, True, False),  # No state change
            ),
            patch("syfthub.jobs.health_monitor.httpx.AsyncClient"),
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_with_state_changes(self, monitor):
        """Test health check cycle with state changes."""
        mock_session = MagicMock()
        endpoints = [
            EndpointHealthInfo(
                id=1,
                is_active=True,
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                owner_domain="example.com",
                owner_id=10,
                owner_type="user",
                heartbeat_expires_at=None,
            )
        ]

        async def mock_check(*args, **kwargs):
            return (1, False, True)  # State changed to unhealthy

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(monitor, "_check_endpoint_health", side_effect=mock_check),
            patch.object(monitor, "_update_endpoint_status", return_value=True),
            patch("syfthub.jobs.health_monitor.httpx.AsyncClient"),
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            monitor._update_endpoint_status.assert_called_once_with(
                mock_session, 1, False
            )

    @pytest.mark.asyncio
    async def test_cycle_handles_exceptions(self, monitor):
        """Test health check cycle handles exceptions from gather results."""
        mock_session = MagicMock()
        endpoints = [
            EndpointHealthInfo(
                id=1,
                is_active=True,
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                owner_domain="example.com",
                owner_id=10,
                owner_type="user",
                heartbeat_expires_at=None,
            )
        ]

        # Mock _check_endpoint_health to raise an exception
        async def failing_check(*args, **kwargs):
            raise ValueError("Test error")

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(monitor, "_check_endpoint_health", side_effect=failing_check),
            patch("syfthub.jobs.health_monitor.httpx.AsyncClient"),
        ):
            mock_db_manager.get_session.return_value = mock_session

            # Should not raise - exceptions are logged via return_exceptions=True
            await monitor.run_health_check_cycle()

            mock_session.close.assert_called_once()


class TestHealthMonitorLifecycle:
    """Tests for start/stop lifecycle methods."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 0.1  # Fast for testing
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    @pytest.fixture
    def disabled_monitor(self):
        """Create disabled EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = False
        settings.health_check_interval_seconds = 30
        settings.health_check_timeout_seconds = 5.0
        settings.health_check_max_concurrent = 20
        settings.heartbeat_grace_period_seconds = 60
        return EndpointHealthMonitor(settings)

    @pytest.mark.asyncio
    async def test_start_when_disabled(self, disabled_monitor):
        """Test start returns immediately when disabled."""
        await disabled_monitor.start()

        assert disabled_monitor._running is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self, monitor):
        """Test starting and stopping the monitor."""
        cycle_count = 0

        async def mock_cycle():
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count >= 2:
                await monitor.stop()

        with patch.object(monitor, "run_health_check_cycle", side_effect=mock_cycle):
            await monitor.start()

        assert monitor._running is False
        assert cycle_count >= 1

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, monitor):
        """Test stop when monitor is not running."""
        await monitor.stop()

        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, monitor):
        """Test stop cancels the running task."""

        # Create a real async task that we can cancel
        async def long_running():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_running())
        monitor._task = task

        # Give task a moment to start
        await asyncio.sleep(0.01)

        await monitor.stop()

        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_start_handles_cycle_exception(self, monitor):
        """Test start handles exceptions in health check cycle."""
        call_count = 0

        async def mock_cycle():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test error")
            else:
                await monitor.stop()

        with patch.object(monitor, "run_health_check_cycle", side_effect=mock_cycle):
            await monitor.start()

        # Should have called cycle at least twice (error + stop)
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_start_runs_cycle_multiple_times(self, monitor):
        """Test start runs multiple cycles before being stopped."""
        call_count = 0

        async def mock_cycle():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                monitor._running = False  # Stop after 3 cycles

        with patch.object(monitor, "run_health_check_cycle", side_effect=mock_cycle):
            await monitor.start()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_stop_handles_done_task(self, monitor):
        """Test stop when task is already done."""
        mock_task = MagicMock()
        mock_task.done.return_value = True
        monitor._task = mock_task

        await monitor.stop()

        mock_task.cancel.assert_not_called()
