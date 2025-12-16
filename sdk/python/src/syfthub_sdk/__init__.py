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

    # Chat with RAG via aggregator
    response = client.chat.complete(
        prompt="What is machine learning?",
        model="alice/gpt-model",
        data_sources=["bob/ml-docs"],
    )
    print(response.response)

    # Streaming chat
    for event in client.chat.stream(prompt="...", model="..."):
        if event.type == "token":
            print(event.content, end="")
"""

from syfthub_sdk._pagination import PageIterator
from syfthub_sdk.chat import (
    ChatResource,
    # Streaming events
    ChatStreamEvent,
    DoneEvent,
    ErrorEvent,
    GenerationStartEvent,
    RetrievalCompleteEvent,
    RetrievalStartEvent,
    SourceCompleteEvent,
    TokenEvent,
)
from syfthub_sdk.client import SyftHubClient
from syfthub_sdk.exceptions import (
    APIError,
    AggregatorError,
    AuthenticationError,
    AuthorizationError,
    ChatError,
    ConfigurationError,
    EndpointResolutionError,
    GenerationError,
    NotFoundError,
    RetrievalError,
    SyftHubError,
    ValidationError,
)
from syfthub_sdk.models import (
    # Backward compatibility aliases (deprecated)
    AccountingBalance,
    AccountingTransaction,
    # Accounting models
    AccountingCredentials,
    AccountingUser,
    # Core models
    AuthTokens,
    # Chat models
    ChatMetadata,
    ChatResponse,
    Connection,
    CreatorType,
    Document,
    Endpoint,
    EndpointPublic,
    EndpointRef,
    EndpointType,
    Message,
    Policy,
    SourceInfo,
    SourceStatus,
    Transaction,
    TransactionStatus,
    User,
    UserRole,
    Visibility,
)
from syfthub_sdk.syftai import SyftAIResource

__version__ = "0.1.0"

__all__ = [
    # Main client
    "SyftHubClient",
    # Core models
    "User",
    "UserRole",
    "Endpoint",
    "EndpointPublic",
    "EndpointType",
    "AuthTokens",
    "Visibility",
    "Policy",
    "Connection",
    # Chat models
    "EndpointRef",
    "Document",
    "SourceInfo",
    "SourceStatus",
    "ChatMetadata",
    "ChatResponse",
    "Message",
    # Chat streaming events
    "ChatStreamEvent",
    "RetrievalStartEvent",
    "SourceCompleteEvent",
    "RetrievalCompleteEvent",
    "GenerationStartEvent",
    "TokenEvent",
    "DoneEvent",
    "ErrorEvent",
    # Resources (for type hints)
    "ChatResource",
    "SyftAIResource",
    # Accounting models
    "AccountingCredentials",
    "AccountingUser",
    "Transaction",
    "TransactionStatus",
    "CreatorType",
    # Backward compatibility (deprecated)
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
    # Chat exceptions
    "ChatError",
    "AggregatorError",
    "RetrievalError",
    "GenerationError",
    "EndpointResolutionError",
    # Utilities
    "PageIterator",
]
