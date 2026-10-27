"""Tests for 1c — the write paths that used to be account-wide.

Two bugs motivated the step, and the tests named for them are the ones worth
keeping honest: ``users.domain`` was a single field per account, so health
reports from two spaces overwrote each other on every cycle; and sync deleted
every endpoint the *account* owned, so one space syncing wiped another's
catalogue.

These do not double as regression tests against the old code — the parameters
they pass did not exist before 1c — so they encode the intended behaviour
rather than proving the previous failure.
"""

import pytest
from tests.test_utils import get_test_user_model_data

from syfthub.domain.satellite import AmbiguousSatelliteError, SatelliteKind
from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel
from syfthub.schemas.endpoint import (
    EndpointCreate,
    EndpointHealthItem,
    EndpointHealthStatus,
    EndpointType,
    EndpointVisibility,
)
from syfthub.schemas.satellite import SatelliteCreate
from syfthub.schemas.user import User
from syfthub.services.endpoint_service import EndpointService
from syfthub.services.satellite_service import SatelliteService


@pytest.fixture
def services(test_session):
    """Endpoint and satellite services on one session."""
    return EndpointService(test_session), SatelliteService(test_session)


@pytest.fixture
def owner(test_session):
    """A user who owns the satellites and endpoints under test."""
    model = UserModel(
        **get_test_user_model_data(
            {
                "username": "alice",
                "email": "alice@example.com",
                "full_name": "Alice",
                "avatar_url": None,
                "role": "user",
                "password_hash": "x",
                "is_active": True,
            }
        )
    )
    test_session.add(model)
    test_session.commit()
    test_session.refresh(model)
    return User.model_validate(model)


def _register(sat_service, user_id, url):
    """Register a space at an origin."""
    return sat_service.create_satellite(
        user_id, SatelliteCreate(kind=SatelliteKind.SPACE, base_url=url)
    )


def _health(url, slug="my-endpoint", satellite_id=None):
    """A one-endpoint health report."""
    from datetime import datetime, timezone

    return {
        "endpoints_health": [
            EndpointHealthItem(
                slug=slug,
                status=EndpointHealthStatus.HEALTHY,
                checked_at=datetime.now(timezone.utc),
            )
        ],
        "url": url,
        "satellite_id": satellite_id,
    }


def _endpoint(slug):
    """A minimal publishable endpoint."""
    return EndpointCreate(
        name=slug,
        slug=slug,
        description="",
        type=EndpointType.MODEL,
        visibility=EndpointVisibility.PUBLIC,
    )


