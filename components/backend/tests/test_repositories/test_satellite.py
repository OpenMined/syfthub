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


class TestRegister:
    """Registration is the write that replaces users.domain."""

    def test_registers_a_space(self, repo, users):
        """Test that a space comes back fully identified."""
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="my-space",
            base_url=BaseUrl("https://space.example.com"),
        )
        assert ref.id > 0
        assert isinstance(ref.public_id, uuid.UUID)
        assert ref.user_id == users[0].id
        assert ref.kind is SatelliteKind.SPACE
        assert ref.slug == "my-space"
        assert ref.base_url == BaseUrl("https://space.example.com")

    def test_registers_a_station_without_a_base_url(self, repo, users):
        """Test that a station needs no origin."""
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.STATION,
            slug="my-station",
            base_url=None,
        )
        assert ref.kind is SatelliteKind.STATION
        assert ref.base_url is None

    def test_stores_the_canonical_origin(self, repo, users):
        """Test that what lands in the column is already normalised."""
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("  HTTPS://Space.Example.COM:443/v1/  "),
        )
        assert ref.base_url is not None
        assert ref.base_url.value == "https://space.example.com"

    def test_public_ids_are_distinct(self, repo, users):
        """Test that each satellite gets its own exposed identifier."""
        ids = {
            repo.register(
                user_id=users[0].id,
                kind=SatelliteKind.SPACE,
                slug=f"s{i}",
                base_url=BaseUrl(f"https://s{i}.example.com"),
            ).public_id
            for i in range(3)
        }
        assert len(ids) == 3

    def test_duplicate_slug_conflicts(self, repo, users):
        """Test that a slug is unique per account."""
        repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="dup",
            base_url=None,
        )
        with pytest.raises(ConflictError):
            repo.register(
                user_id=users[0].id,
                kind=SatelliteKind.SPACE,
                slug="dup",
                base_url=None,
            )

    def test_duplicate_base_url_conflicts(self, repo, users):
        """Test that one account cannot register the same origin twice."""
        repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="a",
            base_url=BaseUrl("https://same.example.com"),
        )
        with pytest.raises(ConflictError):
            repo.register(
                user_id=users[0].id,
                kind=SatelliteKind.SPACE,
                slug="b",
                base_url=BaseUrl("https://same.example.com"),
            )

    def test_duplicate_base_url_across_spellings_conflicts(self, repo, users):
        """Test that the conflict survives a different spelling of one origin."""
        repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="a",
            base_url=BaseUrl("https://same.example.com"),
        )
        with pytest.raises(ConflictError):
            repo.register(
                user_id=users[0].id,
                kind=SatelliteKind.SPACE,
                slug="b",
                base_url=BaseUrl("HTTPS://Same.Example.com:443/"),
            )

    def test_same_slug_across_accounts_is_fine(self, repo, users):
        """Test that slugs are account-scoped, which the backfill relies on."""
        for user in users:
            repo.register(
                user_id=user.id,
                kind=SatelliteKind.SPACE,
                slug="shared-slug",
                base_url=None,
            )
        assert len(repo.list_for_user(users[0].id)) == 1
        assert len(repo.list_for_user(users[1].id)) == 1

    def test_many_satellites_without_a_base_url_coexist(self, repo, users):
        """Test that NULL origins do not collide under the unique index."""
        for i in range(3):
            repo.register(
                user_id=users[0].id,
                kind=SatelliteKind.STATION,
                slug=f"stn{i}",
                base_url=None,
            )
        assert len(repo.list_for_user(users[0].id)) == 3

    def test_recovers_after_a_conflict(self, repo, users):
        """Test that the session survives a conflict; without the rollback every
        later write would fail on a poisoned transaction."""
        repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="x", base_url=None
        )
        with pytest.raises(ConflictError):
            repo.register(
                user_id=users[0].id, kind=SatelliteKind.SPACE, slug="x", base_url=None
            )
        ref = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="y", base_url=None
        )
        assert ref.slug == "y"


class TestLookups:
    """Reads are scoped by owner so they cannot be used to probe."""

    def test_get_by_public_id(self, repo, users):
        """Test fetching by the exposed identifier."""
        created = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        found = repo.get_by_public_id(users[0].id, created.public_id)
        assert found == created

    def test_get_by_public_id_is_owner_scoped(self, repo, users):
        """Test that another account's satellite reads as absent, not found."""
        created = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="s", base_url=None
        )
        assert repo.get_by_public_id(users[1].id, created.public_id) is None

    def test_get_by_unknown_public_id(self, repo, users):
        """Test that an unknown identifier returns None rather than raising."""
        assert repo.get_by_public_id(users[0].id, uuid.uuid4()) is None

    def test_find_by_base_url(self, repo, users):
        """Test resolution by origin, the heartbeat path's lookup."""
        created = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        found = repo.find_by_base_url(users[0].id, BaseUrl("https://s.example.com"))
        assert found == created

    def test_find_by_base_url_matches_across_spellings(self, repo, users):
        """Test that a differently-spelled origin resolves to the same row, so a
        space reporting "https://S.Example.com/" makes no second satellite."""
        created = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        found = repo.find_by_base_url(
            users[0].id, BaseUrl("  HTTPS://S.Example.com:443/v1/  ")
        )
        assert found == created

    def test_find_by_base_url_is_owner_scoped(self, repo, users):
        """Test that one account cannot resolve another's origin."""
        repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
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
        first = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="a", base_url=None
        )
        second = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="b", base_url=None
        )
        repo.register(
            user_id=users[1].id, kind=SatelliteKind.SPACE, slug="c", base_url=None
        )

        listed = repo.list_for_user(users[0].id)
        assert [s.slug for s in listed] == ["a", "b"]
        assert listed == [first, second]


