"""Tests for SatelliteRepository."""

import uuid

import pytest
from tests.test_utils import get_test_user_model_data

from syfthub.domain.base_url import BaseUrl
from syfthub.domain.exceptions import ConflictError
from syfthub.domain.satellite import SatelliteKind
from syfthub.models.endpoint import EndpointModel
from syfthub.models.user import UserModel
from syfthub.repositories.satellite import SatelliteRepository


@pytest.fixture
def repo(test_session):
    """A satellite repository bound to the test session."""
    return SatelliteRepository(test_session)


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


def _register(repo, user_id, url="https://s.example.com", kind=SatelliteKind.SPACE):
    """Register a satellite at an origin."""
    return repo.register(user_id=user_id, kind=kind, base_url=BaseUrl(url))


class TestRegister:
    """Registration is the write that replaces users.domain."""

    def test_registers_a_space(self, repo, users):
        """Test that a space comes back fully identified."""
        ref = _register(repo, users[0].id)
        assert ref.id > 0
        assert isinstance(ref.public_id, uuid.UUID)
        assert ref.user_id == users[0].id
        assert ref.kind is SatelliteKind.SPACE
        assert ref.base_url == BaseUrl("https://s.example.com")
        assert ref.created_at is not None
        assert ref.last_seen_at is None

    def test_registers_a_station(self, repo, users):
        """Test that a station is an ordinary satellite with a kind."""
        ref = _register(
            repo,
            users[0].id,
            url="https://station.example.com",
            kind=SatelliteKind.STATION,
        )
        assert ref.kind is SatelliteKind.STATION
        assert ref.base_url == BaseUrl("https://station.example.com")

    def test_stores_the_canonical_origin(self, repo, users):
        """Test that what lands in the column is already normalised."""
        ref = _register(repo, users[0].id, url="  HTTPS://Space.Example.COM:443/v1/  ")
        assert ref.base_url is not None
        assert ref.base_url.value == "https://space.example.com"

    def test_public_ids_are_distinct(self, repo, users):
        """Test that each satellite gets its own exposed identifier.

        With no name field, this is the only thing telling two apart.
        """
        ids = {
            _register(repo, users[0].id, url=f"https://s{i}.example.com").public_id
            for i in range(3)
        }
        assert len(ids) == 3

    def test_duplicate_origin_conflicts(self, repo, users):
        """Test that one host is exactly one satellite per account."""
        _register(repo, users[0].id, url="https://same.example.com")
        with pytest.raises(ConflictError):
            _register(repo, users[0].id, url="https://same.example.com")

    def test_duplicate_origin_across_spellings_conflicts(self, repo, users):
        """Test that the conflict survives a different spelling of one origin."""
        _register(repo, users[0].id, url="https://same.example.com")
        with pytest.raises(ConflictError):
            _register(repo, users[0].id, url="HTTPS://Same.Example.com:443/")

    def test_same_origin_across_accounts_is_fine(self, repo, users):
        """Test that uniqueness is per account, not global.

        Squatting is pointless: resolution only ever looks inside the caller's
        own satellites.
        """
        for user in users:
            _register(repo, user.id, url="https://shared.example.com")
        assert len(repo.list_for_user(users[0].id)) == 1
        assert len(repo.list_for_user(users[1].id)) == 1

    def test_recovers_after_a_conflict(self, repo, users):
        """Test that the session survives a conflict; without the rollback every
        later write would fail on a poisoned transaction."""
        _register(repo, users[0].id, url="https://a.example.com")
        with pytest.raises(ConflictError):
            _register(repo, users[0].id, url="https://a.example.com")
        ref = _register(repo, users[0].id, url="https://b.example.com")
        assert ref.base_url == BaseUrl("https://b.example.com")