class TestHealthNoLongerFlipFlops:
    """The first live bug: health wrote users.domain, one field per account."""

    def test_two_spaces_keep_their_own_origins(self, services, owner, test_session):
        """Test that alternating reports do not overwrite each other.

        Pre-1c this was the flip-flop: whichever space reported last decided
        where *all* the account's endpoints appeared to live.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")

        for _ in range(3):
            ep_service.report_endpoint_health(
                current_user=owner,
                **_health("https://a.example.com", satellite_id=a.id),
            )
            ep_service.report_endpoint_health(
                current_user=owner,
                **_health("https://b.example.com", satellite_id=b.id),
            )

        by_id = {s.id: s.base_url for s in sat_service.list_satellites(owner.id)}
        assert by_id[a.id] == "https://a.example.com"
        assert by_id[b.id] == "https://b.example.com"

    def test_users_domain_is_no_longer_authoritative(
        self, services, owner, test_session
    ):
        """Test that the satellite, not the account field, holds the origin.

        ``users.domain`` is still mirrored for rollback safety (see
        TestLegacyDomainMirror), but nothing reads it — so the assertion that
        matters is that the *satellite* is what the heartbeat updated.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://moved.example.com")
        )

        listed = sat_service.list_satellites(owner.id)
        assert len(listed) == 1
        assert listed[0].id == a.id
        assert listed[0].base_url == "https://moved.example.com"

    def test_single_space_needs_no_satellite_id(self, services, owner):
        """Test S2: an existing account reports exactly as it does today."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://a.example.com")
        )

        assert sat_service.list_satellites(owner.id)[0].id == a.id

    def test_zero_satellites_registers_from_the_report(self, services, owner):
        """Test that an account with none acquires one, with no space change.

        This is what lets old spaces self-heal: the health report has always
        carried the URL.
        """
        ep_service, sat_service = services
        assert sat_service.list_satellites(owner.id) == []

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://new.example.com")
        )

        listed = sat_service.list_satellites(owner.id)
        assert len(listed) == 1
        assert listed[0].base_url == "https://new.example.com"

    def test_a_moved_space_updates_its_own_row(self, services, owner):
        """Test S6: same satellite, new origin, no duplicate created."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://old.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://moved.example.com")
        )

        listed = sat_service.list_satellites(owner.id)
        assert len(listed) == 1, "a moved space must not split into two satellites"
        assert listed[0].id == a.id
        assert listed[0].base_url == "https://moved.example.com"

    def test_origin_is_canonicalised(self, services, owner):
        """Test that BaseUrl normalises what scheme://netloc did not."""
        ep_service, sat_service = services
        _register(sat_service, owner.id, "https://a.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("HTTPS://A.Example.com:443/v1/")
        )

        assert (
            sat_service.list_satellites(owner.id)[0].base_url == "https://a.example.com"
        )

    def test_a_reported_url_identifies_its_space(self, services, owner):
        """Test that an unmodified space keeps reporting after a second appears.

        Health always carries the URL it is reporting for, so it never needs
        ``satellite_id`` while that URL is one the account has registered — which
        is what keeps un-upgraded spaces working as a fleet grows.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        _register(sat_service, owner.id, "https://b.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://a.example.com")
        )

        by_id = {s.id: s.base_url for s in sat_service.list_satellites(owner.id)}
        assert by_id[a.id] == "https://a.example.com"

    def test_two_spaces_and_an_unknown_url_is_ambiguous(self, services, owner):
        """Test S3: the forcing function, narrowed to where it belongs.

        Only a space that *moved* while the account owns several is ambiguous —
        nothing on record says which one relocated, and guessing would attribute
        the new origin to the wrong host.
        """
        ep_service, sat_service = services
        _register(sat_service, owner.id, "https://a.example.com")
        _register(sat_service, owner.id, "https://b.example.com")

        with pytest.raises(AmbiguousSatelliteError):
            ep_service.report_endpoint_health(
                current_user=owner, **_health("https://moved.example.com")
            )


class TestHealthIsScopedToTheReportingSpace:
    """A report only touches endpoints the reporting satellite serves."""

    def _attach(self, services, owner, satellite, slug):
        ep_service, _ = services
        ep_service.sync_user_endpoints(
            [_endpoint(slug)], owner, satellite_id=satellite.id
        )

    def test_another_space_cannot_overwrite_a_served_endpoint(
        self, services, owner, test_session
    ):
        """Space B reporting A's slug is ignored, not applied to A's endpoint."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")
        self._attach(services, owner, a, "my-endpoint")

        from_b = ep_service.report_endpoint_health(
            current_user=owner, **_health("https://b.example.com", satellite_id=b.id)
        )
        assert (from_b.updated, from_b.ignored) == (0, 1)
        assert test_session.query(EndpointModel).one().health_status is None

        from_a = ep_service.report_endpoint_health(
            current_user=owner, **_health("https://a.example.com", satellite_id=a.id)
        )
        assert (from_a.updated, from_a.ignored) == (1, 0)
        assert test_session.query(EndpointModel).one().health_status == "healthy"


