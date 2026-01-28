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

from .app import SyftAPI
from .config import Settings, load_settings
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    EndpointRegistrationError,
    SyftAPIError,
    SyncError,
)
from .logging import get_logger, setup_logging
from .schemas import (
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
)

__version__ = "0.1.0"

__all__ = [
    # Core
    "SyftAPI",
    # Configuration
    "Settings",
    "load_settings",
    # Logging
    "setup_logging",
    "get_logger",
    # Exceptions
    "SyftAPIError",
    "AuthenticationError",
    "ConfigurationError",
    "EndpointRegistrationError",
    "SyncError",
    # Enums
    "EndpointType",
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
    # Metadata
    "__version__",
]
