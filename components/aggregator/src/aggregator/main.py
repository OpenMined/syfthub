"""Main FastAPI application for the aggregator service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aggregator.api import api_router, health_router
from aggregator.core.config import get_settings
from aggregator.observability import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
    configure_logging,
    get_logger,
)

# Get settings for logging configuration
_settings = get_settings()

# Configure structured logging
configure_logging(
    log_level=_settings.log_level,
    log_format=_settings.log_format if not _settings.debug else "console",
    development_mode=_settings.debug,
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(f"Starting {settings.service_name}")
    logger.info(f"SyftHub URL: {settings.syfthub_url}")
    logger.info(f"Debug mode: {settings.debug}")

    yield

    logger.info(f"Shutting down {settings.service_name}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="SyftHub Aggregator",
        description="""
RAG orchestration service for SyftHub.

This service aggregates context from multiple data sources and generates
responses using model endpoints registered in SyftHub.

## Features

- **Context Retrieval**: Query multiple data sources in parallel
- **RAG Prompting**: Build augmented prompts with retrieved context
- **Streaming**: Real-time response streaming with SSE
- **Flexible**: Works with any model/data source endpoints in SyftHub

## Workflow

1. Frontend sends prompt + model + data sources
2. Aggregator resolves endpoints via SyftHub
3. Queries data sources for relevant documents (parallel)
4. Builds augmented prompt with context
5. Calls model endpoint
6. Returns/streams response to frontend
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add observability middleware (order matters - CorrelationID must be first to process)
    # Middleware executes in reverse order of addition, so add RequestLogging first
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths={"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"},
        log_request_headers=settings.log_request_headers,
        log_request_body=settings.log_request_body,
    )
    app.add_middleware(CorrelationIDMiddleware)

    # Include routers
    app.include_router(health_router)  # /health, /ready
    app.include_router(api_router)  # /api/v1/chat, /api/v1/chat/stream

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "aggregator.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
