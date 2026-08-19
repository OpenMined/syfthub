"""Tests for the email-verification model.

The invariant: ``email_verified_at`` is true of the address on file and nothing
else. It is set only by real proof, cleared whenever the address changes, and
gates nothing — so a change can never cost anyone access to their account.
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from syfthub.auth.security import token_blacklist
from syfthub.main import app


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


@pytest.fixture
def smtp_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend email delivery is configured."""
    monkeypatch.setattr("syfthub.core.config.settings.resend_api_key", "re_test_key")


def _register(client: TestClient, username: str) -> str:
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
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _code_for(email: str) -> str:
    """Recover a hashed OTP from the store; codes only ever leave by email."""
    from syfthub.database.connection import SessionLocal
    from syfthub.repositories.otp import OTPRepository
    from syfthub.services.otp_service import _hash_code

    session = SessionLocal()
    try:
        otp = OTPRepository(session).get_active_otp(email, "registration")
        assert otp is not None, f"no active code for {email}"
        for candidate in range(1_000_000):
            code = f"{candidate:06d}"
            if _hash_code(code) == otp.code_hash:
                return code
        raise AssertionError("could not recover the code")
    finally:
        session.close()


class TestChangingTheAddress:
    """An address change is an ordinary profile write."""

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_applies_immediately_and_drops_the_verified_state(
        self, _notice, _code, client: TestClient, smtp_on: None
    ) -> None:
        token = _register(client, "alice")
        # Prove the original address so there is a verified state to lose.
        client.post(
            "/api/v1/auth/register/verify-otp",
            json={"email": "alice@example.com", "code": _code_for("alice@example.com")},
        )

        response = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["is_email_verified"] is False
        assert body["email_verified_at"] is None

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_login_still_works_afterwards(
        self, _notice, _code, client: TestClient, smtp_on: None
    ) -> None:
        """The whole point of the split: a change costs a tick, not access."""
        token = _register(client, "alice")
        client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        response = client.post(
            "/api/v1/auth/login",
            data={"username": "new@example.com", "password": "testpass123"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_email_verified"] is False

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_warns_the_address_it_replaced(
        self, notice, _code, client: TestClient, smtp_on: None
    ) -> None:
        """The old inbox is the only one the account holder is known to control."""
        token = _register(client, "alice")
        client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        notice.assert_called_once()
        assert notice.call_args.args[0] == "alice@example.com"

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_sends_a_code_to_the_new_address(
        self, _notice, code, client: TestClient, smtp_on: None
    ) -> None:
        token = _register(client, "alice")
        client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        assert code.call_args.args[0] == "new@example.com"

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_an_unchanged_address_sends_nothing(
        self, notice, code, client: TestClient, smtp_on: None
    ) -> None:
        """A client round-tripping a whole profile object must not trigger mail."""
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/users/me",
            json={"email": "ALICE@example.com", "full_name": "Alice Renamed"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["full_name"] == "Alice Renamed"
        notice.assert_not_called()
        code.assert_not_called()

    def test_an_address_held_by_another_account_is_refused(
        self, client: TestClient
    ) -> None:
        _register(client, "bob")
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/users/me",
            json={"email": "bob@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 409


class TestVerifyingTheAddress:
    """POST /auth/me/email/{resend,verify} prove the address on file."""

    @patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
    def test_resend_then_verify_records_the_proof(
        self, _send, client: TestClient, smtp_on: None
    ) -> None:
        token = _register(client, "alice")

        assert (
            client.post(
                "/api/v1/auth/me/email/resend", headers=_auth(token)
            ).status_code
            == 202
        )
        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": _code_for("alice@example.com")},
            headers=_auth(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_email_verified"] is True
        assert response.json()["email_verified_at"] is not None

    @patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
    def test_a_wrong_code_records_nothing(
        self, _send, client: TestClient, smtp_on: None
    ) -> None:
        token = _register(client, "alice")
        client.post("/api/v1/auth/me/email/resend", headers=_auth(token))

        response = client.post(
            "/api/v1/auth/me/email/verify",
            json={"code": "000000"},
            headers=_auth(token),
        )

        assert response.status_code == 400
        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["is_email_verified"] is False

    @patch("syfthub.auth.router.send_otp_email", new_callable=AsyncMock)
    def test_verifying_twice_is_refused(
        self, _send, client: TestClient, smtp_on: None
    ) -> None:
        token = _register(client, "alice")
        client.post("/api/v1/auth/me/email/resend", headers=_auth(token))
        code = _code_for("alice@example.com")
        client.post(
            "/api/v1/auth/me/email/verify", json={"code": code}, headers=_auth(token)
        )

        response = client.post(
            "/api/v1/auth/me/email/verify", json={"code": code}, headers=_auth(token)
        )

        assert response.status_code == 422

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.post(
            "/api/v1/auth/me/email/verify", json={"code": "123456"}
        ).status_code in (401, 403)
        assert client.post("/api/v1/auth/me/email/resend").status_code in (401, 403)


class TestWithoutEmailDelivery:
    """No SMTP means nothing can be proven — and nothing pretends otherwise."""

    def test_registration_leaves_the_address_unverified(
        self, client: TestClient
    ) -> None:
        """The old code set the flag true here, with no proof whatsoever."""
        token = _register(client, "alice")

        me = client.get("/api/v1/auth/me", headers=_auth(token)).json()
        assert me["is_email_verified"] is False
        assert me["email_verified_at"] is None

    def test_registration_still_hands_back_tokens(self, client: TestClient) -> None:
        token = _register(client, "alice")
        assert token

    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_a_change_applies_and_stays_unverified(
        self, _notice, client: TestClient
    ) -> None:
        token = _register(client, "alice")

        response = client.put(
            "/api/v1/users/me",
            json={"email": "new@example.com"},
            headers=_auth(token),
        )

        assert response.status_code == 200
        assert response.json()["email"] == "new@example.com"
        assert response.json()["is_email_verified"] is False

    def test_asking_for_a_code_is_refused(self, client: TestClient) -> None:
        """Better a clear 422 than a code nobody can ever receive."""
        token = _register(client, "alice")

        response = client.post("/api/v1/auth/me/email/resend", headers=_auth(token))

        assert response.status_code == 422


class TestAdminChangingAnAddress:
    """Identical semantics; there is no separate admin mechanism any more."""

    @patch("syfthub.api.endpoints.users.send_otp_email", new_callable=AsyncMock)
    @patch(
        "syfthub.api.endpoints.users.send_email_changed_notice", new_callable=AsyncMock
    )
    def test_admin_change_cannot_lock_the_user_out(
        self, _notice, _code, client: TestClient, smtp_on: None
    ) -> None:
        alice_token = _register(client, "alice")
        alice_id = client.get("/api/v1/auth/me", headers=_auth(alice_token)).json()[
            "id"
        ]
        admin_token = _register(client, "root")
        from syfthub.database.connection import SessionLocal
        from syfthub.models.user import UserModel

        session = SessionLocal()
        try:
            session.query(UserModel).filter(
                UserModel.username == "root"
            ).one().role = "admin"
            session.commit()
        finally:
            session.close()

        response = client.put(
            f"/api/v1/users/{alice_id}",
            json={"email": "moved@example.com"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["email"] == "moved@example.com"
        assert response.json()["is_email_verified"] is False
        # And alice can still sign in — the thing that used to break.
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "moved@example.com", "password": "testpass123"},
        )
        assert login.status_code == 200
