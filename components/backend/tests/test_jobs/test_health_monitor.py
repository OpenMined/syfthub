"""Tests for endpoint health monitor background job."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from syfthub.jobs.health_monitor import (
    HEALTH_MONITOR_LOCK_ID,
    EndpointHealthInfo,
    EndpointHealthMonitor,
)


class TestEndpointHealthInfo:
    """Tests for EndpointHealthInfo dataclass."""

    def test_creation(self):
        """Test EndpointHealthInfo can be created with all fields."""
        info = EndpointHealthInfo(
            id=1,
            slug="test-endpoint",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api", "config": {"url": "/test"}}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
        )
        assert info.id == 1
        assert info.slug == "test-endpoint"
        assert info.endpoint_type == "model"
        assert info.is_active is True
        assert info.connect == [{"type": "rest_api", "config": {"url": "/test"}}]
        assert info.base_url == "https://example.com"
        assert info.owner_id == 10
        assert info.owner_type == "user"
        assert info.health_status is None
        assert info.health_checked_at is None
        assert info.health_ttl_seconds is None

    def test_creation_inactive(self):
        """Test EndpointHealthInfo with inactive endpoint."""
        info = EndpointHealthInfo(
            id=2,
            slug="inactive-endpoint",
            endpoint_type="data_source",
            is_active=False,
            connect=[],
            base_url="https://test.com",
            owner_id=20,
            owner_type="user",
        )
        assert info.id == 2
        assert info.slug == "inactive-endpoint"
        assert info.endpoint_type == "data_source"
        assert info.is_active is False
        assert info.owner_type == "user"

    def test_creation_with_health_fields(self):
        """Test EndpointHealthInfo with per-endpoint health fields."""
        now = datetime.now(timezone.utc)
        info = EndpointHealthInfo(
            id=3,
            slug="healthy-endpoint",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=now,
            health_ttl_seconds=300,
        )
        assert info.health_status == "healthy"
        assert info.health_checked_at == now
        assert info.health_ttl_seconds == 300


class TestEndpointHealthMonitorInit:
    """Tests for EndpointHealthMonitor initialization."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return settings

    def test_init_with_enabled_settings(self, mock_settings):
        """Test initialization with health check enabled."""
        monitor = EndpointHealthMonitor(mock_settings)

        assert monitor.enabled is True
        assert monitor.interval == 30
        assert monitor.failure_threshold == 3
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
        mock_settings.health_check_failure_threshold = 5

        monitor = EndpointHealthMonitor(mock_settings)

        assert monitor.interval == 60
        assert monitor.failure_threshold == 5


