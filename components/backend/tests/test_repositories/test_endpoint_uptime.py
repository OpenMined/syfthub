"""Tests for the endpoint uptime/telemetry repository methods.

Exercises the SQLite fallback paths (no ``ON CONFLICT``) of
``upsert_uptime_sample``, plus ``get_uptime_samples``,
``delete_uptime_samples_older_than``, ``get_by_owner_and_slug_any_state``,
and the latency-aware path of ``bulk_update_health_status``.
"""

from datetime import datetime, timedelta, timezone

import pytest

from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel
from syfthub.repositories.endpoint import EndpointRepository


@pytest.fixture
def user(test_session, sample_user_data):
    u = UserModel(**sample_user_data)
    test_session.add(u)
    test_session.commit()
    return u


@pytest.fixture
def endpoint(test_session, user, sample_endpoint_data):
    data = dict(sample_endpoint_data)
    data["user_id"] = user.id
    ep = EndpointModel(**data)
    test_session.add(ep)
    test_session.commit()
    return ep


class TestUpsertUptimeSample:
    def test_insert_new_row(self, test_session, endpoint):
        repo = EndpointRepository(test_session)
        bucket = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)

        repo.upsert_uptime_sample(
            endpoint_id=endpoint.id,
            bucket_start=bucket,
            is_healthy=True,
            latency_ms=42,
        )
        test_session.commit()

        samples = repo.get_uptime_samples(endpoint_id=endpoint.id, window_hours=24 * 30)
        assert len(samples) == 1
        s = samples[0]
        assert s.total_checks == 1
        assert s.healthy_checks == 1
        assert s.latency_count == 1
        assert s.latency_sum_ms == 42
        assert s.latency_min_ms == 42
        assert s.latency_max_ms == 42

    def test_accumulates_into_existing_bucket(self, test_session, endpoint):
        repo = EndpointRepository(test_session)
        bucket = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)

        repo.upsert_uptime_sample(endpoint.id, bucket, True, 30)
        repo.upsert_uptime_sample(endpoint.id, bucket, True, 50)
        repo.upsert_uptime_sample(endpoint.id, bucket, False, None)
        test_session.commit()

        samples = repo.get_uptime_samples(endpoint.id, 24 * 30)
        assert len(samples) == 1
        s = samples[0]
        assert s.total_checks == 3
        assert s.healthy_checks == 2
        assert s.latency_count == 2
        assert s.latency_sum_ms == 80
        assert s.latency_min_ms == 30
        assert s.latency_max_ms == 50

    def test_unhealthy_without_latency_does_not_touch_latency_fields(
        self, test_session, endpoint
    ):
        repo = EndpointRepository(test_session)
        bucket = datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc)

        repo.upsert_uptime_sample(endpoint.id, bucket, False, None)
        test_session.commit()

        s = repo.get_uptime_samples(endpoint.id, 24 * 30)[0]
        assert s.total_checks == 1
        assert s.healthy_checks == 0
        assert s.latency_count == 0
        assert s.latency_min_ms is None
        assert s.latency_max_ms is None


class TestUptimeRetention:
    def test_purges_old_samples_only(self, test_session, endpoint):
        repo = EndpointRepository(test_session)
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=100)
        fresh = now - timedelta(days=1)

        repo.upsert_uptime_sample(endpoint.id, old, True, 10)
        repo.upsert_uptime_sample(endpoint.id, fresh, True, 20)
        test_session.commit()

        removed = repo.delete_uptime_samples_older_than(retention_days=30)
        test_session.commit()
        assert removed == 1

        remaining = repo.get_uptime_samples(endpoint.id, window_hours=24 * 365)
        assert len(remaining) == 1
        assert remaining[0].latency_sum_ms == 20

    def test_zero_retention_is_noop_when_no_old_rows(self, test_session, endpoint):
        repo = EndpointRepository(test_session)
        bucket = datetime.now(timezone.utc) - timedelta(hours=1)
        repo.upsert_uptime_sample(endpoint.id, bucket, True, 50)
        test_session.commit()
        # Asking to delete rows older than 30 days when nothing is that old
        assert repo.delete_uptime_samples_older_than(retention_days=30) == 0


class TestGetByOwnerAndSlugAnyState:
    def test_finds_user_owned(self, test_session, endpoint, user):
        repo = EndpointRepository(test_session)
        found = repo.get_by_owner_and_slug_any_state(
            user_id=user.id,
            organization_id=None,
            slug=endpoint.slug,
        )
        assert found is not None
        assert found.id == endpoint.id

    def test_returns_inactive_endpoints(self, test_session, endpoint, user):
        # The unique pattern: the regular lookup filters is_active=True; this
        # method must NOT.
        endpoint.is_active = False
        test_session.commit()

        repo = EndpointRepository(test_session)
        found = repo.get_by_owner_and_slug_any_state(
            user_id=user.id,
            organization_id=None,
            slug=endpoint.slug,
        )
        assert found is not None
        assert found.id == endpoint.id

    def test_rejects_both_owners_set(self, test_session):
        repo = EndpointRepository(test_session)
        assert (
            repo.get_by_owner_and_slug_any_state(user_id=1, organization_id=2, slug="x")
            is None
        )

    def test_rejects_neither_owner_set(self, test_session):
        repo = EndpointRepository(test_session)
        assert (
            repo.get_by_owner_and_slug_any_state(
                user_id=None, organization_id=None, slug="x"
            )
            is None
        )

    def test_not_found(self, test_session, user):
        repo = EndpointRepository(test_session)
        assert (
            repo.get_by_owner_and_slug_any_state(
                user_id=user.id, organization_id=None, slug="nope"
            )
            is None
        )


class TestBulkUpdateHealthLatency:
    def test_writes_latency_when_provided(self, test_session, endpoint):
        repo = EndpointRepository(test_session)
        now = datetime.now(timezone.utc)
        repo.bulk_update_health_status(
            [
                {
                    "endpoint_id": endpoint.id,
                    "health_status": "healthy",
                    "health_checked_at": now,
                    "health_ttl_seconds": 300,
                    "last_latency_ms": 73,
                }
            ]
        )
        test_session.commit()

        refreshed = test_session.get(EndpointModel, endpoint.id)
        assert refreshed.last_latency_ms == 73
        assert refreshed.health_status == "healthy"

    def test_skips_latency_when_none(self, test_session, endpoint):
        endpoint.last_latency_ms = 99
        test_session.commit()

        repo = EndpointRepository(test_session)
        repo.bulk_update_health_status(
            [
                {
                    "endpoint_id": endpoint.id,
                    "health_status": "unhealthy",
                    "health_checked_at": datetime.now(timezone.utc),
                    "health_ttl_seconds": 300,
                    "last_latency_ms": None,
                }
            ]
        )
        test_session.commit()

        refreshed = test_session.get(EndpointModel, endpoint.id)
        # Untouched — None means "no fresh signal", not "clear the field"
        assert refreshed.last_latency_ms == 99
        assert refreshed.health_status == "unhealthy"
