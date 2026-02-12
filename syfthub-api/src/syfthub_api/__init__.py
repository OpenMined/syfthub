"""
SyftHub API Framework

A Python framework for building SyftAI Spaces with a FastAPI-like interface.

This package provides a simple, decorator-based approach to define data source
and model endpoints that integrate with the SyftHub ecosystem.

Example:
    from syfthub_api import SyftAPI, Document, Message

    app = SyftAPI()

    @app.datasource(slug="my-data", name="My Data", description="My data source")
    async def search(query: str) -> list[Document]:
        return [Document(document_id="1", content="...", similarity_score=0.9)]

    @app.model(slug="my-model", name="My Model", description="My model")
    async def generate(messages: list[Message]) -> str:
        return "Hello!"

    if __name__ == "__main__":
        import asyncio
        asyncio.run(app.run())
"""

from policy_manager.context import RequestContext

from .app import SyftAPI
from .config import Settings, load_settings, derive_nats_ws_url, TUNNELING_PREFIX
from .heartbeat import HeartbeatManager
from .nats_transport import NATSSpaceTransport
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    EndpointRegistrationError,
    PolicyDeniedError,
    SyftAPIError,
    SyncError,
)
from .logging import get_logger, setup_logging

# File-based endpoint mode (lazy import to avoid circular dependencies)
from .file_mode import (
    FileBasedEndpointProvider,
    EndpointLoader,
    PolicyFactory,
    FileSystemWatcher,
    EndpointConfig,
    PolicyConfig,
)
from .schemas import (
    # Auth
    UserContext,
    # Request schemas
    DataSourceQueryRequest,
    # Response schemas
    DataSourceQueryResponse,
    # Data types (for user construction)
    Document,
    # Enums
    EndpointType,
    Message,
    ModelQueryRequest,
    ModelQueryResponse,
    ModelSummary,
    ProviderInfo,
    References,
    ResponseMessage,
    TokenUsage,
    # Tunnel protocol schemas
    TUNNEL_PROTOCOL_VERSION,
    TunnelEndpointInfo,
    TunnelError,
    TunnelErrorCode,
    TunnelRequest,
    TunnelResponse,
    TunnelTiming,
)

__version__ = "0.1.0"

__all__ = [
    # Core
    "SyftAPI",
    # Auth / Policy context
    "UserContext",
    "RequestContext",
    # Heartbeat
    "HeartbeatManager",
    # NATS Transport
    "NATSSpaceTransport",
    # Configuration
    "Settings",
    "load_settings",
    "derive_nats_ws_url",
    "TUNNELING_PREFIX",
    # Logging
    "setup_logging",
    "get_logger",
    # Exceptions
    "SyftAPIError",
    "AuthenticationError",
    "ConfigurationError",
    "EndpointRegistrationError",
    "PolicyDeniedError",
    "SyncError",
    # Enums
    "EndpointType",
    "TunnelErrorCode",
    # Request schemas
    "DataSourceQueryRequest",
    "Message",
    "ModelQueryRequest",
    # Response schemas
    "DataSourceQueryResponse",
    "ModelQueryResponse",
    # Data types
    "Document",
    "ModelSummary",
    "ProviderInfo",
    "References",
    "ResponseMessage",
    "TokenUsage",
    # Tunnel protocol
    "TUNNEL_PROTOCOL_VERSION",
    "TunnelEndpointInfo",
    "TunnelError",
    "TunnelRequest",
    "TunnelResponse",
    "TunnelTiming",
    # File-based endpoint mode
    "FileBasedEndpointProvider",
    "EndpointLoader",
    "PolicyFactory",
    "FileSystemWatcher",
    "EndpointConfig",
    "PolicyConfig",
    # Metadata
    "__version__",
]
