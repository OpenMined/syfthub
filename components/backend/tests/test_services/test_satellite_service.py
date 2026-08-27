"""Tests for SatelliteService — CRUD and the graduated resolution rule.

Run against a real (SQLite) session rather than a fake repository: the suite
already does this cheaply everywhere else, and it verifies the unique indexes
and the endpoint-orphaning update at the same time.
"""

import uuid

import pytest
from tests.test_utils import get_test_user_model_data

from syfthub.domain.exceptions import ConflictError, NotFoundError, ValidationError
from syfthub.domain.satellite import (
    AmbiguousSatelliteError,
    SatelliteKind,
    SatelliteKindMismatchError,
)
from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel
from syfthub.schemas.satellite import SatelliteCreate, SatelliteUpdate
from syfthub.services.satellite_service import SatelliteService


@pytest.fixture
def service(test_session):
    """A satellite service bound to the test session."""
    return SatelliteService(test_session)


@pytest.fixture
def users(test_session):
    """Two distinct users, so ownership scoping can be exercised."""
    created = []
    for name in ("alice", "bob"):
        user = UserModel(
            **get_test_user_model_data(
                {
                    "username": name,
                    "email": f"{name}@example.com",
                    "full_name": name.title(),
                    "avatar_url": None,
                    "role": "user",
                    "password_hash": "x",
                    "is_active": True,
                }
            )
        )
        test_session.add(user)
        created.append(user)
    test_session.commit()
    for user in created:
        test_session.refresh(user)
    return created


def _create(service, user_id, base_url="https://s.example.com", kind="space"):
    """Register a satellite through the service."""
    return service.create_satellite(
        user_id, SatelliteCreate(kind=SatelliteKind(kind), base_url=base_url)
    )


class TestCrud:
    """The /satellites endpoints."""

    def test_create_returns_the_public_id_as_id(self, service, users):
        """Test that the response exposes public_id, never the integer key."""
        created = _create(service, users[0].id)
        assert isinstance(created.id, uuid.UUID)
        assert created.base_url == "https://s.example.com"
        assert created.kind is SatelliteKind.SPACE
        assert created.created_at is not None

    def test_create_a_station(self, service, users):
        """Test the station case, which must be registered explicitly."""
        created = service.create_satellite(
            users[0].id,
            SatelliteCreate(
                kind=SatelliteKind.STATION, base_url="https://station.example.com"
            ),
        )
        assert created.kind is SatelliteKind.STATION
        assert created.base_url == "https://station.example.com"

    def test_create_normalises_the_origin(self, service, users):
        """Test that the schema canonicalises before the service stores."""
        created = _create(
            service, users[0].id, base_url="  HTTPS://S.Example.com:443/v1/  "
        )
        assert created.base_url == "https://s.example.com"

    def test_create_is_idempotent_on_the_origin(self, service, users):
        """Test that re-registering an origin returns the existing satellite.

        Lets a space call registration unconditionally at startup.
        """
        first = _create(service, users[0].id, base_url="https://a.example.com")
        again = _create(service, users[0].id, base_url="https://a.example.com")

        assert again.id == first.id
        assert len(service.list_satellites(users[0].id)) == 1

    def test_create_rejects_the_same_origin_as_another_kind(self, service, users):
        """Test that a host cannot be both a space and a station."""
        _create(service, users[0].id, base_url="https://a.example.com")
        with pytest.raises(SatelliteKindMismatchError):
            _create(
                service, users[0].id, base_url="https://a.example.com", kind="station"
            )

    def test_list_is_scoped_and_ordered(self, service, users):
        """Test that an account sees only its own satellites."""
        a = _create(service, users[0].id, base_url="https://a.example.com")
        b = _create(service, users[0].id, base_url="https://b.example.com")
        c = _create(service, users[1].id, base_url="https://c.example.com")

        assert [s.id for s in service.list_satellites(users[0].id)] == [a.id, b.id]
        assert [s.id for s in service.list_satellites(users[1].id)] == [c.id]

    def test_get_by_public_id(self, service, users):
        """Test fetching one satellite."""
        created = _create(service, users[0].id)
        fetched = service.get_satellite(users[0].id, created.id)
        assert fetched.id == created.id
        assert fetched.base_url == "https://s.example.com"

    def test_get_is_owner_scoped(self, service, users):
        """Test that another account's satellite is reported as missing.

        Not-found rather than forbidden, so the identifier cannot be probed.
        """
        created = _create(service, users[0].id)
        with pytest.raises(NotFoundError):
            service.get_satellite(users[1].id, created.id)

    def test_get_unknown_raises_not_found(self, service, users):
        """Test an identifier that belongs to nobody."""
        with pytest.raises(NotFoundError):
            service.get_satellite(users[0].id, uuid.uuid4())

    def test_update_moves_the_origin_and_keeps_identity(self, service, users):
        """Test moving a satellite to a new origin."""
        created = _create(service, users[0].id)
        updated = service.update_satellite(
            users[0].id,
            created.id,
            SatelliteUpdate(base_url="https://moved.example.com"),
        )
        assert updated.base_url == "https://moved.example.com"
        assert updated.id == created.id, "moving must not change identity"

    def test_update_rejects_a_sibling_origin(self, service, users):
        """Test that a move cannot collide with another satellite."""
        _create(service, users[0].id, base_url="https://a.example.com")
        b = _create(service, users[0].id, base_url="https://b.example.com")
        with pytest.raises(ConflictError):
            service.update_satellite(
                users[0].id, b.id, SatelliteUpdate(base_url="https://a.example.com")
            )

    def test_update_is_owner_scoped(self, service, users):
        """Test that another account cannot reconfigure your satellite."""
        created = _create(service, users[0].id)
        with pytest.raises(NotFoundError):
            service.update_satellite(
                users[1].id,
                created.id,
                SatelliteUpdate(base_url="https://hijacked.example.com"),
            )

    def test_delete_is_owner_scoped(self, service, users):
        """Test that another account cannot delete your satellite."""
        created = _create(service, users[0].id)
        with pytest.raises(NotFoundError):
            service.delete_satellite(users[1].id, created.id)
        assert len(service.list_satellites(users[0].id)) == 1


