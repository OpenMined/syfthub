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
from syfthub_sdk.aggregators import AggregatorsResource
from syfthub_sdk.api_tokens import APITokensResource
from syfthub_sdk.chat import (
    ChatResource,
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
    AggregatorError,
    APIError,
    AuthenticationError,
    AuthorizationError,
    ChatError,
    ConfigurationError,
    EndpointResolutionError,
    GenerationError,
    NetworkError,
    NotFoundError,
    RetrievalError,
    SyftHubError,
    UserAlreadyExistsError,
    ValidationError,
)
from syfthub_sdk.models import (
    AccountingCredentials,
    AccountingUser,
    APIToken,
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenScope,
    AuthTokens,
    ChatMetadata,
    ChatResponse,
    Connection,
    CreateAPITokenInput,
    CreatorType,
    Document,
    DocumentSource,
    Endpoint,
    EndpointPublic,
    EndpointRef,
    EndpointSearchResponse,
    EndpointSearchResult,
    EndpointType,
    HeartbeatResponse,
    Message,
    NatsCredentials,
    OrganizationRole,
    PeerTokenResponse,
    Policy,
    SatelliteTokenResponse,
    SourceInfo,
    SourceStatus,
    SyncEndpointsResponse,
    TokenUsage,
    Transaction,
    TransactionStatus,
    UpdateAPITokenInput,
    User,
    UserAggregator,
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
    "OrganizationRole",
    "Endpoint",
    "EndpointPublic",
    "EndpointSearchResult",
    "EndpointSearchResponse",
    "EndpointType",
    "AuthTokens",
    "PeerTokenResponse",
    "SatelliteTokenResponse",
    "Visibility",
    "Policy",
    "Connection",
    # API Token models
    "APIToken",
    "APITokenScope",
    "APITokenCreateResponse",
    "APITokenListResponse",
    "CreateAPITokenInput",
    "UpdateAPITokenInput",
    # Chat models
    "EndpointRef",
    "Document",
    "DocumentSource",
    "SourceInfo",
    "SourceStatus",
    "ChatMetadata",
    "ChatResponse",
    "TokenUsage",
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
    "APITokensResource",
    "ChatResource",
    "SyftAIResource",
    # NATS models
    "NatsCredentials",
    # Accounting models
    "AccountingCredentials",
    "AccountingUser",
    "Transaction",
    "TransactionStatus",
    "CreatorType",
    # Sync models
    "SyncEndpointsResponse",
    # Heartbeat models
    "HeartbeatResponse",
    # User Aggregator models
    "UserAggregator",
    "AggregatorsResource",
    # Exceptions
    "SyftHubError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "APIError",
    "ConfigurationError",
    "NetworkError",
    "UserAlreadyExistsError",
    # Chat exceptions
    "ChatError",
    "AggregatorError",
    "RetrievalError",
    "GenerationError",
    "EndpointResolutionError",
    # Utilities
    "PageIterator",
]
