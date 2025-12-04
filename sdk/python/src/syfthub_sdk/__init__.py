"""SyftHub SDK - Python client for interacting with SyftHub API.

Example usage:
    from syfthub_sdk import SyftHubClient

    client = SyftHubClient(base_url="https://hub.syft.com")
    client.auth.login(username="john", password="secret123")

    # Your endpoints
    for endpoint in client.my_endpoints.list():
        print(endpoint.name)

    # Browse public endpoints
    for endpoint in client.hub.browse():
        print(f"{endpoint.path}: {endpoint.name}")
"""

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.client import SyftHubClient
from syfthub_sdk.exceptions import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    NotFoundError,
    SyftHubError,
    ValidationError,
)
from syfthub_sdk.models import (
    AccountingBalance,
    AccountingTransaction,
    AuthTokens,
    Connection,
    Endpoint,
    EndpointPublic,
    EndpointType,
    Policy,
    User,
    UserRole,
    Visibility,
)

__version__ = "0.1.0"

__all__ = [
    # Main client
    "SyftHubClient",
    # Models
    "User",
    "UserRole",
    "Endpoint",
    "EndpointPublic",
    "EndpointType",
    "AuthTokens",
    "Visibility",
    "Policy",
    "Connection",
    "AccountingBalance",
    "AccountingTransaction",
    # Exceptions
    "SyftHubError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "APIError",
    "ConfigurationError",
    # Utilities
    "PageIterator",
]
