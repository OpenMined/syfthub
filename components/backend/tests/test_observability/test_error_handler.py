"""Tests for the DomainException handler and ErrorResponse model."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from syfthub.domain.exceptions import (
    ConflictError,
    DomainException,
    NotFoundError,
    PermissionDeniedError,
    UserAlreadyExistsError,
    ValidationError,
)
from syfthub.observability.constants import CORRELATION_ID_HEADER
from syfthub.observability.handlers import (
    ErrorResponse,
    _get_domain_exception_status,
    register_exception_handlers,
)

# =============================================================================
# ErrorResponse model tests
# =============================================================================


class TestErrorResponseModel:
    """Tests for the ErrorResponse Pydantic model."""

    def test_basic_creation(self):
        """Test creating a minimal ErrorResponse."""
        resp = ErrorResponse(code="NOT_FOUND", message="User not found")

        assert resp.code == "NOT_FOUND"
        assert resp.message == "User not found"

    def test_extra_fields_allowed(self):
        """Test that extra fields are accepted (e.g. field, audience)."""
        resp = ErrorResponse(
            code="CONFLICT", message="Username already exists", field="username"
        )

        assert resp.code == "CONFLICT"
        assert resp.field == "username"  # type: ignore[attr-defined]

    def test_serialization(self):
        """Test that the model serializes correctly."""
        resp = ErrorResponse(
            code="USER_ALREADY_EXISTS", message="Email exists", field="email"
        )
        data = resp.model_dump()

        assert data["code"] == "USER_ALREADY_EXISTS"
        assert data["message"] == "Email exists"
        assert data["field"] == "email"


# =============================================================================
# DOMAIN_EXCEPTION_STATUS_MAP and MRO lookup tests
# =============================================================================


class TestDomainExceptionStatusMap:
    """Tests for DOMAIN_EXCEPTION_STATUS_MAP and _get_domain_exception_status."""

    def test_not_found_maps_to_404(self):
        assert _get_domain_exception_status(NotFoundError("User")) == 404

    def test_permission_denied_maps_to_403(self):
        assert _get_domain_exception_status(PermissionDeniedError()) == 403

    def test_conflict_maps_to_409(self):
        assert _get_domain_exception_status(ConflictError("user", "email")) == 409

    def test_user_already_exists_maps_to_409(self):
        from syfthub.domain.exceptions import UserAlreadyExistsError

        assert (
            _get_domain_exception_status(UserAlreadyExistsError("username", "alice"))
            == 409
        )

    def test_validation_error_maps_to_422(self):
        assert _get_domain_exception_status(ValidationError("Bad data")) == 422

    def test_base_domain_exception_maps_to_500(self):
        """Unknown DomainException subclass falls back to DomainException -> 500."""
        assert _get_domain_exception_status(DomainException("generic")) == 500

    def test_unknown_subclass_uses_parent_mro(self):
        """A new subclass without a specific mapping should inherit from parent."""

        class NewSubError(NotFoundError):
            pass

        error = NewSubError("Resource")
        # MRO: NewSubError -> NotFoundError -> DomainException
        # First match in map is NotFoundError -> 404
        status = _get_domain_exception_status(error)
        assert status == 404

    def test_all_concrete_exceptions_have_entries(self):
        """Verify all concrete exception types produce a non-500 status."""
        from syfthub.domain.exceptions import (
            AccountingAccountExistsError,
            AccountingServiceUnavailableError,
            AudienceInactiveError,
            AudienceNotFoundError,
            InvalidAccountingPasswordError,
            KeyLoadError,
            KeyNotConfiguredError,
        )

        concrete_exceptions = [
            NotFoundError("resource"),
            PermissionDeniedError(),
            ConflictError("resource", "field"),
            ValidationError("msg"),
            UserAlreadyExistsError("username", "alice"),
            AudienceNotFoundError("audience"),
            AudienceInactiveError("audience"),
            KeyNotConfiguredError(),
            KeyLoadError("reason"),
            AccountingAccountExistsError("email@test.com"),
            InvalidAccountingPasswordError(),
            AccountingServiceUnavailableError("detail"),
        ]
        for exc in concrete_exceptions:
            status = _get_domain_exception_status(exc)
            assert status != 500, (
                f"{type(exc).__name__} falls back to 500 (missing from STATUS_MAP)"
            )


# =============================================================================
# DomainException handler integration tests
# =============================================================================


@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with the DomainException handler registered."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/not-found")
    async def raise_not_found():
        raise NotFoundError("User")

    @app.get("/raise/permission-denied")
    async def raise_permission_denied():
        raise PermissionDeniedError("Admin role required")

    @app.get("/raise/conflict")
    async def raise_conflict():
        raise ConflictError("user", "username")

    @app.get("/raise/user-exists")
    async def raise_user_exists():
        raise UserAlreadyExistsError("username", "alice")

    @app.get("/raise/generic")
    async def raise_generic():
        raise DomainException("Generic domain error")

    return app


@pytest.fixture
def handler_client(test_app):
    """TestClient for the test app."""
    return TestClient(test_app, raise_server_exceptions=False)


class TestDomainExceptionHandler:
    """Integration tests for the DomainException global handler."""

    def test_not_found_returns_404(self, handler_client):
        """NotFoundError should produce 404 with structured detail."""
        response = handler_client.get("/raise/not-found")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["code"] == "NOT_FOUND"
        assert "User not found" in data["detail"]["message"]

    def test_permission_denied_returns_403(self, handler_client):
        """PermissionDeniedError should produce 403."""
        response = handler_client.get("/raise/permission-denied")

        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["code"] == "PERMISSION_DENIED"
        assert "Admin role required" in data["detail"]["message"]

    def test_conflict_returns_409_with_field(self, handler_client):
        """ConflictError should produce 409 and include the 'field' extra attribute."""
        response = handler_client.get("/raise/conflict")

        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["code"] == "CONFLICT"
        assert data["detail"]["field"] == "username"

    def test_user_already_exists_returns_409_with_extras(self, handler_client):
        """UserAlreadyExistsError should include field and value in detail."""
        response = handler_client.get("/raise/user-exists")

        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["code"] == "USER_ALREADY_EXISTS"
        assert data["detail"]["field"] == "username"

    def test_generic_domain_exception_returns_500(self, handler_client):
        """Unrecognized DomainException falls back to 500."""
        response = handler_client.get("/raise/generic")

        assert response.status_code == 500

    def test_correlation_id_header_present(self, handler_client):
        """All error responses should include X-Correlation-ID header."""
        response = handler_client.get("/raise/not-found")

        assert CORRELATION_ID_HEADER in response.headers

    def test_response_envelope_uses_detail_key(self, handler_client):
        """Response body should use 'detail' as the outer key (Starlette convention)."""
        response = handler_client.get("/raise/permission-denied")

        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], dict)
        assert "code" in data["detail"]
        assert "message" in data["detail"]
