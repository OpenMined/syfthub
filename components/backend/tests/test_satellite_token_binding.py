"""Phase 2 — a satellite token names a satellite, not an account.

Under the old scheme `aud` was the owner's username, which identified a service
only while an account ran exactly one host. These cover what changes once it
does not: S9 (a token cannot be minted for a host its supposed owner does not
run) and S10 (a token for one of an account's hosts is rejected at another).
"""

from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from syfthub.auth.keys import RSAKeyManager
from syfthub.main import app


@pytest.fixture(autouse=True)
def configured_keys():
    """Give the IdP a signing key; minting is 503 without one."""
    RSAKeyManager._instance = None
    manager = RSAKeyManager()
    manager._generate_keypair("test-binding-key")
    # The routes hold the module-level singleton; satellite_tokens receives it
    # as an argument, so only the route module needs patching.
    with patch("syfthub.api.endpoints.token.key_manager", manager):
        yield manager
    RSAKeyManager._instance = None


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    client = TestClient(app)
    yield client
    drop_tables()


def register(client: TestClient, username: str) -> dict:
    """Register a user and return an Authorization header."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": username.title(),
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_satellite(client, headers, base_url, kind="space") -> str:
    """Register a satellite and return its public id."""
    response = client.post(
        "/api/v1/satellites",
        headers=headers,
        json={"kind": kind, "base_url": base_url},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def claims(token: str) -> dict:
    """The token's payload, without verifying (tests assert on aud)."""
    return jwt.decode(token, options={"verify_signature": False}, audience=None)


class TestMintBindsToASatellite:
    """`aud` carries the satellite, so a receiver checks an id it owns."""

    def test_aud_is_the_satellite_not_the_username(self, client: TestClient):
        """Test the core change."""
        alice = register(client, "alice")
        satellite = add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"

        bob = register(client, "bob")
        response = client.get(
            "/api/v1/token",
            headers=bob,
            params={"owner_username": owner, "resource": "https://alice.example.com"},
        )

        assert response.status_code == 200, response.text
        assert claims(response.json()["target_token"])["aud"] == satellite

    def test_the_destination_path_is_ignored(self, client: TestClient):
        """Test that only the origin matters, as the caller sends a full URL."""
        alice = register(client, "alice")
        satellite = add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"
        bob = register(client, "bob")

        response = client.get(
            "/api/v1/token",
            headers=bob,
            params={
                "owner_username": owner,
                "resource": "https://alice.example.com/api/v1/credits/w-1/balance",
            },
        )

        assert response.status_code == 200, response.text
        assert claims(response.json()["target_token"])["aud"] == satellite

    def test_two_hosts_of_one_account_mint_different_audiences(
        self, client: TestClient
    ):
        """Test the case the username form could not express."""
        alice = register(client, "alice")
        space = add_satellite(client, alice, "https://space.example.com")
        station = add_satellite(
            client, alice, "https://station.example.com", kind="station"
        )
        owner = "alice"
        bob = register(client, "bob")

        def mint(dest):
            r = client.get(
                "/api/v1/token",
                headers=bob,
                params={"owner_username": owner, "resource": dest},
            )
            assert r.status_code == 200, r.text
            return claims(r.json()["target_token"])["aud"]

        assert mint("https://space.example.com") == space
        assert mint("https://station.example.com") == station
        assert space != station

    def test_guest_tokens_bind_the_same_way(self, client: TestClient):
        """Test that the guest path inherits the binding.

        Both paths share one minting function, so this is really a check that
        nobody added a second one.
        """
        alice = register(client, "alice")
        satellite = add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"

        response = client.get(
            "/api/v1/token/guest",
            params={"owner_username": owner, "resource": "https://alice.example.com"},
        )

        assert response.status_code == 200, response.text
        payload = claims(response.json()["target_token"])
        assert payload["aud"] == satellite
        assert payload["sub"] == "guest"


class TestUnknownDestinationIsRefused:
    """S9 — the security property. No token is minted, so none can be stolen."""

    def test_a_host_the_owner_does_not_run_is_refused(self, client: TestClient):
        """Test the confused-deputy case directly.

        A publisher naming `credits_url = https://evil.example.com` with
        `wallet_owner = alice` gets nothing: the URL resolves inside *alice's*
        satellites and is not there.
        """
        alice = register(client, "alice")
        add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"
        bob = register(client, "bob")

        response = client.get(
            "/api/v1/token",
            headers=bob,
            params={"owner_username": owner, "resource": "https://evil.example.com"},
        )

        assert response.status_code == 422, response.text
        assert "no registered satellite" in response.text.lower()

    def test_another_accounts_host_does_not_count(self, client: TestClient):
        """Test that resolution is scoped to the named owner.

        Naming alice as owner but carol's host must not mint: the token would
        say "for alice" while being delivered to carol.
        """
        alice = register(client, "alice")
        add_satellite(client, alice, "https://alice.example.com")
        carol = register(client, "carol")
        add_satellite(client, carol, "https://carol.example.com")
        owner = "alice"
        bob = register(client, "bob")

        response = client.get(
            "/api/v1/token",
            headers=bob,
            params={"owner_username": owner, "resource": "https://carol.example.com"},
        )

        assert response.status_code == 422

    def test_an_unknown_owner_is_refused(self, client: TestClient):
        """Test that a fabricated owner id yields nothing."""
        bob = register(client, "bob")
        response = client.get(
            "/api/v1/token",
            headers=bob,
            params={
                "owner_username": "nobody-here",
                "resource": "https://anything.example.com",
            },
        )
        assert response.status_code in (400, 404), response.text

    def test_naming_no_audience_at_all_is_refused(self, client: TestClient):
        """Test that a token always names something."""
        bob = register(client, "bob")
        response = client.get("/api/v1/token", headers=bob)
        assert response.status_code == 400


