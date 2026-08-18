"""End-to-end tests for the verified email-change flow.

An email address is a credential here, so changing one lives beside
``PUT /auth/me/password`` rather than on ``PUT /users/me``. These tests pin both
halves of that contract: the profile endpoint refuses to change an address, and
``/auth/me/email`` only moves it once a code sent to the new address is verified.
"""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app
from syfthub.services.email_change_service import EMAIL_CHANGE_PURPOSE


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Test client against a clean database."""
    from syfthub.database.connection import create_tables, drop_tables

    drop_tables()
    create_tables()
    yield TestClient(app)
    drop_tables()


@pytest.fixture(autouse=True)
def reset_auth_data() -> None:
    """Clear the token blacklist between tests."""
    token_blacklist.clear()


def _register(client: TestClient, username: str, *, role: str | None = None) -> str:
    """Register a user and return their access token."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": f"{username.title()} User",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text

    if role == "admin":
        from syfthub.database.connection import SessionLocal
        from syfthub.models.user import UserModel

        session = SessionLocal()
        try:
            user = session.query(UserModel).filter(UserModel.username == username).one()
            user.role = "admin"
            session.commit()
        finally:
            session.close()

    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user_id(client: TestClient, token: str) -> int:
    return int(client.get("/api/v1/auth/me", headers=_auth(token)).json()["id"])


def _registration_code(email: str) -> str:
    """Recover the registration-purpose code minted by an admin's change."""
    return _code_for(email, "registration")


def _pending_code(pending_email: str) -> str:
    """Recover the OTP minted for a pending address.

    The code only ever leaves by email, so a test has to reach into the OTP
    store. Codes are hashed at rest, so brute-force the 6-digit space against
    the stored hash rather than trying to read a plaintext that does not exist.
    """

    return _code_for(pending_email, EMAIL_CHANGE_PURPOSE)


def _code_for(email: str, purpose: str) -> str:
    """Brute-force a hashed OTP back out of the store for the given purpose."""
    from syfthub.database.connection import SessionLocal
    from syfthub.repositories.otp import OTPRepository
    from syfthub.services.otp_service import _hash_code

    session = SessionLocal()
    try:
        otp = OTPRepository(session).get_active_otp(email, purpose)
        assert otp is not None, f"no active {purpose} OTP for {email}"
        for candidate in range(1_000_000):
            code = f"{candidate:06d}"
            if _hash_code(code) == otp.code_hash:
                return code
        raise AssertionError("could not recover the OTP code")
    finally:
        session.close()


class TestProfileEndpointRefusesEmailChanges:
    """PUT /users/me cannot change an address, and says where to go instead."""

    def test_a_different_address_is_rejected(self, client: TestClient) -> None:
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "EMAIL_NOT_UPDATABLE_HERE"
        assert "/auth/me/email" in detail["message"]

    def test_nothing_changes_on_the_account(self, client: TestClient) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["email"] == "alice@example.com"
        assert me["pending_email"] is None
        assert me["is_email_verified"] is True

    def test_the_unchanged_address_passes_through(self, client: TestClient) -> None:
        """A client round-tripping a whole user object must still work."""
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/users/me",
            json={"email": "ALICE@example.com", "full_name": "Alice Renamed"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Alice Renamed"


class TestRequestingAChange:
    """PUT /auth/me/email parks the address; it does not apply it."""

    def test_returns_202_and_does_not_move_the_address(
        self, client: TestClient
    ) -> None:
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/auth/me/email",
            json={"email": "New@Example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 202, response.text
        assert response.json()["pending_email"] == "new@example.com"

        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["email"] == "alice@example.com"
        assert me["pending_email"] == "new@example.com"
        assert me["is_email_verified"] is True

    def test_pending_survives_a_fresh_request(self, client: TestClient) -> None:
        """Pending is server state, which is what lets a second device see it."""
        token = _register(client, "alice")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["pending_email"] == "new@example.com"

    def test_the_current_address_is_refused(self, client: TestClient) -> None:
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/auth/me/email",
            json={"email": "alice@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    def test_an_address_held_by_another_account_is_refused(
        self, client: TestClient
    ) -> None:
        _register(client, "bob")
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/auth/me/email",
            json={"email": "bob@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 409

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.put(
            "/api/v1/auth/me/email", json={"email": "new@example.com"}
        )
        assert response.status_code in (401, 403)


class TestConfirmingAChange:
    """The address moves only once the code sent to it is verified."""

    def test_verifying_the_code_moves_the_address(self, client: TestClient) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": _pending_code("new@example.com")},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["pending_email"] is None
        assert body["is_email_verified"] is True

    def test_a_wrong_code_leaves_everything_alone(self, client: TestClient) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": "000000"},
            headers=_auth(token),
        )

        assert response.status_code == 400
        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["email"] == "alice@example.com"
        assert me["pending_email"] == "new@example.com"

    def test_verifying_without_a_pending_change_is_rejected(
        self, client: TestClient
    ) -> None:
        token = _register(client, "alice")

        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": "123456"},
            headers=_auth(token),
        )

        assert response.status_code == 422

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/me/email/verify", json={"code": "123456"})
        assert response.status_code in (401, 403)

    def test_malformed_codes_are_rejected_by_validation(
        self, client: TestClient
    ) -> None:
        token = _register(client, "alice")

        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": "abc"},
            headers=_auth(token),
        )
        assert response.status_code == 422


