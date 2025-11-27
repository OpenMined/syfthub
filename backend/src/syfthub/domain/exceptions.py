"""Domain-specific exceptions."""

from __future__ import annotations


class DomainException(Exception):
    """Base exception for domain-related errors."""

    def __init__(self, message: str, error_code: str = "DOMAIN_ERROR"):
        """Initialize domain exception."""
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class ValidationError(DomainException):
    """Exception raised when domain validation fails."""

    def __init__(self, message: str):
        """Initialize validation error."""
        super().__init__(message, "VALIDATION_ERROR")
