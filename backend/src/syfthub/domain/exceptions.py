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


# ===========================================
# IDENTITY PROVIDER (IdP) EXCEPTIONS
# ===========================================


class IdPException(DomainException):
    """Base exception for Identity Provider errors."""

    def __init__(self, message: str, error_code: str = "IDP_ERROR"):
        """Initialize IdP exception."""
        super().__init__(message, error_code)


class InvalidAudienceError(IdPException):
    """Raised when requested audience is not in the allowlist."""

    def __init__(self, audience: str):
        """Initialize invalid audience error."""
        self.audience = audience
        super().__init__(
            f"The requested audience '{audience}' is not a registered service.",
            "INVALID_AUDIENCE",
        )


class KeyNotConfiguredError(IdPException):
    """Raised when RSA keys are not configured."""

    def __init__(self) -> None:
        """Initialize key not configured error."""
        super().__init__(
            "RSA keys not configured. Identity Provider is unavailable.",
            "KEY_NOT_CONFIGURED",
        )


class KeyLoadError(IdPException):
    """Raised when RSA keys cannot be loaded."""

    def __init__(self, reason: str):
        """Initialize key load error."""
        self.reason = reason
        super().__init__(
            f"Failed to load RSA keys: {reason}",
            "KEY_LOAD_ERROR",
        )