class TestDeleteCascadesToEndpoints:
    """Deleting a satellite deletes what it served."""

    def test_endpoints_are_deleted_with_the_satellite(
        self, service, users, test_session, sample_endpoint_data
    ):
        """Test that "delete this space" removes the space and its endpoints.

        Leaving them behind deactivated would keep their slugs held and block
        the owner from ever republishing them.
        """
        created = _create(service, users[0].id)
        ref = service.satellite_repository.get_by_public_id(users[0].id, created.id)
        endpoint = EndpointModel(
            **{**sample_endpoint_data, "user_id": users[0].id, "space_id": ref.id}
        )
        test_session.add(endpoint)
        test_session.commit()
        endpoint_id = endpoint.id

        service.delete_satellite(users[0].id, created.id)
        test_session.expire_all()

        assert test_session.get(EndpointModel, endpoint_id) is None

    def test_unattached_endpoints_are_untouched(
        self, service, users, test_session, sample_endpoint_data
    ):
        """Test that a NULL space_id never cascades.

        Pre-satellite rows, and publishes by an account with no satellite, must
        survive an unrelated satellite being deleted.
        """
        created = _create(service, users[0].id)
        test_session.add(
            EndpointModel(
                **{
                    **sample_endpoint_data,
                    "user_id": users[0].id,
                    "slug": "unattached",
                    "space_id": None,
                }
            )
        )
        test_session.commit()

        service.delete_satellite(users[0].id, created.id)
        test_session.expire_all()

        assert (
            test_session.query(EndpointModel).filter_by(slug="unattached").one()
            is not None
        )

    def test_other_satellites_endpoints_are_untouched(
        self, service, users, test_session, sample_endpoint_data
    ):
        """Test that the cascade is scoped to the deleted satellite."""
        a = _create(service, users[0].id, base_url="https://a.example.com")
        b = _create(service, users[0].id, base_url="https://b.example.com")
        ref_a = service.satellite_repository.get_by_public_id(users[0].id, a.id)
        ref_b = service.satellite_repository.get_by_public_id(users[0].id, b.id)

        for i, space in enumerate((ref_a.id, ref_b.id)):
            test_session.add(
                EndpointModel(
                    **{
                        **sample_endpoint_data,
                        "user_id": users[0].id,
                        "slug": f"ep-{i}",
                        "space_id": space,
                    }
                )
            )
        test_session.commit()

        service.delete_satellite(users[0].id, a.id)
        test_session.expire_all()

        assert test_session.query(EndpointModel).filter_by(slug="ep-0").count() == 0
        kept = test_session.query(EndpointModel).filter_by(slug="ep-1").one()
        assert kept.space_id == ref_b.id
        assert kept.is_active is True

    def test_deleting_a_satellite_with_no_endpoints(self, service, users):
        """Test the ordinary case."""
        created = _create(service, users[0].id)
        service.delete_satellite(users[0].id, created.id)
        assert service.list_satellites(users[0].id) == []