class TestCancellingAChange:
    """DELETE /auth/me/email abandons the pending change, never the address."""

    def test_clears_the_pending_address_only(self, client: TestClient) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        response = client.delete("/api/v1/auth/me/email", headers=_auth(token))

        assert response.status_code == 204
        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["pending_email"] is None
        assert me["email"] == "alice@example.com"

    def test_is_idempotent(self, client: TestClient) -> None:
        token = _register(client, "alice")

        for _ in range(2):
            assert (
                client.delete("/api/v1/auth/me/email", headers=_auth(token)).status_code
                == 204
            )


class TestResendingTheCode:
    """POST /auth/me/email/resend mints a fresh code for the pending address."""

    def test_accepted_when_a_change_is_pending(self, client: TestClient) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        response = client.post("/api/v1/auth/me/email/resend", headers=_auth(token))

        assert response.status_code == 202

    def test_rejected_when_nothing_is_pending(self, client: TestClient) -> None:
        token = _register(client, "alice")

        response = client.post("/api/v1/auth/me/email/resend", headers=_auth(token))

        assert response.status_code == 422


class TestAdminSetsAnEmail:
    """PUT /users/{id}/email applies immediately and clears the verified flag."""

    def test_admin_can_set_another_users_email(self, client: TestClient) -> None:
        alice_token = _register(client, "alice")
        alice_id = _user_id(client, alice_token)
        admin_token = _register(client, "root", role="admin")

        response = client.put(
            f"/api/v1/users/{alice_id}/email",
            json={"email": "Moved@Example.com"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user"]["email"] == "moved@example.com"
        # The admin proved nothing about the new address, so it is not verified.
        assert body["user"]["is_email_verified"] is False
        # A code goes out in the same request; otherwise the change is silent,
        # because the previous address stops resolving.
        assert body["verification_sent_to"] == "moved@example.com"

    def test_the_user_can_then_verify_and_log_in_without_a_session(
        self, client: TestClient
    ) -> None:
        """The whole point of the registration purpose: no session is needed."""
        alice_token = _register(client, "alice")
        alice_id = _user_id(client, alice_token)
        admin_token = _register(client, "root", role="admin")
        client.put(
            f"/api/v1/users/{alice_id}/email",
            json={"email": "moved@example.com"},
            headers=_auth(admin_token),
        )

        # No Authorization header on either call.
        code = _registration_code("moved@example.com")
        response = client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "moved@example.com", "code": code},
        )

        assert response.status_code == 200, response.text
        # Verifying hands back tokens, so entering the code *is* the login.
        assert response.json()["access_token"]
        me = client.get("/api/v1/auth/me", headers=_auth(alice_token)).json()
        assert me["email"] == "moved@example.com"
        assert me["is_email_verified"] is True

    def test_a_non_admin_is_refused(self, client: TestClient) -> None:
        alice_token = _register(client, "alice")
        alice_id = _user_id(client, alice_token)
        bob_token = _register(client, "bob")

        response = client.put(
            f"/api/v1/users/{alice_id}/email",
            json={"email": "hijack@example.com"},
            headers=_auth(bob_token),
        )

        assert response.status_code == 403
        me = client.get("/api/v1/auth/me", headers=_auth(alice_token)).json()
        assert me["email"] == "alice@example.com"
        assert me["is_email_verified"] is True

    def test_an_admin_cannot_target_their_own_account(self, client: TestClient) -> None:
        """This path clears the verified flag, and login is refused while that is
        false — so aiming it at yourself is self-lockout. Mirrors the existing
        guard against self-deactivation."""
        admin_token = _register(client, "root", role="admin")
        admin_id = _user_id(client, admin_token)

        response = client.put(
            f"/api/v1/users/{admin_id}/email",
            json={"email": "newroot@example.com"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 422
        assert "/auth/me/email" in response.json()["detail"]["message"]
        me = client.get("/api/v1/auth/me", headers=_auth(admin_token)).json()
        assert me["email"] == "root@example.com"
        assert me["is_email_verified"] is True

    def test_it_supersedes_a_users_own_pending_change(self, client: TestClient) -> None:
        alice_token = _register(client, "alice")
        alice_id = _user_id(client, alice_token)
        admin_token = _register(client, "root", role="admin")
        client.put(
            "/api/v1/auth/me/email",
            json={"email": "self-chosen@example.com"},
            headers=_auth(alice_token),
        )

        client.put(
            f"/api/v1/users/{alice_id}/email",
            json={"email": "admin-chosen@example.com"},
            headers=_auth(admin_token),
        )

        me = client.get("/api/v1/auth/me", headers=_auth(alice_token)).json()
        assert me["email"] == "admin-chosen@example.com"
        assert me["pending_email"] is None