class TestLookups:
    """Reads are scoped by owner so they cannot be used to probe."""

    def test_get_by_public_id(self, repo, users):
        """Test fetching by the exposed identifier."""
        created = _register(repo, users[0].id)
        assert repo.get_by_public_id(users[0].id, created.public_id) == created

    def test_get_by_public_id_is_owner_scoped(self, repo, users):
        """Test that another account's satellite reads as absent, not found."""
        created = _register(repo, users[0].id)
        assert repo.get_by_public_id(users[1].id, created.public_id) is None

    def test_get_by_unknown_public_id(self, repo, users):
        """Test that an unknown identifier returns None rather than raising."""
        assert repo.get_by_public_id(users[0].id, uuid.uuid4()) is None

    def test_find_by_base_url(self, repo, users):
        """Test resolution by origin, the heartbeat path's lookup."""
        created = _register(repo, users[0].id)
        found = repo.find_by_base_url(users[0].id, BaseUrl("https://s.example.com"))
        assert found == created

    def test_find_by_base_url_matches_across_spellings(self, repo, users):
        """Test that a differently-spelled origin resolves to the same row, so a
        space reporting "https://S.Example.com/" makes no second satellite."""
        created = _register(repo, users[0].id)
        found = repo.find_by_base_url(
            users[0].id, BaseUrl("  HTTPS://S.Example.com:443/v1/  ")
        )
        assert found == created

    def test_find_by_base_url_is_owner_scoped(self, repo, users):
        """Test that one account cannot resolve another's origin."""
        _register(repo, users[0].id)
        assert (
            repo.find_by_base_url(users[1].id, BaseUrl("https://s.example.com")) is None
        )

    def test_find_by_unknown_base_url(self, repo, users):
        """Test that an unregistered origin returns None."""
        assert (
            repo.find_by_base_url(users[0].id, BaseUrl("https://nope.example.com"))
            is None
        )

    def test_list_for_user_is_empty_by_default(self, repo, users):
        """Test the zero branch the graduated rule depends on."""
        assert repo.list_for_user(users[0].id) == []

    def test_list_for_user_is_ordered_and_scoped(self, repo, users):
        """Test a stable order, keeping the one-satellite branch determinate."""
        first = _register(repo, users[0].id, url="https://a.example.com")
        second = _register(repo, users[0].id, url="https://b.example.com")
        _register(repo, users[1].id, url="https://c.example.com")

        assert repo.list_for_user(users[0].id) == [first, second]