class TestTryAcquireCycleLock:
    """Tests for _try_acquire_cycle_lock advisory lock method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    def test_lock_acquired_on_postgresql(self, monitor):
        """Test lock is acquired when pg_try_advisory_lock returns True."""
        mock_session = MagicMock()
        mock_session.bind.dialect.name = "postgresql"
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        assert monitor._try_acquire_cycle_lock(mock_session) is True
        mock_session.execute.assert_called_once()

    def test_lock_not_acquired_on_postgresql(self, monitor):
        """Test lock not acquired when another worker holds it."""
        mock_session = MagicMock()
        mock_session.bind.dialect.name = "postgresql"
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute.return_value = mock_result

        assert monitor._try_acquire_cycle_lock(mock_session) is False

    def test_lock_skipped_on_sqlite(self, monitor):
        """Test lock is always acquired (skipped) on SQLite."""
        mock_session = MagicMock()
        mock_session.bind.dialect.name = "sqlite"

        assert monitor._try_acquire_cycle_lock(mock_session) is True
        mock_session.execute.assert_not_called()

    def test_lock_skipped_when_no_bind(self, monitor):
        """Test lock is not acquired when session has no bind."""
        mock_session = MagicMock()
        mock_session.bind = None

        assert monitor._try_acquire_cycle_lock(mock_session) is True

    def test_lock_uses_correct_lock_id(self, monitor):
        """Test that the correct advisory lock ID is used."""
        mock_session = MagicMock()
        mock_session.bind.dialect.name = "postgresql"
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        monitor._try_acquire_cycle_lock(mock_session)

        call_args = mock_session.execute.call_args
        params = call_args[0][1]
        assert params["lock_id"] == HEALTH_MONITOR_LOCK_ID

    def test_lock_returns_false_on_exception(self, monitor):
        """Test lock returns False when database query fails."""
        mock_session = MagicMock()
        mock_session.bind.dialect.name = "postgresql"
        mock_session.execute.side_effect = Exception("Connection lost")

        assert monitor._try_acquire_cycle_lock(mock_session) is False


class TestGetEndpointsForHealthCheck:
    """Tests for _get_endpoints_for_health_check method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    def test_get_endpoints_empty(self, monitor):
        """Test getting endpoints when none exist."""
        mock_session = MagicMock()
        mock_session.execute.return_value.all.return_value = []

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert endpoints == []
        assert mock_session.execute.call_count == 1  # single user query

    def test_get_endpoints_user_owned(self, monitor):
        """Test getting user-owned endpoints."""
        mock_session = MagicMock()

        # 10-column tuple: id, slug, type, is_active, connect, domain, owner_id,
        # health_status, health_checked_at, health_ttl_seconds
        user_results = [
            (
                1,
                "endpoint-1",
                "model",
                True,
                [{"type": "rest_api", "config": {"url": "/test"}}],
                "https://user.com",
                10,
                None,
                None,
                None,
            ),
            (
                2,
                "endpoint-2",
                "data_source",
                False,
                [{"type": "mcp", "config": {"url": "/mcp"}}],
                "https://user2.com",
                20,
                "healthy",
                datetime.now(timezone.utc),
                300,
            ),
        ]

        mock_session.execute.return_value.all.return_value = user_results

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        assert len(endpoints) == 2
        assert endpoints[0].id == 1
        assert endpoints[0].slug == "endpoint-1"
        assert endpoints[0].endpoint_type == "model"
        assert endpoints[0].is_active is True
        assert endpoints[0].base_url == "https://user.com"
        assert endpoints[0].owner_type == "user"
        assert endpoints[0].owner_id == 10
        assert endpoints[0].health_status is None
        assert endpoints[1].id == 2
        assert endpoints[1].health_status == "healthy"
        assert endpoints[1].health_ttl_seconds == 300

    def test_get_endpoints_filters_no_connect(self, monitor):
        """Test that endpoints without connect config are filtered out."""
        mock_session = MagicMock()

        user_results = [
            # No connect config
            (
                1,
                "ep-1",
                "model",
                True,
                None,
                "https://user.com",
                10,
                None,
                None,
                None,
            ),
            # Empty connect config (falsy)
            (
                2,
                "ep-2",
                "model",
                True,
                [],
                "https://user2.com",
                20,
                None,
                None,
                None,
            ),
            # Has connect config
            (
                3,
                "ep-3",
                "model",
                True,
                [{"type": "rest_api"}],
                "https://user3.com",
                30,
                None,
                None,
                None,
            ),
        ]

        mock_session.execute.return_value.all.return_value = user_results

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        # Only endpoint 3 should be included (has truthy connect and domain)
        assert len(endpoints) == 1
        assert endpoints[0].id == 3

    def test_get_endpoints_includes_no_domain(self, monitor):
        """Test that endpoints without domain are included (will be marked unhealthy)."""
        mock_session = MagicMock()

        user_results = [
            # No domain - included
            (
                1,
                "ep-1",
                "model",
                True,
                [{"type": "rest_api"}],
                None,
                10,
                None,
                None,
                None,
            ),
            # Empty domain - included
            (
                2,
                "ep-2",
                "model",
                True,
                [{"type": "rest_api"}],
                "",
                20,
                None,
                None,
                None,
            ),
            # Has domain - included
            (
                3,
                "ep-3",
                "model",
                True,
                [{"type": "rest_api"}],
                "https://valid.com",
                30,
                None,
                None,
                None,
            ),
        ]

        mock_session.execute.return_value.all.return_value = user_results

        endpoints = monitor._get_endpoints_for_health_check(mock_session)

        # All 3 endpoints should be included (no domain filtering)
        assert len(endpoints) == 3
        assert endpoints[0].id == 1
        assert endpoints[0].base_url is None
        assert endpoints[1].id == 2
        assert endpoints[1].base_url == ""
        assert endpoints[2].id == 3
        assert endpoints[2].base_url == "https://valid.com"


