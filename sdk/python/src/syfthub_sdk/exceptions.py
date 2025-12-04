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
    """Raised when request validation fails (422)."""

    def __init__(
        self,
        message: str = "Validation error",
        detail: Any = None,
    ) -> None:
        super().__init__(message, status_code=422, detail=detail)


class APIError(SyftHubError):
    """Raised for other API errors."""

    pass


class ConfigurationError(SyftHubError):
    """Raised when SDK configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=None, detail=None)
