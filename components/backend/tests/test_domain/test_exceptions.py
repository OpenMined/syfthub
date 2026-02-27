"""Tests for domain exceptions."""

from syfthub.domain.exceptions import (
    AccountingAccountExistsError,
    AccountingException,
    AccountingServiceUnavailableError,
    ConflictError,
    DomainException,
    IdPException,
    InvalidAccountingPasswordError,
    InvalidAudienceError,
    KeyLoadError,
    KeyNotConfiguredError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)


class TestDomainException:
    """Test DomainException base class."""

    def test_domain_exception_with_message_only(self):
        """Test creating domain exception with message only."""
        exception = DomainException("Test error message")

        assert str(exception) == "Test error message"
        assert exception.message == "Test error message"
        assert exception.error_code == "DOMAIN_ERROR"

    def test_domain_exception_with_custom_error_code(self):
        """Test creating domain exception with custom error code."""
        exception = DomainException("Custom error", "CUSTOM_CODE")

        assert str(exception) == "Custom error"
        assert exception.message == "Custom error"
        assert exception.error_code == "CUSTOM_CODE"

    def test_domain_exception_inheritance(self):
        """Test that DomainException inherits from Exception."""
        exception = DomainException("Test")

        assert isinstance(exception, Exception)
        assert isinstance(exception, DomainException)


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_creation(self):
        """Test creating validation error."""
        error = ValidationError("Validation failed")

        assert str(error) == "Validation failed"
        assert error.message == "Validation failed"
        assert error.error_code == "VALIDATION_ERROR"
        assert isinstance(error, DomainException)

    def test_validation_error_inheritance(self):
        """Test ValidationError inheritance chain."""
        error = ValidationError("Test")

        assert isinstance(error, ValidationError)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)


class TestIdPException:
    """Test IdPException base class."""

    def test_idp_exception_with_message_only(self):
        """Test creating IdP exception with message only."""
        exception = IdPException("IdP error message")

        assert str(exception) == "IdP error message"
        assert exception.message == "IdP error message"
        assert exception.error_code == "IDP_ERROR"

    def test_idp_exception_with_custom_error_code(self):
        """Test creating IdP exception with custom error code."""
        exception = IdPException("Custom IdP error", "CUSTOM_IDP_CODE")

        assert str(exception) == "Custom IdP error"
        assert exception.message == "Custom IdP error"
        assert exception.error_code == "CUSTOM_IDP_CODE"

    def test_idp_exception_inheritance(self):
        """Test IdPException inheritance chain."""
        exception = IdPException("Test")

        assert isinstance(exception, IdPException)
        assert isinstance(exception, DomainException)
        assert isinstance(exception, Exception)


class TestInvalidAudienceError:
    """Test InvalidAudienceError exception."""

    def test_invalid_audience_error_creation(self):
        """Test creating invalid audience error."""
        error = InvalidAudienceError("test-service")

        assert "test-service" in str(error)
        assert error.audience == "test-service"
        assert error.error_code == "INVALID_AUDIENCE"
        assert "not a registered service" in error.message

    def test_invalid_audience_error_inheritance(self):
        """Test InvalidAudienceError inheritance chain."""
        error = InvalidAudienceError("test")

        assert isinstance(error, InvalidAudienceError)
        assert isinstance(error, IdPException)
        assert isinstance(error, DomainException)


class TestKeyNotConfiguredError:
    """Test KeyNotConfiguredError exception."""

    def test_key_not_configured_error_creation(self):
        """Test creating key not configured error."""
        error = KeyNotConfiguredError()

        assert "RSA keys not configured" in str(error)
        assert error.error_code == "KEY_NOT_CONFIGURED"

    def test_key_not_configured_error_inheritance(self):
        """Test KeyNotConfiguredError inheritance chain."""
        error = KeyNotConfiguredError()

        assert isinstance(error, KeyNotConfiguredError)
        assert isinstance(error, IdPException)
        assert isinstance(error, DomainException)


class TestKeyLoadError:
    """Test KeyLoadError exception."""

    def test_key_load_error_creation(self):
        """Test creating key load error."""
        error = KeyLoadError("invalid key format")

        assert "invalid key format" in str(error)
        assert error.reason == "invalid key format"
        assert error.error_code == "KEY_LOAD_ERROR"
        assert "Failed to load RSA keys" in error.message

    def test_key_load_error_inheritance(self):
        """Test KeyLoadError inheritance chain."""
        error = KeyLoadError("test reason")

        assert isinstance(error, KeyLoadError)
        assert isinstance(error, IdPException)
        assert isinstance(error, DomainException)


