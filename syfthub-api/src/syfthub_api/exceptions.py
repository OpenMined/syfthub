"""
Custom exceptions for the SyftHub API framework.

This module defines a hierarchy of exceptions for handling errors
in the SyftAPI framework, including configuration, authentication,
synchronization, and endpoint registration errors.

Exception Hierarchy:
    SyftAPIError (base)
    ├── ConfigurationError
    ├── AuthenticationError
    ├── SyncError
    ├── EndpointRegistrationError
    └── PolicyDeniedError
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from policy_manager.result import PolicyResult


class SyftAPIError(Exception):
    """
    Base exception for all SyftHub API errors.

    All exceptions raised by the SyftAPI framework inherit from this class,
    allowing users to catch all framework-specific errors with a single
    except clause if desired.

    Attributes:
        message: Human-readable error description.
        cause: Optional underlying exception that caused this error.

    Example:
        try:
            await app.run()
        except SyftAPIError as e:
            print(f"SyftAPI error: {e}")
            if e.cause:
                print(f"Caused by: {e.cause}")
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        """
        Initialize the exception.

        Args:
            message: Human-readable error description.
            cause: Optional underlying exception that caused this error.
        """
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __str__(self) -> str:
        if self.cause:
            return f"{self.message} (caused by: {self.cause})"
        return self.message


class ConfigurationError(SyftAPIError):
    """
    Raised when configuration is invalid or missing.

    This exception is raised when required configuration values
    (such as syfthub_url, username, password, or space_url) are
    not provided or are invalid.

    Example:
        try:
            app = SyftAPI()  # Missing required config
        except ConfigurationError as e:
            print(f"Configuration error: {e}")
    """

    pass


class AuthenticationError(SyftAPIError):
    """
    Raised when authentication with SyftHub fails.

    This exception is raised when the framework fails to authenticate
    with the SyftHub backend, which may be due to invalid credentials,
    network issues, or server errors.

    Example:
        try:
            await app.run()
        except AuthenticationError as e:
            print(f"Authentication failed: {e}")
    """

    pass


class SyncError(SyftAPIError):
    """
    Raised when endpoint synchronization fails.

    This exception is raised when the framework fails to synchronize
    registered endpoints with the SyftHub backend after successful
    authentication.

    Example:
        try:
            await app.run()
        except SyncError as e:
            print(f"Failed to sync endpoints: {e}")
    """

    pass


class EndpointRegistrationError(SyftAPIError):
    """
    Raised when endpoint registration is invalid.

    This exception is raised when an endpoint definition is invalid,
    such as when:
    - The slug format is invalid
    - A duplicate slug is registered
    - The name or description is empty
    - The endpoint function is not async

    Example:
        try:
            @app.datasource(slug="invalid slug!", name="", description="...")
            async def my_endpoint(query: str):
                pass
        except EndpointRegistrationError as e:
            print(f"Invalid endpoint: {e}")
    """

    pass


class PolicyDeniedError(SyftAPIError):
    """
    Raised when a policy denies a request.

    This exception is raised during endpoint invocation when a policy
    in the pre-execution or post-execution chain returns a denial or
    pending result.

    Attributes:
        result: The PolicyResult that caused the denial.

    Example:
        try:
            await app.run()
        except PolicyDeniedError as e:
            print(f"Denied by {e.result.policy_name}: {e.result.reason}")
            if e.result.pending:
                print(f"Request is pending review")
    """

    def __init__(self, result: PolicyResult) -> None:
        self.result = result
        message = f"Policy '{result.policy_name}' denied: {result.reason}"
        super().__init__(message)
