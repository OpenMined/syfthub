"""Tests for EmailChangeService and the public_id external identifier.

The property under test throughout is the invariant that made this work
necessary: ``is_email_verified`` must never describe an address whose owner has
not proven control of it, because that flag is about to be exported as an OIDC
``email_verified`` claim that relying parties link accounts by.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from syfthub.domain.exceptions import (
    ConflictError,
    InvalidOTPError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from syfthub.models.user import UserModel
from syfthub.repositories.user import UserRepository
from syfthub.schemas.user import User, UserUpdate
from syfthub.services.email_change_service import (
    ADMIN_SET_PURPOSE,
    EMAIL_CHANGE_PURPOSE,
    EmailChangeService,
)
from syfthub.services.user_service import UserService


def _make_user(username: str, **overrides) -> UserModel:
    """Build a UserModel with sensible defaults."""
    data = {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": f"{username.title()} User",
        "role": "user",
        "is_active": True,
        "is_email_verified": True,
        "auth_provider": "local",
        "password_hash": "x",
    }
    data.update(overrides)
    return UserModel(**data)


@pytest.fixture
def persisted_user(test_session: Session) -> UserModel:
    """A committed user with a verified address."""
    user = _make_user("alice")
    test_session.add(user)
    test_session.commit()
    test_session.refresh(user)
    return user


def _as_schema(model: UserModel) -> User:
    return User.model_validate(model)


class TestPublicId:
    """users.public_id — the opaque external identifier backing OIDC `sub`."""

    def test_assigned_automatically(self, persisted_user: UserModel) -> None:
        assert isinstance(persisted_user.public_id, uuid.UUID)

    def test_distinct_per_user(self, test_session: Session) -> None:
        first = _make_user("bob")
        second = _make_user("carol")
        test_session.add_all([first, second])
        test_session.commit()

        assert first.public_id != second.public_id

    def test_is_a_random_version_4_uuid(self, persisted_user: UserModel) -> None:
        """Random, not derived from `id` — a derived value would leak the very
        thing `public_id` exists to hide."""
        assert persisted_user.public_id.version == 4

    def test_survives_a_profile_update(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        """It is an identifier, so it must be immutable across ordinary edits."""
        original = persisted_user.public_id
        repo = UserRepository(test_session)

        repo.update_user(persisted_user.id, UserUpdate(full_name="Renamed"))

        test_session.refresh(persisted_user)
        assert persisted_user.public_id == original

    def test_absent_from_the_public_profile(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        profile = UserService(test_session).get_public_user_profile(
            persisted_user.username
        )
        assert profile is not None
        assert not hasattr(profile, "public_id")
        assert not hasattr(profile, "id")


class TestUpdateUserNoLongerWritesEmail:
    """The repository-level half of the fix."""

    def test_email_is_ignored(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        repo = UserRepository(test_session)

        repo.update_user(
            persisted_user.id, UserUpdate(email="attacker-target@example.com")
        )

        test_session.refresh(persisted_user)
        assert persisted_user.email == "alice@example.com"
        assert persisted_user.is_email_verified is True

    def test_other_fields_still_apply(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        repo = UserRepository(test_session)

        repo.update_user(
            persisted_user.id,
            UserUpdate(full_name="Alice Renamed", email="ignored@example.com"),
        )

        test_session.refresh(persisted_user)
        assert persisted_user.full_name == "Alice Renamed"
        assert persisted_user.email == "alice@example.com"


class TestRequestChange:
    """Requesting a change must not touch the current, verified address."""

    def test_parks_the_address_without_moving_email(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)

        code = service.request_change(_as_schema(persisted_user), "New@Example.com")

        test_session.refresh(persisted_user)
        assert persisted_user.pending_email == "new@example.com"
        assert persisted_user.email == "alice@example.com"
        assert persisted_user.is_email_verified is True
        assert len(code) == 6

    def test_otp_is_keyed_to_the_new_address(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        """The code must prove the *new* address, not the old one."""
        service = EmailChangeService(test_session)

        service.request_change(_as_schema(persisted_user), "new@example.com")

        assert (
            service.otp_service.otp_repo.get_active_otp(
                "new@example.com", EMAIL_CHANGE_PURPOSE
            )
            is not None
        )
        assert (
            service.otp_service.otp_repo.get_active_otp(
                "alice@example.com", EMAIL_CHANGE_PURPOSE
            )
            is None
        )

    def test_rejects_the_current_address(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)

        with pytest.raises(ValidationError):
            service.request_change(_as_schema(persisted_user), "ALICE@example.com")

    def test_rejects_an_address_held_by_another_account(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        test_session.add(_make_user("bob"))
        test_session.commit()
        service = EmailChangeService(test_session)

        with pytest.raises(ConflictError):
            service.request_change(_as_schema(persisted_user), "bob@example.com")

        test_session.refresh(persisted_user)
        assert persisted_user.pending_email is None

    def test_a_second_request_replaces_the_first(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)

        service.request_change(_as_schema(persisted_user), "first@example.com")
        service.request_change(_as_schema(persisted_user), "second@example.com")

        test_session.refresh(persisted_user)
        assert persisted_user.pending_email == "second@example.com"


class TestConfirmChange:
    """Only a verified code moves the address."""

    def test_promotes_the_pending_address(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)
        code = service.request_change(_as_schema(persisted_user), "new@example.com")

        result = service.confirm_change(_as_schema(persisted_user), code)

        test_session.refresh(persisted_user)
        assert persisted_user.email == "new@example.com"
        assert persisted_user.pending_email is None
        assert persisted_user.is_email_verified is True
        assert result.email == "new@example.com"

    def test_a_wrong_code_changes_nothing_and_keeps_the_change_pending(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)
        service.request_change(_as_schema(persisted_user), "new@example.com")

        with pytest.raises(InvalidOTPError):
            service.confirm_change(_as_schema(persisted_user), "000000")

        # verify_otp increments the attempt counter without committing before it
        # raises, so the session carries a pending write. Roll it back so the
        # assertions read committed state and SQLite is not left holding a write
        # lock that would block table teardown.
        test_session.rollback()
        reread = UserRepository(test_session).get_by_id(persisted_user.id)
        assert reread is not None
        assert reread.email == "alice@example.com"
        assert reread.pending_email == "new@example.com"
        test_session.rollback()

    def test_rejects_when_nothing_is_pending(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)

        with pytest.raises(ValidationError):
            service.confirm_change(_as_schema(persisted_user), "123456")

    def test_loses_a_race_for_the_same_address(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        """If someone else takes the address before confirmation, we must not
        clobber the unique constraint — the other account keeps it."""
        service = EmailChangeService(test_session)
        code = service.request_change(_as_schema(persisted_user), "taken@example.com")

        test_session.add(_make_user("bob", email="taken@example.com"))
        test_session.commit()

        with pytest.raises(ConflictError):
            service.confirm_change(_as_schema(persisted_user), code)

        # The service rolled the failed UPDATE back, so re-read rather than
        # trusting the identity map, then close the read transaction — SQLite
        # holds a shared lock on an open one, which would block table teardown.
        test_session.rollback()
        reread = UserRepository(test_session).get_by_id(persisted_user.id)
        assert reread is not None
        assert reread.email == "alice@example.com"
        assert reread.pending_email == "taken@example.com"
        test_session.rollback()

    def test_cannot_confirm_another_users_change(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        """The pending address is read from the caller's own row, so a code
        minted for someone else's change is useless."""
        other = _make_user("bob")
        test_session.add(other)
        test_session.commit()
        test_session.refresh(other)

        service = EmailChangeService(test_session)
        code = service.request_change(_as_schema(other), "bobs-new@example.com")

        with pytest.raises(ValidationError):
            service.confirm_change(_as_schema(persisted_user), code)

        test_session.refresh(persisted_user)
        assert persisted_user.email == "alice@example.com"