class TestSyncNoLongerClobbers:
    """The second live bug: sync deleted every endpoint the account owned."""

    def test_syncing_one_space_leaves_the_other_alone(
        self, services, owner, test_session
    ):
        """Test the clobber is gone.

        Pre-1c, space B syncing deleted space A's endpoints outright.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")

        ep_service.sync_user_endpoints([_endpoint("from-a")], owner, satellite_id=a.id)
        ep_service.sync_user_endpoints([_endpoint("from-b")], owner, satellite_id=b.id)

        slugs = sorted(r[0] for r in test_session.query(EndpointModel.slug).all())
        assert slugs == ["from-a", "from-b"]

    def test_sync_attaches_to_the_resolved_satellite(
        self, services, owner, test_session
    ):
        """Test that synced endpoints carry space_id."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        ref = sat_service.satellite_repository.get_by_public_id(owner.id, a.id)

        ep_service.sync_user_endpoints(
            [_endpoint("my-endpoint")], owner, satellite_id=a.id
        )

        assert test_session.query(EndpointModel).one().space_id == ref.id

    def test_resyncing_replaces_only_that_space(self, services, owner, test_session):
        """Test that a second sync for one space is still destructive for it."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")

        ep_service.sync_user_endpoints([_endpoint("a-one")], owner, satellite_id=a.id)
        ep_service.sync_user_endpoints([_endpoint("b-one")], owner, satellite_id=b.id)
        ep_service.sync_user_endpoints([_endpoint("a-two")], owner, satellite_id=a.id)

        slugs = sorted(r[0] for r in test_session.query(EndpointModel.slug).all())
        assert slugs == ["a-two", "b-one"], "a's sync replaced a's, kept b's"

    def test_empty_sync_clears_only_that_space(self, services, owner, test_session):
        """Test that an empty payload no longer wipes the whole account."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")
        ep_service.sync_user_endpoints([_endpoint("a-one")], owner, satellite_id=a.id)
        ep_service.sync_user_endpoints([_endpoint("b-one")], owner, satellite_id=b.id)

        ep_service.sync_user_endpoints([], owner, satellite_id=a.id)

        slugs = [r[0] for r in test_session.query(EndpointModel.slug).all()]
        assert slugs == ["b-one"]

    def test_sync_with_no_satellite_leaves_endpoints_unattached(
        self, services, owner, test_session
    ):
        """Test Decision A: an account with no satellite can still sync."""
        ep_service, _ = services

        ep_service.sync_user_endpoints([_endpoint("loose")], owner)

        endpoint = test_session.query(EndpointModel).one()
        assert endpoint.slug == "loose"
        assert endpoint.space_id is None

    def test_unattached_sync_does_not_touch_attached_endpoints(
        self, services, owner, test_session
    ):
        """Test that the None bucket is scoped like any other.

        An account that later registers a satellite must not have its attached
        endpoints wiped by an unqualified sync.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        ep_service.sync_user_endpoints(
            [_endpoint("attached")], owner, satellite_id=a.id
        )

        # Now an unqualified sync — resolves to the single satellite, not None.
        ep_service.sync_user_endpoints([_endpoint("replacement")], owner)

        slugs = [r[0] for r in test_session.query(EndpointModel.slug).all()]
        assert slugs == ["replacement"]


class TestPublishAttaches:
    """Publish sets space_id so listings can derive a URL per endpoint."""

    def test_publish_attaches_to_the_single_satellite(
        self, services, owner, test_session
    ):
        """Test the ordinary case."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        ref = sat_service.satellite_repository.get_by_public_id(owner.id, a.id)

        ep_service.create_endpoint(
            _endpoint("my-endpoint"), owner.id, current_user=owner
        )

        assert test_session.query(EndpointModel).one().space_id == ref.id

    def test_publish_with_no_satellite_is_allowed(self, services, owner, test_session):
        """Test Decision A for publish: unattached, not refused.

        A brand-new account must be able to publish before any space has
        reported in, exactly as it can today.
        """
        ep_service, _ = services

        ep_service.create_endpoint(
            _endpoint("my-endpoint"), owner.id, current_user=owner
        )

        assert test_session.query(EndpointModel).one().space_id is None

    def test_publish_honours_an_explicit_satellite(self, services, owner, test_session):
        """Test that a chosen satellite wins over the count."""
        ep_service, sat_service = services
        _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")
        ref_b = sat_service.satellite_repository.get_by_public_id(owner.id, b.id)

        ep_service.create_endpoint(
            _endpoint("my-endpoint"), owner.id, current_user=owner, satellite_id=b.id
        )

        assert test_session.query(EndpointModel).one().space_id == ref_b.id

    def test_publish_is_ambiguous_with_two_satellites(self, services, owner):
        """Test that publish refuses rather than guessing."""
        ep_service, sat_service = services
        _register(sat_service, owner.id, "https://a.example.com")
        _register(sat_service, owner.id, "https://b.example.com")

        with pytest.raises(AmbiguousSatelliteError):
            ep_service.create_endpoint(
                _endpoint("my-endpoint"), owner.id, current_user=owner
            )