class TestCheckEndpointHealth:
    """Tests for _check_endpoint_health and tier methods."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    @pytest.fixture
    def sample_endpoint(self):
        """Create sample endpoint with no health signals (unhealthy)."""
        return EndpointHealthInfo(
            id=1,
            slug="test-model",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api", "enabled": True, "config": {"url": "/test"}}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
        )

    def test_no_domain_is_unhealthy(self, monitor):
        """Test endpoint without owner domain is unhealthy."""
        endpoint = EndpointHealthInfo(
            id=1,
            slug="no-domain",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url=None,
            owner_id=10,
            owner_type="user",
        )
        endpoint_id, is_healthy = monitor._check_endpoint_health(endpoint)
        assert endpoint_id == 1
        assert is_healthy is False

    def test_empty_domain_is_unhealthy(self, monitor):
        """Test endpoint with empty owner domain is unhealthy."""
        endpoint = EndpointHealthInfo(
            id=2,
            slug="empty-domain",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url="",
            owner_id=10,
            owner_type="user",
        )
        endpoint_id, is_healthy = monitor._check_endpoint_health(endpoint)
        assert endpoint_id == 2
        assert is_healthy is False

    def test_fresh_per_endpoint_health_healthy(self, monitor):
        """Test fresh per-endpoint health status of 'healthy' returns True."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=now - timedelta(seconds=10),
            health_ttl_seconds=300,
        )
        endpoint_id, is_healthy = monitor._check_endpoint_health(endpoint)
        assert endpoint_id == 1
        assert is_healthy is True

    def test_fresh_per_endpoint_health_unhealthy(self, monitor):
        """Test fresh per-endpoint health status of 'unhealthy' returns False."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="unhealthy",
            health_checked_at=now - timedelta(seconds=10),
            health_ttl_seconds=300,
        )
        endpoint_id, is_healthy = monitor._check_endpoint_health(endpoint)
        assert endpoint_id == 1
        assert is_healthy is False

    def test_no_signals_is_unhealthy(self, monitor, sample_endpoint):
        """Test no health signals (null health fields) is unhealthy."""
        endpoint_id, is_healthy = monitor._check_endpoint_health(sample_endpoint)
        assert endpoint_id == 1
        assert is_healthy is False

    def test_stale_per_endpoint_health_is_unhealthy(self, monitor):
        """Test expired per-endpoint health is unhealthy (no heartbeat fallback)."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api"}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=now - timedelta(seconds=600),  # Stale (expired)
            health_ttl_seconds=300,
        )
        endpoint_id, is_healthy = monitor._check_endpoint_health(endpoint)
        assert endpoint_id == 1
        assert is_healthy is False

    def test_explicit_now_is_the_clock(self, monitor):
        """The cycle's clock, not wall time, decides freshness."""
        checked_at = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test-endpoint",
            endpoint_type="model",
            is_active=True,
            connect=[{"type": "rest_api", "config": {"url": "/test"}}],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=checked_at,
            health_ttl_seconds=60,
        )

        # Long expired on the wall clock, but fresh at the snapshot instant.
        assert monitor._check_endpoint_health(
            endpoint, now=checked_at + timedelta(seconds=30)
        ) == (1, True)
        assert monitor._check_endpoint_health(
            endpoint, now=checked_at + timedelta(seconds=90)
        ) == (1, False)


class TestCheckPerEndpointHealth:
    """Tests for _check_per_endpoint_health tier method."""

    @pytest.fixture
    def monitor(self):
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    def test_returns_none_when_no_health_fields(self, monitor):
        """Test returns None when health fields are absent."""
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
        )
        now = datetime.now(timezone.utc)
        assert monitor._check_per_endpoint_health(endpoint, now) is None

    def test_returns_none_when_expired(self, monitor):
        """Test returns None when health status has expired."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=now - timedelta(seconds=600),
            health_ttl_seconds=300,
        )
        assert monitor._check_per_endpoint_health(endpoint, now) is None

    def test_returns_true_when_healthy(self, monitor):
        """Test returns True when fresh and healthy."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="healthy",
            health_checked_at=now - timedelta(seconds=10),
            health_ttl_seconds=300,
        )
        assert monitor._check_per_endpoint_health(endpoint, now) is True

    def test_returns_false_when_unhealthy(self, monitor):
        """Test returns False when fresh and unhealthy."""
        now = datetime.now(timezone.utc)
        endpoint = EndpointHealthInfo(
            id=1,
            slug="test",
            endpoint_type="model",
            is_active=True,
            connect=[],
            base_url="https://example.com",
            owner_id=10,
            owner_type="user",
            health_status="unhealthy",
            health_checked_at=now - timedelta(seconds=10),
            health_ttl_seconds=300,
        )
        assert monitor._check_per_endpoint_health(endpoint, now) is False