class TestResendAndCancel:
    """Lifecycle management for an in-flight change."""

    def test_resend_returns_the_pending_address_and_a_fresh_code(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)
        service.request_change(_as_schema(persisted_user), "new@example.com")

        pending, code = service.resend_code(_as_schema(persisted_user))

        assert pending == "new@example.com"
        assert len(code) == 6

    def test_resend_requires_a_pending_change(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)

        with pytest.raises(ValidationError):
            service.resend_code(_as_schema(persisted_user))

    def test_cancel_clears_the_pending_address(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)
        service.request_change(_as_schema(persisted_user), "new@example.com")

        service.cancel_change(_as_schema(persisted_user))

        test_session.refresh(persisted_user)
        assert persisted_user.pending_email is None
        assert persisted_user.email == "alice@example.com"

    def test_cancel_is_idempotent(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        service = EmailChangeService(test_session)
        service.cancel_change(_as_schema(persisted_user))
        service.cancel_change(_as_schema(persisted_user))

    def test_missing_user_raises_not_found(self, test_session: Session) -> None:
        service = EmailChangeService(test_session)
        ghost = User(
            id=999999, username="ghost", email="ghost@example.com", full_name="Ghost"
        )

        with pytest.raises(NotFoundError):
            service.resend_code(ghost)


class TestAdminSetEmail:
    """An admin changing someone else's address has proven nothing."""

    def test_applies_immediately_and_clears_the_verified_flag(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()

        _, address, code = EmailChangeService(test_session).admin_set_email(
            persisted_user.id, "Moved@Example.com", _as_schema(admin)
        )

        test_session.refresh(persisted_user)
        assert persisted_user.email == "moved@example.com"
        assert persisted_user.is_email_verified is False
        assert address == "moved@example.com"
        assert len(code) == 6

    def test_mints_the_code_under_the_registration_purpose(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        """The target may have no session, and only the registration-purpose
        endpoints can be completed without one."""
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()
        service = EmailChangeService(test_session)

        service.admin_set_email(
            persisted_user.id, "moved@example.com", _as_schema(admin)
        )

        assert (
            service.otp_service.otp_repo.get_active_otp(
                "moved@example.com", ADMIN_SET_PURPOSE
            )
            is not None
        )
        assert ADMIN_SET_PURPOSE == "registration"

    def test_an_unchanged_address_mints_nothing(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()

        _, _, code = EmailChangeService(test_session).admin_set_email(
            persisted_user.id, "ALICE@example.com", _as_schema(admin)
        )

        assert code == ""
        test_session.refresh(persisted_user)
        assert persisted_user.is_email_verified is True

    def test_clears_any_pending_change(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()
        EmailChangeService(test_session).request_change(
            _as_schema(persisted_user), "self-chosen@example.com"
        )

        EmailChangeService(test_session).admin_set_email(
            persisted_user.id, "admin-chosen@example.com", _as_schema(admin)
        )

        test_session.refresh(persisted_user)
        assert persisted_user.pending_email is None
        assert persisted_user.email == "admin-chosen@example.com"

    def test_non_admin_is_refused(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        other = _make_user("bob")
        test_session.add(other)
        test_session.commit()
        test_session.refresh(other)

        with pytest.raises(PermissionDeniedError):
            EmailChangeService(test_session).admin_set_email(
                persisted_user.id, "hijack@example.com", _as_schema(other)
            )

        test_session.refresh(persisted_user)
        assert persisted_user.email == "alice@example.com"

    def test_rejects_an_address_held_by_another_account(
        self, test_session: Session, persisted_user: UserModel
    ) -> None:
        admin = _make_user("root", role="admin")
        test_session.add_all([admin, _make_user("bob")])
        test_session.commit()

        with pytest.raises(ConflictError):
            EmailChangeService(test_session).admin_set_email(
                persisted_user.id, "bob@example.com", _as_schema(admin)
            )

    def test_refuses_to_target_the_caller(self, test_session: Session) -> None:
        """Clearing your own verified flag is self-lockout; PUT /auth/me/email
        is the path that keeps the current address working."""
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()
        test_session.refresh(admin)

        with pytest.raises(ValidationError) as exc_info:
            EmailChangeService(test_session).admin_set_email(
                admin.id, "newroot@example.com", _as_schema(admin)
            )

        assert "/auth/me/email" in exc_info.value.message
        test_session.refresh(admin)
        assert admin.email == "root@example.com"
        assert admin.is_email_verified is True

    def test_missing_target_raises_not_found(self, test_session: Session) -> None:
        admin = _make_user("root", role="admin")
        test_session.add(admin)
        test_session.commit()

        with pytest.raises(NotFoundError):
            EmailChangeService(test_session).admin_set_email(
                999999, "nobody@example.com", _as_schema(admin)
            )
