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
    """Raised when requested audience is not in the allowlist.

    DEPRECATED: Use AudienceNotFoundError or AudienceInactiveError instead.
    This exception is kept for backward compatibility.
    """

    def __init__(self, audience: str):
        """Initialize invalid audience error."""
        self.audience = audience
        super().__init__(
            f"The requested audience '{audience}' is not a registered service.",
            "INVALID_AUDIENCE",
        )


class AudienceNotFoundError(IdPException):
    """Raised when the requested audience is not a registered user.

    In the dynamic audience model, a valid audience must be the username
    of an existing user account. This error is raised when the requested
    audience doesn't match any username in the database.
    """

    def __init__(self, audience: str):
        """Initialize audience not found error."""
        self.audience = audience
        super().__init__(
            f"Audience '{audience}' is not a registered user.",
            "AUDIENCE_NOT_FOUND",
        )


class AudienceInactiveError(IdPException):
    """Raised when the requested audience user is inactive.

    In the dynamic audience model, tokens can only be minted for active
    users. This error is raised when the user exists but is deactivated.
    """

    def __init__(self, audience: str):
        """Initialize audience inactive error."""
        self.audience = audience
        super().__init__(
            f"Audience '{audience}' is inactive and cannot receive tokens.",
            "AUDIENCE_INACTIVE",
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


# ===========================================
# USER REGISTRATION EXCEPTIONS
# ===========================================


class UserAlreadyExistsError(DomainException):
    """Raised when username or email already exists in SyftHub.

    This error indicates a duplicate user registration attempt.
    """

    def __init__(self, field: str, value: str):
        """Initialize user already exists error.

        Args:
            field: The field that already exists ("username" or "email")
            value: The value that already exists
        """
        self.field = field
        self.value = value
        super().__init__(
            f"{field.capitalize()} already exists",
            "USER_ALREADY_EXISTS",
        )


# ===========================================
# ACCOUNTING SERVICE EXCEPTIONS
# ===========================================


class AccountingException(DomainException):
    """Base exception for accounting service errors."""

    def __init__(self, message: str, error_code: str = "ACCOUNTING_ERROR"):
        """Initialize accounting exception."""
        super().__init__(message, error_code)


class AccountingAccountExistsError(AccountingException):
    """Raised when email already has an account in the accounting service.

    This error indicates that the user needs to provide their existing
    accounting password to link their accounts during registration.
    """

    def __init__(self, email: str):
        """Initialize accounting account exists error."""
        self.email = email
        self.requires_accounting_password = True
        super().__init__(
            f"This email ({email}) already has an account in the accounting service. "
            "Please provide your existing accounting password to link your accounts.",
            "ACCOUNTING_ACCOUNT_EXISTS",
        )


class InvalidAccountingPasswordError(AccountingException):
    """Raised when the provided accounting password is invalid."""

    def __init__(self) -> None:
        """Initialize invalid accounting password error."""
        super().__init__(
            "The provided accounting password is invalid. "
            "Please check your password and try again.",
            "INVALID_ACCOUNTING_PASSWORD",
        )


class AccountingServiceUnavailableError(AccountingException):
    """Raised when the accounting service is unavailable or returns an error."""

    def __init__(self, detail: str):
        """Initialize accounting service unavailable error."""
        self.detail = detail
        super().__init__(
            f"Accounting service error: {detail}",
            "ACCOUNTING_SERVICE_UNAVAILABLE",
        )