class TestWrites:
    """The heartbeat and reconfiguration writes."""

    def test_set_base_url(self, repo, users):
        """Test recording a newly reported origin."""
        ref = _register(repo, users[0].id)
        repo.set_base_url(ref.id, BaseUrl("https://reported.example.com"))

        updated = repo.get_by_public_id(users[0].id, ref.public_id)
        assert updated is not None
        assert updated.base_url == BaseUrl("https://reported.example.com")

    def test_set_base_url_records_last_seen(self, repo, users):
        """Test that reporting an origin also counts as being seen."""
        ref = _register(repo, users[0].id)
        repo.set_base_url(ref.id, BaseUrl("https://s.example.com"))

        model = repo.get_by_id(ref.id)
        assert model is not None
        assert model.last_seen_at is not None

    def test_set_base_url_is_idempotent(self, repo, users):
        """Test that a repeated heartbeat is not a conflict."""
        ref = _register(repo, users[0].id)
        for _ in range(3):
            repo.set_base_url(ref.id, BaseUrl("https://s.example.com"))
        assert len(repo.list_for_user(users[0].id)) == 1

    def test_two_satellites_do_not_overwrite_each_other(self, repo, users):
        """Test the bug this table exists to fix: with users.domain, two spaces
        overwrote each other on every heartbeat."""
        a = _register(repo, users[0].id, url="https://a.example.com")
        b = _register(repo, users[0].id, url="https://b.example.com")
        repo.set_base_url(a.id, BaseUrl("https://a2.example.com"))
        repo.set_base_url(b.id, BaseUrl("https://b2.example.com"))

        by_id = {s.public_id: s.base_url for s in repo.list_for_user(users[0].id)}
        assert by_id[a.public_id] == BaseUrl("https://a2.example.com")
        assert by_id[b.public_id] == BaseUrl("https://b2.example.com")

    def test_set_base_url_conflicts_with_a_sibling(self, repo, users):
        """Test that a satellite cannot steal a sibling's origin."""
        _register(repo, users[0].id, url="https://a.example.com")
        b = _register(repo, users[0].id, url="https://b.example.com")
        with pytest.raises(ConflictError):
            repo.set_base_url(b.id, BaseUrl("https://a.example.com"))

    def test_set_base_url_on_a_missing_satellite_is_a_no_op(self, repo, users):
        """Test that a vanished satellite does not raise."""
        repo.set_base_url(9999, BaseUrl("https://gone.example.com"))

    def test_move_keeps_identity(self, repo, users):
        """Test that reconfiguring an origin preserves the identifier.

        This is why the identifier is a surrogate: a space can change host
        without its endpoints or outstanding tokens losing their anchor.
        """
        ref = _register(repo, users[0].id)
        moved = repo.move(ref.id, BaseUrl("https://moved.example.com"))
        assert moved is not None
        assert moved.public_id == ref.public_id
        assert moved.id == ref.id
        assert moved.base_url == BaseUrl("https://moved.example.com")

    def test_move_does_not_stamp_last_seen(self, repo, users):
        """Test that reconfiguration is not a heartbeat."""
        ref = _register(repo, users[0].id)
        repo.move(ref.id, BaseUrl("https://moved.example.com"))

        model = repo.get_by_id(ref.id)
        assert model is not None
        assert model.last_seen_at is None

    def test_move_conflicts_with_a_sibling(self, repo, users):
        """Test that a move cannot collide with another satellite."""
        _register(repo, users[0].id, url="https://a.example.com")
        b = _register(repo, users[0].id, url="https://b.example.com")
        with pytest.raises(ConflictError):
            repo.move(b.id, BaseUrl("https://a.example.com"))

    def test_move_on_a_missing_satellite_returns_none(self, repo):
        """Test that a vanished satellite is reported, not raised."""
        assert repo.move(9999, BaseUrl("https://gone.example.com")) is None

    def test_touch_last_seen(self, repo, users):
        """Test a heartbeat that reports no origin change."""
        ref = _register(repo, users[0].id)
        repo.touch_last_seen(ref.id)

        model = repo.get_by_id(ref.id)
        assert model is not None
        assert model.last_seen_at is not None
        assert model.base_url == "https://s.example.com"

    def test_touch_last_seen_on_a_missing_satellite_is_a_no_op(self, repo):
        """Test that a vanished satellite does not raise."""
        repo.touch_last_seen(9999)


class TestCascade:
    """Deleting a user removes their satellites, which removes their endpoints."""

    def test_deleting_a_user_removes_their_satellites(self, repo, users, test_session):
        """Test that satellites are owned, per the cascade on the relationship."""
        _register(repo, users[0].id)
        test_session.delete(test_session.get(UserModel, users[0].id))
        test_session.commit()

        assert repo.list_for_user(users[0].id) == []

    def test_deleting_a_satellite_deletes_its_endpoints(
        self, repo, users, test_session, sample_endpoint_data
    ):
        """Test that the FK cascade removes what the satellite served."""
        ref = _register(repo, users[0].id)
        endpoint = EndpointModel(
            **{**sample_endpoint_data, "user_id": users[0].id, "space_id": ref.id}
        )
        test_session.add(endpoint)
        test_session.commit()
        endpoint_id = endpoint.id

        test_session.delete(repo.get_by_id(ref.id))
        test_session.commit()
        test_session.expire_all()

        assert test_session.get(EndpointModel, endpoint_id) is None

    def test_deleting_a_user_removes_both(
        self, repo, users, test_session, sample_endpoint_data
    ):
        """Test that deleting the owner removes satellites and endpoints."""
        ref = _register(repo, users[0].id)
        endpoint = EndpointModel(
            **{**sample_endpoint_data, "user_id": users[0].id, "space_id": ref.id}
        )
        test_session.add(endpoint)
        test_session.commit()
        endpoint_id = endpoint.id

        test_session.delete(test_session.get(UserModel, users[0].id))
        test_session.commit()

        assert repo.list_for_user(users[0].id) == []
        assert test_session.get(EndpointModel, endpoint_id) is None