class TestLegacyAudAlias:
    """`?aud=<username>` still works, because the published SDK sends it."""

    def test_alias_resolves_to_the_accounts_one_satellite(self, client: TestClient):
        """Test the compatibility path."""
        alice = register(client, "alice")
        satellite = add_satellite(client, alice, "https://alice.example.com")
        bob = register(client, "bob")

        response = client.get("/api/v1/token", headers=bob, params={"aud": "alice"})

        assert response.status_code == 200, response.text
        assert claims(response.json()["target_token"])["aud"] == satellite

    def test_alias_is_ambiguous_once_the_account_runs_two(self, client: TestClient):
        """Test that the alias refuses rather than guessing.

        It names the account, not a host. With two it cannot mean one of them,
        and picking either would hand out a token for the wrong destination.
        """
        alice = register(client, "alice")
        add_satellite(client, alice, "https://space.example.com")
        add_satellite(client, alice, "https://station.example.com", kind="station")
        bob = register(client, "bob")

        response = client.get("/api/v1/token", headers=bob, params={"aud": "alice"})

        assert response.status_code == 422, response.text
        assert "satellite_id" in response.text

    def test_alias_for_an_account_with_no_satellite_is_refused(
        self, client: TestClient
    ):
        """Test that there is nothing to bind to."""
        register(client, "alice")
        bob = register(client, "bob")
        response = client.get("/api/v1/token", headers=bob, params={"aud": "alice"})
        assert response.status_code in (400, 404), response.text


class TestVerifyIsAMembershipTest:
    """S10 — and the reason /verify must not use the resolution rule."""

    def _mint_for(self, client, minter_headers, owner_username, dest) -> str:
        r = client.get(
            "/api/v1/token",
            headers=minter_headers,
            params={"owner_username": owner_username, "resource": dest},
        )
        assert r.status_code == 200, r.text
        return r.json()["target_token"]

    def test_a_token_for_your_satellite_verifies(self, client: TestClient):
        """Test the ordinary case."""
        alice = register(client, "alice")
        add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://alice.example.com")
        response = client.post("/api/v1/verify", headers=alice, json={"token": token})

        assert response.status_code == 200, response.text
        assert response.json()["valid"] is True

    def test_two_satellites_do_not_make_verification_ambiguous(
        self, client: TestClient
    ):
        """Test why this is a membership test and not `resolve`.

        An account running a station alongside a space owns two satellites.
        Resolving would refuse — on the credit-verification path — for a
        question the token had already answered.
        """
        alice = register(client, "alice")
        add_satellite(client, alice, "https://space.example.com")
        add_satellite(client, alice, "https://station.example.com", kind="station")
        owner = "alice"
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://station.example.com")
        response = client.post("/api/v1/verify", headers=alice, json={"token": token})

        assert response.status_code == 200, response.text
        assert response.json()["valid"] is True

    def test_another_accounts_token_is_rejected(self, client: TestClient):
        """Test that a caller cannot verify a token addressed elsewhere."""
        alice = register(client, "alice")
        add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"
        carol = register(client, "carol")
        add_satellite(client, carol, "https://carol.example.com")
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://alice.example.com")
        response = client.post("/api/v1/verify", headers=carol, json={"token": token})

        assert response.json()["valid"] is False

    def test_cross_host_replay_within_one_account_is_rejected(self, client: TestClient):
        """Test S10, the case the username form allowed.

        A token minted for alice's space, presented at alice's station with the
        station named, must fail. Under `aud = "alice"` it would have passed.
        """
        alice = register(client, "alice")
        add_satellite(client, alice, "https://space.example.com")
        station = add_satellite(
            client, alice, "https://station.example.com", kind="station"
        )
        owner = "alice"
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://space.example.com")
        response = client.post(
            "/api/v1/verify",
            headers=alice,
            json={"token": token, "satellite_id": station},
        )

        assert response.json()["valid"] is False, (
            "a token for the space must not verify at the station"
        )
        assert response.json()["error"] == "audience_mismatch"

    def test_naming_the_right_satellite_verifies(self, client: TestClient):
        """Test the other half: the strict check passes when it should."""
        alice = register(client, "alice")
        space = add_satellite(client, alice, "https://space.example.com")
        add_satellite(client, alice, "https://station.example.com", kind="station")
        owner = "alice"
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://space.example.com")
        response = client.post(
            "/api/v1/verify",
            headers=alice,
            json={"token": token, "satellite_id": space},
        )

        assert response.json()["valid"] is True, response.text

    def test_a_satellite_id_you_do_not_own_is_refused(self, client: TestClient):
        """Test that the strict branch is owner-scoped."""
        alice = register(client, "alice")
        add_satellite(client, alice, "https://alice.example.com")
        owner = "alice"
        carol = register(client, "carol")
        carol_sat = add_satellite(client, carol, "https://carol.example.com")
        bob = register(client, "bob")

        token = self._mint_for(client, bob, owner, "https://alice.example.com")
        response = client.post(
            "/api/v1/verify",
            headers=alice,
            json={"token": token, "satellite_id": carol_sat},
        )

        assert response.status_code == 404