class TestUpdateHealthStatuses:
    """Tests for _update_health_statuses (bulk, one commit per cycle)."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    @pytest.fixture
    def endpoints(self, test_session):
        """Three persisted endpoints with distinct slugs."""
        from syfthub.models.endpoint import EndpointModel
        from syfthub.models.user import UserModel
        from tests.test_utils import get_test_user_model_data

        user = UserModel(**get_test_user_model_data())
        test_session.add(user)
        test_session.commit()
        rows = [
            EndpointModel(
                user_id=user.id,
                name=f"Endpoint {i}",
                slug=f"endpoint-{i}",
                description="",
                type="model",
                visibility="public",
                is_active=True,
                contributors=[user.id],
                version="0.1.0",
                readme="",
                stars_count=0,
                policies=[],
            )
            for i in range(3)
        ]
        test_session.add_all(rows)
        test_session.commit()
        return rows

    @staticmethod
    def _state(test_session, endpoint_id):
        from syfthub.models.endpoint import EndpointModel

        test_session.expire_all()
        row = test_session.get(EndpointModel, endpoint_id)
        return (row.is_active, row.consecutive_failure_count)

    def test_healthy_resets_and_activates(self, monitor, test_session, endpoints):
        a = endpoints[0]
        a.is_active = False
        a.consecutive_failure_count = 5
        test_session.commit()

        result = monitor._update_health_statuses(test_session, {a.id: True})

        assert result == {a.id: (True, 0)}
        assert self._state(test_session, a.id) == (True, 0)

    def test_unhealthy_increments_below_threshold(
        self, monitor, test_session, endpoints
    ):
        a = endpoints[0]

        assert monitor._update_health_statuses(test_session, {a.id: False}) == {
            a.id: (True, 1)
        }
        assert monitor._update_health_statuses(test_session, {a.id: False}) == {
            a.id: (True, 2)
        }
        assert self._state(test_session, a.id) == (True, 2)

    def test_unhealthy_deactivates_at_threshold(self, monitor, test_session, endpoints):
        a = endpoints[0]
        a.consecutive_failure_count = 2
        test_session.commit()

        result = monitor._update_health_statuses(test_session, {a.id: False})

        assert result == {a.id: (False, 3)}
        assert self._state(test_session, a.id) == (False, 3)

    def test_mixed_verdicts_in_one_call(self, monitor, test_session, endpoints):
        a, b, c = endpoints
        b.consecutive_failure_count = 2
        test_session.commit()

        result = monitor._update_health_statuses(
            test_session, {a.id: True, b.id: False, c.id: False}
        )

        assert result == {a.id: (True, 0), b.id: (False, 3), c.id: (True, 1)}

    def test_missing_endpoint_is_absent_from_result(
        self, monitor, test_session, endpoints
    ):
        a = endpoints[0]

        result = monitor._update_health_statuses(
            test_session, {999_999: False, a.id: True}
        )

        assert result == {a.id: (True, 0)}

    def test_database_error_rolls_back_and_returns_empty(self, monitor):
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("Database error")

        result = monitor._update_health_statuses(mock_session, {1: False})

        assert result == {}
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    def test_one_commit_and_bounded_statements_for_many_endpoints(self, monitor):
        mock_session = MagicMock()
        mock_session.execute.return_value = []

        monitor._update_health_statuses(
            mock_session, {i: i % 2 == 0 for i in range(1200)}
        )

        # 600 healthy + 600 unhealthy ids, 500 per statement: 2 + 2 UPDATEs.
        assert mock_session.execute.call_count == 4
        mock_session.commit.assert_called_once()


class TestRunHealthCheckCycle:
    """Tests for run_health_check_cycle method."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    @pytest.mark.asyncio
    async def test_cycle_skips_when_lock_not_acquired(self, monitor):
        """Test health check cycle skips when advisory lock is held by another worker."""
        mock_session = MagicMock()

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=False),
            patch.object(monitor, "_get_endpoints_for_health_check") as mock_get,
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            # Should not query endpoints since lock was not acquired
            mock_get.assert_not_called()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_proceeds_when_lock_acquired(self, monitor):
        """Test health check cycle proceeds when advisory lock is acquired."""
        mock_session = MagicMock()

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=True),
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=[]
            ) as mock_get,
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            # Should query endpoints since lock was acquired
            mock_get.assert_called_once()
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cycle_no_endpoints(self, monitor):
        """Test health check cycle with no endpoints."""
        mock_session = MagicMock()

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=True),
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
                slug="test-endpoint",
                endpoint_type="model",
                is_active=True,
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                base_url="https://example.com",
                owner_id=10,
                owner_type="user",
            )
        ]

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=True),
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(monitor, "_check_endpoint_health", return_value=(1, True)),
            patch.object(
                monitor,
                "_update_health_statuses",
                return_value={1: (True, 0)},  # Still active, no failures
            ),
            patch.object(monitor, "_emit_uptime_samples") as mock_emit,
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            mock_session.close.assert_called_once()
            # One sample per endpoint: (id, reported_healthy, is_active)
            samples = mock_emit.call_args.args[1]
            assert samples == [(1, True, True)]

    @pytest.mark.asyncio
    async def test_cycle_with_state_changes(self, monitor):
        """Test health check cycle with state changes when threshold reached."""
        mock_session = MagicMock()
        endpoints = [
            EndpointHealthInfo(
                id=1,
                slug="test-endpoint",
                endpoint_type="model",
                is_active=True,  # Was active
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                base_url="https://example.com",
                owner_id=10,
                owner_type="user",
            )
        ]

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=True),
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(monitor, "_check_endpoint_health", return_value=(1, False)),
            patch.object(
                monitor,
                "_update_health_statuses",
                return_value={1: (False, 3)},  # Now inactive after 3 failures
            ),
            patch.object(monitor, "_emit_uptime_samples") as mock_emit,
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

            monitor._update_health_statuses.assert_called_once_with(
                mock_session, {1: False}
            )
            # The sample records the smoothed verdict, not just the report.
            assert mock_emit.call_args.args[1] == [(1, False, False)]

    @pytest.mark.asyncio
    async def test_cycle_judges_every_endpoint_against_one_clock(self, monitor):
        """One ``now`` for the whole snapshot.

        A fresh clock per endpoint aged the snapshot by however long the
        cycle had already run, so endpoints late in a slow cycle looked
        stale although newer reports had landed.
        """
        mock_session = MagicMock()
        endpoints = [
            EndpointHealthInfo(
                id=i,
                slug=f"ep-{i}",
                endpoint_type="model",
                is_active=True,
                connect=[{"type": "rest_api", "config": {"url": "/test"}}],
                base_url="https://example.com",
                owner_id=10,
                owner_type="user",
            )
            for i in (1, 2, 3)
        ]

        with (
            patch("syfthub.jobs.health_monitor.db_manager") as mock_db_manager,
            patch.object(monitor, "_try_acquire_cycle_lock", return_value=True),
            patch.object(
                monitor, "_get_endpoints_for_health_check", return_value=endpoints
            ),
            patch.object(
                monitor,
                "_check_endpoint_health",
                side_effect=lambda ep, _now: (ep.id, True),
            ) as mock_check,
            patch.object(
                monitor,
                "_update_health_statuses",
                return_value={1: (True, 0), 2: (True, 0), 3: (True, 0)},
            ),
            patch.object(monitor, "_emit_uptime_samples") as mock_emit,
        ):
            mock_db_manager.get_session.return_value = mock_session

            await monitor.run_health_check_cycle()

        clocks = {call.args[1] for call in mock_check.call_args_list}
        assert len(clocks) == 1, "every endpoint must be judged at the same instant"
        assert mock_emit.call_args.args[2] == clocks.pop()


