"""Custom exceptions for SyftHub SDK."""

from __future__ import annotations

from typing import Any


class SyftHubError(Exception):
    """Base exception for all SyftHub SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(SyftHubError):
    """Raised when authentication fails (401)."""

    def __init__(
        self,
        message: str = "Authentication failed",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=401, detail=detail)


class AuthorizationError(SyftHubError):
    """Raised when access is denied (403)."""

    def __init__(
        self,
        message: str = "Access denied",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=403, detail=detail)


class NotFoundError(SyftHubError):
    """Raised when a resource is not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=404, detail=detail)


class ValidationError(SyftHubError):
    """Raised when request validation fails (422).

    Attributes:
        errors: Optional dict mapping field names to lists of error messages.
                Example: {"email": ["Invalid format", "Already taken"]}
    """

    def __init__(
        self,
        message: str = "Validation error",
        detail: Any = None,
        errors: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message, status_code=422, detail=detail)
        self.errors = errors or {}


class APIError(SyftHubError):
    """Raised for other API errors."""

    pass


class NetworkError(SyftHubError):
    """Raised when a network operation fails (connection, timeout, DNS).

    This is distinct from APIError which indicates the server returned an error.
    NetworkError means we couldn't reach the server at all.

    Attributes:
        cause: The underlying exception that caused this error
    """

    def __init__(
        self,
        message: str = "Network error",
        cause: Exception | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=None, detail=detail)
        self.cause = cause
        self.__cause__ = cause


class UserAlreadyExistsError(SyftHubError):
    """Raised when user registration fails due to duplicate username or email.

    Attributes:
        field: The field that caused the conflict ('username' or 'email'), if determinable
    """

    def __init__(
        self,
        message: str = "User already exists",
        field: str | None = None,
        status_code: int | None = 409,
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, detail=detail)
        self.field = field


class ConfigurationError(SyftHubError):
    """Raised when SDK configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None, detail=None)


# =============================================================================
# Chat-related Exceptions
# =============================================================================


class ChatError(SyftHubError):
    """Base exception for chat-related errors."""

    def __init__(
        self,
        message: str,
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=None, detail=detail)


class AggregatorError(ChatError):
    """Raised when the aggregator service is unavailable or returns an error."""

    def __init__(
        self,
        message: str = "Aggregator service error",
        status_code: int | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.status_code = status_code


class RetrievalError(ChatError):
    """Raised when data source retrieval fails."""

    def __init__(
        self,
        message: str = "Failed to retrieve from data sources",
        source_path: str | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.source_path = source_path


class GenerationError(ChatError):
    """Raised when model generation fails."""

    def __init__(
        self,
        message: str = "Failed to generate response",
        model_slug: str | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.model_slug = model_slug


class EndpointResolutionError(ChatError):
    """Raised when an endpoint cannot be resolved to a usable reference."""

    def __init__(
        self,
        message: str = "Failed to resolve endpoint",
        endpoint_path: str | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.endpoint_path = endpoint_path


# =============================================================================
# Accounting-related Exceptions
# =============================================================================


class AccountingAccountExistsError(SyftHubError):
    """Raised when email already exists in the accounting service during registration.

    This error indicates that the user needs to provide their existing
    accounting password to link their SyftHub account with their existing
    accounting account.

    Example:
        try:
            client.auth.register(username="john", email="john@example.com", ...)
        except AccountingAccountExistsError as e:
            # Prompt user for their existing accounting password
            accounting_password = input("Enter your existing accounting password: ")
            # Retry registration with the password
            client.auth.register(
                username="john",
                email="john@example.com",
                ...,
                accounting_password=accounting_password
            )
    """

    requires_accounting_password: bool = True

    def __init__(
        self,
        message: str = "This email already has an account in the accounting service",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=409, detail=detail)


class InvalidAccountingPasswordError(SyftHubError):
    """Raised when the provided accounting password is invalid."""

    def __init__(
        self,
        message: str = "The provided accounting password is invalid",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=401, detail=detail)


class AccountingServiceUnavailableError(SyftHubError):
    """Raised when the accounting service is unavailable or returns an error."""

    def __init__(
        self,
        message: str = "Accounting service is unavailable",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=503, detail=detail)