class TestSyncBeforeRegistration:
    """The order an unupgraded space may do things in."""

    def test_syncing_before_a_satellite_exists_then_after(
        self, services, owner, test_session
    ):
        """Test that a space which synced before registering can sync again.

        Sequence: sync with no satellite (endpoints land unattached), then a
        heartbeat registers one, then sync again. The scoped delete used to skip
        the unattached rows, so the re-create collided on the per-user unique
        slug and every later sync returned 500 — permanently.
        """
        ep_service, sat_service = services

        ep_service.sync_user_endpoints([_endpoint("my-endpoint")], owner)
        assert test_session.query(EndpointModel).one().space_id is None

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://later.example.com")
        )
        ref = sat_service.satellite_repository.list_for_user(owner.id)[0]

        ep_service.sync_user_endpoints([_endpoint("my-endpoint")], owner)

        test_session.expire_all()
        survivor = test_session.query(EndpointModel).one()
        assert survivor.slug == "my-endpoint"
        assert survivor.space_id == ref.id, "the re-sync should claim it"

    def test_publishing_before_registration_then_syncing(
        self, services, owner, test_session
    ):
        """Test the same collision via publish rather than sync."""
        ep_service, sat_service = services
        ep_service.create_endpoint(
            _endpoint("my-endpoint"), owner.id, current_user=owner
        )
        a = _register(sat_service, owner.id, "https://a.example.com")
        ref = sat_service.satellite_repository.get_by_public_id(owner.id, a.id)

        ep_service.sync_user_endpoints(
            [_endpoint("my-endpoint")], owner, satellite_id=a.id
        )

        test_session.expire_all()
        survivor = test_session.query(EndpointModel).one()
        assert survivor.space_id == ref.id


class TestLegacyDomainMirror:
    """``users.domain`` is kept current purely so a rollback is a non-event.

    Nothing in the codebase reads it. If this release were rolled back, the
    previous code would read it again — and a value frozen at deploy time would
    send every one of that account's endpoints to wherever its space used to be.
    """

    def test_heartbeat_mirrors_a_moved_origin(self, services, owner, test_session):
        """Test the path that fires continuously."""
        ep_service, sat_service = services
        _register(sat_service, owner.id, "https://old.example.com")

        ep_service.report_endpoint_health(
            current_user=owner, **_health("https://moved.example.com")
        )

        test_session.expire_all()
        assert (
            test_session.get(UserModel, owner.id).domain == "https://moved.example.com"
        )

    def test_profile_update_mirrors(self, services, owner, test_session):
        """Test the legacy setup path."""
        _, sat_service = services
        sat_service.register_or_move_space(owner.id, "https://first.example.com")

        test_session.expire_all()
        assert (
            test_session.get(UserModel, owner.id).domain == "https://first.example.com"
        )

        sat_service.register_or_move_space(owner.id, "https://second.example.com")
        test_session.expire_all()
        assert (
            test_session.get(UserModel, owner.id).domain == "https://second.example.com"
        )

    def test_a_station_is_never_mirrored(self, services, owner, test_session):
        """Test that a station's origin does not land in the column.

        A station serves no endpoints, so mirroring it would point the
        rolled-back code at a host that answers nothing.
        """
        _, sat_service = services
        sat_service.create_satellite(
            owner.id,
            SatelliteCreate(
                kind=SatelliteKind.STATION, base_url="https://station.example.com"
            ),
        )

        test_session.expire_all()
        assert test_session.get(UserModel, owner.id).domain is None

    def test_a_second_space_stops_the_mirror(self, services, owner, test_session):
        """Test that the column is left alone once it cannot describe the truth.

        With two spaces no single field is correct, and such an account is
        post-migration by definition — there is nothing to roll back to.
        """
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        test_session.expire_all()
        assert test_session.get(UserModel, owner.id).domain == "https://a.example.com"

        b = _register(sat_service, owner.id, "https://b.example.com")
        ep_service.report_endpoint_health(
            current_user=owner,
            **_health("https://b-moved.example.com", satellite_id=b.id),
        )

        test_session.expire_all()
        assert (
            test_session.get(UserModel, owner.id).domain == "https://a.example.com"
        ), "the mirror must not follow a second space"
        # And the first space is untouched by the second's heartbeat.
        by_id = {s.id: s.base_url for s in sat_service.list_satellites(owner.id)}
        assert by_id[a.id] == "https://a.example.com"
        assert by_id[b.id] == "https://b-moved.example.com"


