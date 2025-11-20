"""Tests for domain exceptions."""

from syfthub.domain.exceptions import (
    BusinessRuleViolation,
    DomainException,
    InvariantViolation,
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


class TestBusinessRuleViolation:
    """Test BusinessRuleViolation exception."""

    def test_business_rule_violation_creation(self):
        """Test creating business rule violation."""
        error = BusinessRuleViolation("Business rule violated")

        assert str(error) == "Business rule violated"
        assert error.message == "Business rule violated"
        assert error.error_code == "BUSINESS_RULE_VIOLATION"
        assert isinstance(error, DomainException)

    def test_business_rule_violation_inheritance(self):
        """Test BusinessRuleViolation inheritance chain."""
        error = BusinessRuleViolation("Test")

        assert isinstance(error, BusinessRuleViolation)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)


class TestInvariantViolation:
    """Test InvariantViolation exception."""

    def test_invariant_violation_creation(self):
        """Test creating invariant violation."""
        error = InvariantViolation("Invariant violated")

        assert str(error) == "Invariant violated"
        assert error.message == "Invariant violated"
        assert error.error_code == "INVARIANT_VIOLATION"
        assert isinstance(error, DomainException)

    def test_invariant_violation_inheritance(self):
        """Test InvariantViolation inheritance chain."""
        error = InvariantViolation("Test")

        assert isinstance(error, InvariantViolation)
        assert isinstance(error, DomainException)
        assert isinstance(error, Exception)