class TestGraduatedResolution:
    """The rule every write path in 1c will share."""

    def test_zero_satellites_registers_one_from_the_reported_url(self, service, users):
        """Test the 0 branch — a brand new account reporting in."""
        ref = service.resolve(users[0].id, reported_url="https://new.example.com")
        assert ref.base_url.value == "https://new.example.com"
        assert ref.kind is SatelliteKind.SPACE
        assert len(service.list_satellites(users[0].id)) == 1

    def test_zero_satellites_without_a_url_is_refused(self, service, users):
        """Test that resolution never invents a satellite out of nothing."""
        with pytest.raises(ValidationError):
            service.resolve(users[0].id)

    def test_one_satellite_is_used(self, service, users):
        """Test the 1 branch — every existing account today."""
        created = _create(service, users[0].id)
        ref = service.resolve(users[0].id)
        assert ref.public_id == created.id

    def test_one_satellite_is_used_even_with_a_different_url(self, service, users):
        """Test that a moved space still resolves to its own satellite.

        The rule picks by count, not by URL match, which is what lets a space
        change origin without splitting into two satellites.
        """
        created = _create(service, users[0].id, base_url="https://old.example.com")
        ref = service.resolve(users[0].id, reported_url="https://new.example.com")
        assert ref.public_id == created.id
        assert len(service.list_satellites(users[0].id)) == 1

    def test_two_satellites_without_a_choice_is_ambiguous(self, service, users):
        """Test the 2+ branch — the intended forcing function."""
        _create(service, users[0].id, base_url="https://a.example.com")
        _create(service, users[0].id, base_url="https://b.example.com")

        with pytest.raises(AmbiguousSatelliteError) as exc:
            service.resolve(users[0].id, reported_url="https://a.example.com")
        assert exc.value.count == 2
        assert "satellite_id" in str(exc.value), "must name the remedy"

    def test_ambiguity_is_a_422(self, service, users):
        """Test that ambiguity is a client error, not a server error."""
        from syfthub.observability.handlers import _get_domain_exception_status

        _create(service, users[0].id, base_url="https://a.example.com")
        _create(service, users[0].id, base_url="https://b.example.com")
        with pytest.raises(AmbiguousSatelliteError) as exc:
            service.resolve(users[0].id)
        assert _get_domain_exception_status(exc.value) == 422

    def test_explicit_id_wins_over_the_count(self, service, users):
        """Test that naming a satellite resolves even when 2+ exist."""
        a = _create(service, users[0].id, base_url="https://a.example.com")
        _create(service, users[0].id, base_url="https://b.example.com")

        ref = service.resolve(users[0].id, satellite_id=a.id)
        assert ref.public_id == a.id

    def test_explicit_id_must_belong_to_the_caller(self, service, users):
        """Test that a satellite cannot be written to across accounts."""
        created = _create(service, users[0].id)
        _create(service, users[1].id, base_url="https://t.example.com")

        with pytest.raises(NotFoundError):
            service.resolve(users[1].id, satellite_id=created.id)

    def test_explicit_unknown_id_is_not_found(self, service, users):
        """Test that an unknown identifier does not silently fall through."""
        _create(service, users[0].id)
        with pytest.raises(NotFoundError):
            service.resolve(users[0].id, satellite_id=uuid.uuid4())

    def test_resolution_is_scoped_per_account(self, service, users):
        """Test that another account's satellites do not create ambiguity."""
        _create(service, users[1].id, base_url="https://a.example.com")
        _create(service, users[1].id, base_url="https://b.example.com")

        ref = service.resolve(users[0].id, reported_url="https://mine.example.com")
        assert ref.user_id == users[0].id

    def test_registering_a_station_via_resolve(self, service, users):
        """Test that the created kind is the caller's to choose."""
        ref = service.resolve(
            users[0].id,
            reported_url="https://station.example.com",
            kind=SatelliteKind.STATION,
        )
        assert ref.kind is SatelliteKind.STATION