class TestSyncKeepsExistingEndpoints:
    """The space's list is the truth; the Hub's rows are kept, not replaced.

    Every restart re-syncs. Deleting and re-creating gave each endpoint a new
    id, and the cascade on ``endpoints.id`` took its stars, uptime history,
    collective membership and health state with it. A space cannot rename an
    endpoint, so the slug is a stable key.
    """

    def _rows(self, test_session):
        test_session.expire_all()
        return {
            r.slug: r
            for r in test_session.query(EndpointModel).order_by(EndpointModel.slug)
        }

    def test_resync_keeps_the_id_and_its_history(self, services, owner, test_session):
        """The same slug reported again is the same endpoint, history intact."""
        from datetime import datetime, timezone

        from syfthub.models.endpoint import EndpointUptimeSampleModel

        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        first = ep_service.sync_user_endpoints(
            [_endpoint("news")], owner, satellite_id=a.id
        )
        original_id = first.endpoints[0].id

        row = test_session.get(EndpointModel, original_id)
        row.stars_count = 7
        row.health_status = "healthy"
        row.consecutive_failure_count = 2
        test_session.add(
            EndpointUptimeSampleModel(
                endpoint_id=original_id,
                bucket_start=datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc),
                total_checks=60,
                healthy_checks=58,
                active_checks=60,
            )
        )
        test_session.commit()

        second = ep_service.sync_user_endpoints(
            [_endpoint("news")], owner, satellite_id=a.id
        )

        assert second.endpoints[0].id == original_id
        assert (second.created, second.updated, second.deleted) == (0, 1, 0)
        assert second.synced == 1
        survivor = self._rows(test_session)["news"]
        assert survivor.stars_count == 7
        assert survivor.health_status == "healthy"
        assert survivor.consecutive_failure_count == 2
        assert test_session.query(EndpointUptimeSampleModel).count() == 1

    def test_resync_updates_catalogue_fields_in_place(
        self, services, owner, test_session
    ):
        """Changed name, description, policies land on the existing row."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        first = ep_service.sync_user_endpoints(
            [_endpoint("news")], owner, satellite_id=a.id
        )

        edited = _endpoint("news")
        edited.name = "World news"
        edited.description = "Fresh every hour"
        result = ep_service.sync_user_endpoints([edited], owner, satellite_id=a.id)

        row = self._rows(test_session)["news"]
        assert row.id == first.endpoints[0].id
        assert (row.name, row.description) == ("World news", "Fresh every hour")
        assert (result.created, result.updated) == (0, 1)

    def test_unreported_endpoints_are_deleted_with_their_history(
        self, services, owner, test_session
    ):
        """Dropping an endpoint on the space drops it, and only it, on the Hub."""
        from datetime import datetime, timezone

        from syfthub.models.endpoint import EndpointUptimeSampleModel

        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        first = ep_service.sync_user_endpoints(
            [_endpoint("keep"), _endpoint("drop")], owner, satellite_id=a.id
        )
        ids = {ep.slug: ep.id for ep in first.endpoints}
        for slug in ("keep", "drop"):
            test_session.add(
                EndpointUptimeSampleModel(
                    endpoint_id=ids[slug],
                    bucket_start=datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc),
                    total_checks=1,
                    healthy_checks=1,
                    active_checks=1,
                )
            )
        test_session.commit()

        result = ep_service.sync_user_endpoints(
            [_endpoint("keep")], owner, satellite_id=a.id
        )

        assert (result.synced, result.deleted) == (1, 1)
        rows = self._rows(test_session)
        assert list(rows) == ["keep"]
        assert rows["keep"].id == ids["keep"]
        samples = test_session.query(EndpointUptimeSampleModel).all()
        assert [s.endpoint_id for s in samples] == [ids["keep"]]

    def test_new_endpoints_are_created_beside_existing_ones(
        self, services, owner, test_session
    ):
        """Adding an endpoint on the space creates just that one."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        first = ep_service.sync_user_endpoints(
            [_endpoint("old")], owner, satellite_id=a.id
        )

        result = ep_service.sync_user_endpoints(
            [_endpoint("old"), _endpoint("new")], owner, satellite_id=a.id
        )

        assert (result.created, result.updated, result.deleted) == (1, 1, 0)
        rows = self._rows(test_session)
        assert rows["old"].id == first.endpoints[0].id
        assert rows["new"].id != rows["old"].id

    def test_unattached_rows_are_adopted_not_replaced(
        self, services, owner, test_session
    ):
        """A pre-satellite row with the slug keeps its id and joins the space."""
        ep_service, sat_service = services
        created = ep_service.create_endpoint(
            _endpoint("legacy"), owner.id, current_user=owner
        )
        a = _register(sat_service, owner.id, "https://a.example.com")
        ref = sat_service.satellite_repository.get_by_public_id(owner.id, a.id)

        result = ep_service.sync_user_endpoints(
            [_endpoint("legacy")], owner, satellite_id=a.id
        )

        row = self._rows(test_session)["legacy"]
        assert row.id == created.id
        assert row.space_id == ref.id
        assert (result.updated, result.deleted) == (1, 0)

    def test_a_slug_served_elsewhere_moves_to_the_syncing_space(
        self, services, owner, test_session
    ):
        """Slugs are unique per user, so the reporting space takes the row over."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        b = _register(sat_service, owner.id, "https://b.example.com")
        ref_b = sat_service.satellite_repository.get_by_public_id(owner.id, b.id)
        first = ep_service.sync_user_endpoints(
            [_endpoint("moved")], owner, satellite_id=a.id
        )

        result = ep_service.sync_user_endpoints(
            [_endpoint("moved")], owner, satellite_id=b.id
        )

        row = self._rows(test_session)["moved"]
        assert row.id == first.endpoints[0].id
        assert row.space_id == ref_b.id
        assert (result.updated, result.deleted) == (1, 0)

    def test_archived_endpoint_stays_private_and_archived(
        self, services, owner, test_session
    ):
        """Archiving is the Hub's call; a re-sync saying public must not undo it."""
        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        ep_service.sync_user_endpoints([_endpoint("news")], owner, satellite_id=a.id)
        row = self._rows(test_session)["news"]
        row.archived = True
        row.visibility = "private"
        test_session.commit()

        ep_service.sync_user_endpoints([_endpoint("news")], owner, satellite_id=a.id)

        row = self._rows(test_session)["news"]
        assert row.archived is True
        assert row.visibility == "private"

    def test_search_index_drops_deleted_and_reindexes_served(
        self, services, owner, test_session
    ):
        """Deleted rows leave the index; every served public row is upserted."""
        from unittest.mock import MagicMock

        ep_service, sat_service = services
        a = _register(sat_service, owner.id, "https://a.example.com")
        ep_service.sync_user_endpoints(
            [_endpoint("same"), _endpoint("gone")], owner, satellite_id=a.id
        )
        rows = self._rows(test_session)
        rows["gone"].rag_file_id = str(rows["gone"].id)
        test_session.commit()

        rag = MagicMock()
        rag.is_available = True
        rag.ingest_endpoint.side_effect = lambda model: str(model.id)
        ep_service.rag_service = rag

        ep_service.sync_user_endpoints(
            [_endpoint("same"), _endpoint("added")], owner, satellite_id=a.id
        )

        rag.remove_endpoint.assert_called_once_with(str(rows["gone"].id))
        ingested = sorted(m.args[0].slug for m in rag.ingest_endpoint.call_args_list)
        assert ingested == ["added", "same"]