class TestAccountingException:
    """Test AccountingException base class."""

    def test_accounting_exception_with_message_only(self):
        """Test creating accounting exception with message only."""
        exception = AccountingException("Accounting error message")

        assert str(exception) == "Accounting error message"
        assert exception.message == "Accounting error message"
        assert exception.error_code == "ACCOUNTING_ERROR"

    def test_accounting_exception_with_custom_error_code(self):
        """Test creating accounting exception with custom error code."""
        exception = AccountingException("Custom error", "CUSTOM_ACCOUNTING_CODE")

        assert str(exception) == "Custom error"
        assert exception.message == "Custom error"
        assert exception.error_code == "CUSTOM_ACCOUNTING_CODE"

    def test_accounting_exception_inheritance(self):
        """Test AccountingException inheritance chain."""
        exception = AccountingException("Test")

        assert isinstance(exception, AccountingException)
        assert isinstance(exception, DomainException)
        assert isinstance(exception, Exception)


class TestAccountingAccountExistsError:
    """Test AccountingAccountExistsError exception."""

    def test_accounting_account_exists_error_creation(self):
        """Test creating accounting account exists error."""
        error = AccountingAccountExistsError("user@example.com")

        assert "user@example.com" in str(error)
        assert error.email == "user@example.com"
        assert error.requires_accounting_password is True
        assert error.error_code == "ACCOUNTING_ACCOUNT_EXISTS"
        assert "already has an account" in error.message

    def test_accounting_account_exists_error_inheritance(self):
        """Test AccountingAccountExistsError inheritance chain."""
        error = AccountingAccountExistsError("test@example.com")

        assert isinstance(error, AccountingAccountExistsError)
        assert isinstance(error, AccountingException)
        assert isinstance(error, DomainException)


class TestInvalidAccountingPasswordError:
    """Test InvalidAccountingPasswordError exception."""

    def test_invalid_accounting_password_error_creation(self):
        """Test creating invalid accounting password error."""
        error = InvalidAccountingPasswordError()

        assert "invalid" in str(error).lower()
        assert error.error_code == "INVALID_ACCOUNTING_PASSWORD"
        assert "password" in error.message.lower()

    def test_invalid_accounting_password_error_inheritance(self):
        """Test InvalidAccountingPasswordError inheritance chain."""
        error = InvalidAccountingPasswordError()

        assert isinstance(error, InvalidAccountingPasswordError)
        assert isinstance(error, AccountingException)
        assert isinstance(error, DomainException)


class TestAccountingServiceUnavailableError:
    """Test AccountingServiceUnavailableError exception."""

    def test_accounting_service_unavailable_error_creation(self):
        """Test creating accounting service unavailable error."""
        error = AccountingServiceUnavailableError("Connection timeout")

        assert "Connection timeout" in str(error)
        assert error.detail == "Connection timeout"
        assert error.error_code == "ACCOUNTING_SERVICE_UNAVAILABLE"
        assert "Accounting service error" in error.message

    def test_accounting_service_unavailable_error_inheritance(self):
        """Test AccountingServiceUnavailableError inheritance chain."""
        error = AccountingServiceUnavailableError("test detail")

        assert isinstance(error, AccountingServiceUnavailableError)
        assert isinstance(error, AccountingException)
        assert isinstance(error, DomainException)


class TestNotFoundError:
    """Test NotFoundError exception."""

    def test_not_found_error_creation(self):
        """Test creating not found error without identifier."""
        error = NotFoundError("User")

        assert error.resource == "User"
        assert error.error_code == "NOT_FOUND"
        assert error.message == "User not found"
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)

    def test_not_found_error_with_identifier(self):
        """Test creating not found error with identifier."""
        error = NotFoundError("Endpoint", "my-endpoint")

        assert error.resource == "Endpoint"
        assert error.error_code == "NOT_FOUND"
        assert "Endpoint" in error.message
        assert "my-endpoint" in error.message

    def test_not_found_error_inheritance(self):
        """Test NotFoundError inheritance chain."""
        error = NotFoundError("Resource")

        assert isinstance(error, NotFoundError)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)


class TestPermissionDeniedError:
    """Test PermissionDeniedError exception."""

    def test_permission_denied_error_creation_default(self):
        """Test creating permission denied error with default message."""
        error = PermissionDeniedError()

        assert error.error_code == "PERMISSION_DENIED"
        assert "Permission denied" in error.message

    def test_permission_denied_error_creation_custom(self):
        """Test creating permission denied error with custom message."""
        error = PermissionDeniedError("Admin role required")

        assert error.error_code == "PERMISSION_DENIED"
        assert error.message == "Admin role required"

    def test_permission_denied_error_inheritance(self):
        """Test PermissionDeniedError inheritance chain."""
        error = PermissionDeniedError()

        assert isinstance(error, PermissionDeniedError)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)


class TestConflictError:
    """Test ConflictError exception."""

    def test_conflict_error_creation(self):
        """Test creating conflict error."""
        error = ConflictError("user", "username")

        assert error.resource == "user"
        assert error.field == "username"
        assert error.error_code == "CONFLICT"
        assert "Username" in error.message
        assert "already exists" in error.message

    def test_conflict_error_email(self):
        """Test creating conflict error for email."""
        error = ConflictError("user", "email")

        assert error.field == "email"
        assert "Email" in error.message

    def test_conflict_error_inheritance(self):
        """Test ConflictError inheritance chain."""
        error = ConflictError("resource", "field")

        assert isinstance(error, ConflictError)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)