class TestHealthMonitorLifecycle:
    """Tests for start/stop lifecycle methods."""

    @pytest.fixture
    def monitor(self):
        """Create EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 0.1  # Fast for testing
        settings.health_check_failure_threshold = 3
        return EndpointHealthMonitor(settings)

    @pytest.fixture
    def disabled_monitor(self):
        """Create disabled EndpointHealthMonitor for testing."""
        settings = MagicMock()
        settings.health_check_enabled = False
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
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


class TestUptimeSampleEmission:
    """Tests for the new uptime telemetry hooks in EndpointHealthMonitor."""

    @pytest.fixture
    def monitor(self):
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        settings.uptime_bucket_seconds = 1800
        settings.uptime_retention_days = 90
        return EndpointHealthMonitor(settings)

    def test_init_reads_uptime_settings(self):
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        settings.uptime_bucket_seconds = 600
        settings.uptime_retention_days = 14
        m = EndpointHealthMonitor(settings)
        assert m.bucket_seconds == 600
        assert m.uptime_retention_days == 14

    def test_init_defaults_when_settings_are_magicmock(self):
        # MagicMock returns MagicMock for absent attrs; init must fall back to
        # safe defaults rather than blowing up.
        settings = MagicMock()
        settings.health_check_enabled = True
        settings.health_check_interval_seconds = 30
        settings.health_check_failure_threshold = 3
        # uptime_* left unset → MagicMock attr access; init should coerce.
        m = EndpointHealthMonitor(settings)
        assert m.bucket_seconds == 1800
        assert m.uptime_retention_days == 90

    def test_current_bucket_start_floors_to_bucket(self, monitor):
        # 12:34:56 with 1800s buckets → 12:30:00
        now = datetime(2026, 5, 13, 12, 34, 56, tzinfo=timezone.utc)
        bucket = monitor._current_bucket_start(now)
        assert bucket == datetime(2026, 5, 13, 12, 30, 0, tzinfo=timezone.utc)

    def test_current_bucket_start_on_boundary(self, monitor):
        now = datetime(2026, 5, 13, 13, 0, 0, tzinfo=timezone.utc)
        assert monitor._current_bucket_start(now) == now

    def test_emit_uptime_samples_writes_one_batch(self, monitor):
        mock_session = MagicMock()
        now = datetime(2026, 5, 13, 12, 5, 0, tzinfo=timezone.utc)
        with patch("syfthub.repositories.endpoint.EndpointRepository") as RepoCls:
            repo = MagicMock()
            RepoCls.return_value = repo
            monitor._emit_uptime_samples(
                mock_session,
                [(42, True, True), (43, False, True)],  # 43: a blip, still active
                now=now,
            )
        bucket = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        repo.upsert_uptime_samples.assert_called_once_with(
            [(42, bucket, True, True), (43, bucket, False, True)]
        )
        mock_session.commit.assert_called_once()

    def test_emit_uptime_samples_swallows_errors(self, monitor):
        mock_session = MagicMock()
        now = datetime(2026, 5, 13, 12, 0, 0, tzinfo=timezone.utc)
        with patch(
            "syfthub.repositories.endpoint.EndpointRepository",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise — emission is best-effort.
            monitor._emit_uptime_samples(mock_session, [(1, False, False)], now=now)
        mock_session.rollback.assert_called_once()

    def test_emit_uptime_samples_skips_empty_cycle(self, monitor):
        with patch("syfthub.repositories.endpoint.EndpointRepository") as RepoCls:
            monitor._emit_uptime_samples(
                MagicMock(), [], now=datetime(2026, 5, 13, tzinfo=timezone.utc)
            )
        RepoCls.assert_not_called()

    def test_retention_runs_at_most_once_per_day(self, monitor):
        mock_session = MagicMock()
        now = datetime(2026, 5, 13, 1, 0, 0, tzinfo=timezone.utc)
        with patch("syfthub.repositories.endpoint.EndpointRepository") as RepoCls:
            repo = MagicMock()
            repo.delete_uptime_samples_older_than.return_value = 5
            RepoCls.return_value = repo

            monitor._maybe_run_uptime_retention(mock_session, now)
            monitor._maybe_run_uptime_retention(mock_session, now)  # same day → skipped
        repo.delete_uptime_samples_older_than.assert_called_once_with(90)
        mock_session.commit.assert_called_once()
        assert monitor._last_retention_sweep_date == "2026-05-13"

    def test_retention_disabled_when_zero(self, monitor):
        monitor.uptime_retention_days = 0
        with patch("syfthub.repositories.endpoint.EndpointRepository") as RepoCls:
            monitor._maybe_run_uptime_retention(
                MagicMock(), datetime(2026, 5, 13, tzinfo=timezone.utc)
            )
        RepoCls.assert_not_called()

    def test_retention_rolls_back_on_error(self, monitor):
        mock_session = MagicMock()
        now = datetime(2026, 5, 14, 1, 0, 0, tzinfo=timezone.utc)
        with patch("syfthub.repositories.endpoint.EndpointRepository") as RepoCls:
            repo = MagicMock()
            repo.delete_uptime_samples_older_than.side_effect = RuntimeError("db")
            RepoCls.return_value = repo
            # Must not raise
            monitor._maybe_run_uptime_retention(mock_session, now)
        mock_session.rollback.assert_called_once()
        # Date marker must NOT advance on failure so we'll retry next cycle
        assert monitor._last_retention_sweep_date != "2026-05-14"