class TestWrites:
    """The heartbeat writes that replace the users.domain update."""

    def test_set_base_url(self, repo, users):
        """Test recording an origin reported after registration."""
        ref = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="s", base_url=None
        )
        repo.set_base_url(ref.id, BaseUrl("https://reported.example.com"))

        updated = repo.get_by_public_id(users[0].id, ref.public_id)
        assert updated is not None
        assert updated.base_url == BaseUrl("https://reported.example.com")

    def test_set_base_url_records_last_seen(self, repo, users, test_session):
        """Test that reporting an origin also counts as being seen."""
        ref = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="s", base_url=None
        )
        repo.set_base_url(ref.id, BaseUrl("https://s.example.com"))

        model = repo.get_by_id(ref.id)
        assert model is not None
        assert model.last_seen_at is not None

    def test_set_base_url_is_idempotent(self, repo, users):
        """Test that a repeated heartbeat is not a conflict."""
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        for _ in range(3):
            repo.set_base_url(ref.id, BaseUrl("https://s.example.com"))

        assert len(repo.list_for_user(users[0].id)) == 1

    def test_two_satellites_do_not_overwrite_each_other(self, repo, users):
        """Test the bug this table exists to fix: with users.domain, two spaces
        overwrote each other on every heartbeat."""
        a = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="a",
            base_url=BaseUrl("https://a.example.com"),
        )
        b = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="b",
            base_url=BaseUrl("https://b.example.com"),
        )
        repo.set_base_url(a.id, BaseUrl("https://a2.example.com"))
        repo.set_base_url(b.id, BaseUrl("https://b2.example.com"))

        by_slug = {s.slug: s.base_url for s in repo.list_for_user(users[0].id)}
        assert by_slug["a"] == BaseUrl("https://a2.example.com")
        assert by_slug["b"] == BaseUrl("https://b2.example.com")

    def test_set_base_url_conflicts_with_a_sibling(self, repo, users):
        """Test that a satellite cannot steal a sibling's origin."""
        repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="a",
            base_url=BaseUrl("https://a.example.com"),
        )
        b = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="b",
            base_url=BaseUrl("https://b.example.com"),
        )
        with pytest.raises(ConflictError):
            repo.set_base_url(b.id, BaseUrl("https://a.example.com"))

    def test_set_base_url_on_a_missing_satellite_is_a_no_op(self, repo, users):
        """Test that a vanished satellite does not raise."""
        repo.set_base_url(9999, BaseUrl("https://gone.example.com"))

    def test_touch_last_seen(self, repo, users):
        """Test a heartbeat that reports no origin change."""
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        repo.touch_last_seen(ref.id)

        model = repo.get_by_id(ref.id)
        assert model is not None
        assert model.last_seen_at is not None
        assert model.base_url == "https://s.example.com"

    def test_touch_last_seen_on_a_missing_satellite_is_a_no_op(self, repo):
        """Test that a vanished satellite does not raise."""
        repo.touch_last_seen(9999)


class TestCascade:
    """Deleting a user removes their satellites; deleting a satellite does not
    remove their endpoints."""

    def test_deleting_a_user_removes_their_satellites(self, repo, users, test_session):
        """Test that satellites are owned, per the cascade on the relationship."""
        repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="s", base_url=None
        )
        test_session.delete(test_session.get(UserModel, users[0].id))
        test_session.commit()

        assert repo.list_for_user(users[0].id) == []

    def test_deleting_a_satellite_orphans_its_endpoints(
        self, repo, users, test_session, sample_endpoint_data
    ):
        """Test that endpoints survive their space being deleted.

        The orphan-on-delete invariant: catalogue entries and the addresses
        buyers hold must not vanish when an operator tears down a space.
        """
        ref = repo.register(
            user_id=users[0].id,
            kind=SatelliteKind.SPACE,
            slug="s",
            base_url=BaseUrl("https://s.example.com"),
        )
        endpoint = EndpointModel(
            **{**sample_endpoint_data, "user_id": users[0].id, "space_id": ref.id}
        )
        test_session.add(endpoint)
        test_session.commit()
        endpoint_id = endpoint.id

        test_session.delete(repo.get_by_id(ref.id))
        test_session.commit()
        test_session.expire_all()

        survivor = test_session.get(EndpointModel, endpoint_id)
        assert survivor is not None, "endpoint was destroyed with its satellite"
        assert survivor.space_id is None, (
            "orphaned endpoint still points at a satellite"
        )

    def test_deleting_a_user_removes_both(
        self, repo, users, test_session, sample_endpoint_data
    ):
        """Test that orphan-on-delete does not keep endpoints alive past their
        owner."""
        ref = repo.register(
            user_id=users[0].id, kind=SatelliteKind.SPACE, slug="s", base_url=None
        )
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
