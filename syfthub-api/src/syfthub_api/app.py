"""
SyftHub API Framework - Core Application Module

Provides the SyftAPI class for building SyftAI Spaces with a FastAPI-like interface.
"""

# Standard library
import asyncio
import inspect
import json
import os
import re
import signal
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import wraps
from typing import Any

# Third-party
import uvicorn
from fastapi import APIRouter, FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from syfthub_sdk import SyftHubClient, User, Visibility

# Local
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    EndpointRegistrationError,
    SyncError,
)
from .heartbeat import HeartbeatManager
from .logging import setup_logging
from .config import TUNNELING_PREFIX
from .schemas import (
    DataSourceQueryRequest,
    DataSourceQueryResponse,
    Document,
    EndpointType,
    Message,
    ModelQueryRequest,
    ModelQueryResponse,
    ModelSummary,
    References,
    ResponseMessage,
    TunnelError,
    TunnelErrorCode,
    TunnelResponse,
    TunnelTiming,
    TUNNEL_PROTOCOL_VERSION,
)

# Slug validation pattern: lowercase alphanumeric, hyphens, underscores, 1-64 chars
# Must start with alphanumeric, can end with alphanumeric or be single char
_SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$")

# Validation constants
_MAX_NAME_LENGTH = 100
_MAX_DESCRIPTION_LENGTH = 500

# Type aliases for lifecycle hooks and middleware
LifecycleHook = Callable[[], Awaitable[None]]
MiddlewareCallNext = Callable[[Request], Awaitable[Response]]
MiddlewareDispatch = Callable[[Request, MiddlewareCallNext], Awaitable[Response]]


class SyftAPI:
    """
    Main application class for building SyftAI Spaces.

    Provides decorators for registering data source and model endpoints,
    and handles synchronization with the SyftHub backend.

    Example:
        app = SyftAPI()

        @app.datasource(slug="my-data", name="My Data", description="...")
        async def search(query: str) -> list[Document]:
            return [...]

        asyncio.run(app.run())

    Raises:
        ConfigurationError: If required configuration is missing.
        EndpointRegistrationError: If endpoint registration is invalid.
        AuthenticationError: If authentication with SyftHub fails.
        SyncError: If endpoint synchronization fails.
    """

    def __init__(
        self,
        syfthub_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        space_url: str | None = None,
        log_level: str = "INFO",
        heartbeat_enabled: bool | None = None,
        heartbeat_ttl_seconds: int | None = None,
        heartbeat_interval_multiplier: float | None = None,
    ) -> None:
        """
        Initialize the SyftAPI application.

        Args:
            syfthub_url: URL of the SyftHub backend. Falls back to SYFTHUB_URL env var.
            username: SyftHub username. Falls back to SYFTHUB_USERNAME env var.
            password: SyftHub password. Falls back to SYFTHUB_PASSWORD env var.
            space_url: Public URL of this SyftAI Space. Falls back to SPACE_URL env var.
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                Falls back to LOG_LEVEL env var. Defaults to INFO.
            heartbeat_enabled: Enable periodic heartbeat to SyftHub.
                Falls back to HEARTBEAT_ENABLED env var. Defaults to True.
            heartbeat_ttl_seconds: Heartbeat TTL in seconds (1-3600, server caps at 600).
                Falls back to HEARTBEAT_TTL_SECONDS env var. Defaults to 300.
            heartbeat_interval_multiplier: Send heartbeat at TTL * multiplier.
                Falls back to HEARTBEAT_INTERVAL_MULTIPLIER env var. Defaults to 0.8.

        Raises:
            ConfigurationError: If required configuration is missing.
        """
        # Setup logging
        effective_log_level = log_level or os.environ.get("LOG_LEVEL", "INFO")
        self._logger = setup_logging(level=effective_log_level)

        self.endpoints: list[dict[str, Any]] = []
        self._syfthub_url = syfthub_url or os.environ.get("SYFTHUB_URL")
        self._username = username or os.environ.get("SYFTHUB_USERNAME")
        self._password = password or os.environ.get("SYFTHUB_PASSWORD")
        self._space_url = space_url or os.environ.get("SPACE_URL")

        if not self._syfthub_url:
            raise ConfigurationError("syfthub_url must be provided or set as SYFTHUB_URL env var")
        if not self._username:
            raise ConfigurationError("username must be provided or set as SYFTHUB_USERNAME env var")
        if not self._password:
            raise ConfigurationError("password must be provided or set as SYFTHUB_PASSWORD env var")
        if not self._space_url:
            raise ConfigurationError("space_url must be provided or set as SPACE_URL env var")

        # Heartbeat configuration
        if heartbeat_enabled is not None:
            self._heartbeat_enabled = heartbeat_enabled
        else:
            env_val = os.environ.get("HEARTBEAT_ENABLED", "true")
            self._heartbeat_enabled = env_val.lower() in ("true", "1", "yes")

        if heartbeat_ttl_seconds is not None:
            self._heartbeat_ttl_seconds = heartbeat_ttl_seconds
        else:
            self._heartbeat_ttl_seconds = int(os.environ.get("HEARTBEAT_TTL_SECONDS", "300"))

        if heartbeat_interval_multiplier is not None:
            self._heartbeat_interval_multiplier = heartbeat_interval_multiplier
        else:
            self._heartbeat_interval_multiplier = float(
                os.environ.get("HEARTBEAT_INTERVAL_MULTIPLIER", "0.8")
            )

        # Heartbeat manager (initialized after authentication)
        self._heartbeat_manager: HeartbeatManager | None = None
        self._client: SyftHubClient | None = None

        # Lifecycle hooks and middleware
        self._on_startup: list[LifecycleHook] = []
        self._on_shutdown: list[LifecycleHook] = []
        self._middleware: list[tuple[type, dict[str, Any]]] = []
        self._middleware_dispatch: list[MiddlewareDispatch] = []

        # Testing flag - skip sync when True
        self._skip_sync: bool = False

        # Tunneling mode attributes
        self._is_tunneling: bool = self._space_url.startswith(TUNNELING_PREFIX)
        self._tunnel_shutdown: bool = False
        self._pending_responses: dict[str, asyncio.Future[dict[str, Any]]] = {}

        # Tunnel consumer configuration
        self._tunnel_poll_interval: float = 0.5  # seconds between polls when queue empty
        self._tunnel_batch_size: int = 10  # messages per consume call

        self._logger.debug(
            "SyftAPI initialized with syfthub_url=%s, space_url=%s, heartbeat_enabled=%s, tunneling=%s",
            self._syfthub_url,
            self._space_url,
            self._heartbeat_enabled,
            self._is_tunneling,
        )

    def on_startup(self, fn: LifecycleHook) -> LifecycleHook:
        """
        Decorator to register a function to run on application startup.

        The decorated function must be async and take no arguments.

        Args:
            fn: Async function to run on startup.

        Returns:
            The original function (unmodified).

        Example:
            @app.on_startup
            async def init_database():
                await db.connect()
        """
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("Startup hook must be an async function")
        self._on_startup.append(fn)
        return fn

    def on_shutdown(self, fn: LifecycleHook) -> LifecycleHook:
        """
        Decorator to register a function to run on application shutdown.

        The decorated function must be async and take no arguments.

        Args:
            fn: Async function to run on shutdown.

        Returns:
            The original function (unmodified).

        Example:
            @app.on_shutdown
            async def cleanup():
                await db.disconnect()
        """
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("Shutdown hook must be an async function")
        self._on_shutdown.append(fn)
        return fn

    def add_middleware(self, middleware_class: type, **options: Any) -> None:
        """
        Add a Starlette/FastAPI middleware class.

        Args:
            middleware_class: The middleware class to add.
            **options: Keyword arguments to pass to the middleware constructor.

        Example:
            from starlette.middleware.cors import CORSMiddleware

            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
            )
        """
        self._middleware.append((middleware_class, options))

    def middleware(self, fn: MiddlewareDispatch) -> MiddlewareDispatch:
        """
        Decorator to add a custom middleware function.

        The decorated function receives a Request and a call_next function,
        and must return a Response.

        Args:
            fn: Middleware dispatch function.

        Returns:
            The original function (unmodified).

        Example:
            @app.middleware
            async def log_requests(request: Request, call_next):
                start = time.time()
                response = await call_next(request)
                duration = time.time() - start
                print(f"{request.method} {request.url.path} - {duration:.3f}s")
                return response
        """
        if not inspect.iscoroutinefunction(fn):
            raise TypeError("Middleware function must be async")
        self._middleware_dispatch.append(fn)
        return fn

    def _validate_slug(self, slug: str) -> None:
        """
        Validate endpoint slug format and uniqueness.

        Args:
            slug: The slug to validate.

        Raises:
            EndpointRegistrationError: If slug is invalid or duplicate.
        """
        if not slug:
            raise EndpointRegistrationError("Endpoint slug cannot be empty")

        if not _SLUG_PATTERN.match(slug):
            raise EndpointRegistrationError(
                f"Invalid slug '{slug}'. Slugs must be 1-64 characters, "
                "lowercase alphanumeric with hyphens/underscores allowed, "
                "and must start with a letter or number."
            )

        # Check for duplicates
        existing_slugs = {ep["slug"] for ep in self.endpoints}
        if slug in existing_slugs:
            raise EndpointRegistrationError(
                f"Duplicate endpoint slug '{slug}'. Each endpoint must have a unique slug."
            )

    def _validate_name(self, name: str, slug: str) -> None:
        """
        Validate endpoint name.

        Args:
            name: The name to validate.
            slug: The endpoint slug (for error messages).

        Raises:
            EndpointRegistrationError: If name is invalid.
        """
        if not name or not name.strip():
            raise EndpointRegistrationError(f"Endpoint name cannot be empty for slug '{slug}'")
        if len(name) > _MAX_NAME_LENGTH:
            raise EndpointRegistrationError(
                f"Endpoint name exceeds {_MAX_NAME_LENGTH} characters for slug '{slug}'"
            )

    def _validate_description(self, description: str, slug: str) -> None:
        """
        Validate endpoint description.

        Args:
            description: The description to validate.
            slug: The endpoint slug (for error messages).

        Raises:
            EndpointRegistrationError: If description is invalid.
        """
        if not description or not description.strip():
            raise EndpointRegistrationError(
                f"Endpoint description cannot be empty for slug '{slug}'"
            )
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            raise EndpointRegistrationError(
                f"Endpoint description exceeds {_MAX_DESCRIPTION_LENGTH} characters "
                f"for slug '{slug}'"
            )

    def _register_endpoint(
        self,
        endpoint_type: EndpointType,
        slug: str,
        name: str,
        description: str,
        fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """
        Register an endpoint internally.

        Args:
            endpoint_type: Type of endpoint (DATA_SOURCE or MODEL).
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the endpoint.
            fn: Async function that handles requests.

        Raises:
            EndpointRegistrationError: If validation fails (invalid slug, name,
                description, duplicate slug, or non-async function).
        """
        # Validate all inputs
        self._validate_slug(slug)
        self._validate_name(name, slug)
        self._validate_description(description, slug)

        if not inspect.iscoroutinefunction(fn):
            raise EndpointRegistrationError(f"Endpoint function for '{slug}' must be async")

        self.endpoints.append(
            {
                "type": endpoint_type,
                "slug": slug,
                "name": name,
                "description": description,
                "fn": fn,
            }
        )

    def datasource(
        self, slug: str, name: str, description: str
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, list[Document]]]],
        Callable[..., Coroutine[Any, Any, list[Document]]],
    ]:
        """
        Decorator to register a data source endpoint.

        The decorated function should accept a `query: str` parameter and return
        a list of Document objects.

        Args:
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the data source.

        Returns:
            Decorator function.

        Example:
            @app.datasource(slug="papers", name="Papers", description="Scientific papers")
            async def search_papers(query: str) -> list[Document]:
                return [Document(...), ...]
        """

        def decorator(
            fn: Callable[..., Coroutine[Any, Any, list[Document]]],
        ) -> Callable[..., Coroutine[Any, Any, list[Document]]]:
            self._register_endpoint(EndpointType.DATA_SOURCE, slug, name, description, fn)

            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> list[Document]:
                return await fn(*args, **kwargs)

            return wrapper

        return decorator

    def model(
        self, slug: str, name: str, description: str
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, str]]],
        Callable[..., Coroutine[Any, Any, str]],
    ]:
        """
        Decorator to register a model endpoint.

        The decorated function should accept a `messages: list[Message]` parameter
        and return a string response.

        Args:
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the model.

        Returns:
            Decorator function.

        Example:
            @app.model(slug="echo", name="Echo Model", description="Echoes input")
            async def echo(messages: list[Message]) -> str:
                return messages[-1].content
        """

        def decorator(
            fn: Callable[..., Coroutine[Any, Any, str]],
        ) -> Callable[..., Coroutine[Any, Any, str]]:
            self._register_endpoint(EndpointType.MODEL, slug, name, description, fn)

            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> str:
                return await fn(*args, **kwargs)

            return wrapper

        return decorator

    async def _sync_endpoints(self) -> None:
        """
        Synchronize registered endpoints with the SyftHub backend.

        Raises:
            AuthenticationError: If authentication with SyftHub fails.
            SyncError: If endpoint synchronization fails.
        """
        self._logger.info("Authenticating with SyftHub at %s...", self._syfthub_url)
        client = SyftHubClient(base_url=self._syfthub_url)

        # These are validated in __init__ so they cannot be None here
        assert self._username is not None
        assert self._password is not None

        try:
            user: User = await asyncio.to_thread(
                client.auth.login, username=self._username, password=self._password
            )
            self._logger.info("Successfully authenticated as user: %s", user.username)

            # Update user's domain
            updated_user = await asyncio.to_thread(client.users.update, domain=self._space_url)
            self._logger.info("User domain updated to: %s", updated_user.domain)

            # Store client for heartbeat use
            self._client = client

        except AuthenticationError:
            # Re-raise if already wrapped
            raise
        except Exception as e:
            self._logger.error("Authentication failed: %s", e)
            raise AuthenticationError(f"Failed to authenticate with SyftHub: {e}", cause=e) from e

        self._logger.info("Syncing %d endpoints with SyftHub...", len(self.endpoints))
        endpoints_to_sync = []
        for endpoint in self.endpoints:
            endpoints_to_sync.append(
                {
                    "name": endpoint["name"],
                    "slug": endpoint["slug"],
                    "type": endpoint["type"].value,
                    "description": endpoint["description"],
                    "visibility": Visibility.PUBLIC.value,
                    "connect": [{"type": "http", "config": {"url": self._space_url}}],
                }
            )

        if endpoints_to_sync:
            try:
                result = await asyncio.to_thread(
                    client.my_endpoints.sync, endpoints=endpoints_to_sync
                )
                self._logger.info(
                    "Successfully synced %d endpoints (deleted %d old endpoints)",
                    result.synced,
                    result.deleted,
                )
            except SyncError:
                # Re-raise if already wrapped
                raise
            except Exception as e:
                self._logger.error("Failed to sync endpoints: %s", e)
                raise SyncError(f"Failed to sync endpoints with SyftHub: {e}", cause=e) from e
        else:
            self._logger.info("No endpoints to sync")

    async def _start_heartbeat(self) -> None:
        """
        Start the heartbeat manager if enabled.

        The heartbeat manager sends periodic requests to SyftHub to indicate
        that this space is alive and available.
        """
        if not self._heartbeat_enabled:
            self._logger.debug("Heartbeat is disabled")
            return

        if self._client is None:
            self._logger.warning("Cannot start heartbeat: client not authenticated")
            return

        assert self._space_url is not None  # Validated in __init__

        self._heartbeat_manager = HeartbeatManager(
            client=self._client,
            space_url=self._space_url,
            ttl_seconds=self._heartbeat_ttl_seconds,
            interval_multiplier=self._heartbeat_interval_multiplier,
        )
        await self._heartbeat_manager.start()

    async def _stop_heartbeat(self) -> None:
        """
        Stop the heartbeat manager gracefully.
        """
        if self._heartbeat_manager is not None:
            await self._heartbeat_manager.stop()
            self._heartbeat_manager = None

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """
        Manage application lifecycle with startup and shutdown hooks.

        This is used as the lifespan context manager for FastAPI.
        """
        # Run startup hooks
        self._logger.debug("Running %d startup hooks...", len(self._on_startup))
        for hook in self._on_startup:
            try:
                self._logger.debug("Running startup hook: %s", hook.__name__)
                await hook()
            except Exception as e:
                self._logger.error("Startup hook '%s' failed: %s", hook.__name__, e)
                raise

        yield  # Application runs here

        # Run shutdown hooks
        self._logger.debug("Running %d shutdown hooks...", len(self._on_shutdown))
        for hook in self._on_shutdown:
            try:
                self._logger.debug("Running shutdown hook: %s", hook.__name__)
                await hook()
            except Exception as e:
                self._logger.error("Shutdown hook '%s' failed: %s", hook.__name__, e)
                # Don't raise on shutdown - try to clean up everything

    def _find_endpoint_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Find a registered endpoint by its slug.

        Args:
            slug: The endpoint slug to find.

        Returns:
            The endpoint dict if found, None otherwise.
        """
        for endpoint in self.endpoints:
            if endpoint["slug"] == slug:
                return endpoint
        return None

    async def _invoke_datasource_handler(
        self, endpoint: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a DATA_SOURCE endpoint handler.

        This method is used by both HTTP handlers and tunnel mode.

        Args:
            endpoint: The registered endpoint dict.
            payload: Request payload with 'messages' (query), 'limit', etc.

        Returns:
            Response dict with 'references' containing documents.
        """
        fn = endpoint["fn"]
        query = payload.get("messages", "")

        # Call user's async function
        documents = await fn(query=query)

        # Format response
        return {
            "summary": None,
            "references": {
                "documents": [
                    doc.model_dump() if hasattr(doc, "model_dump") else doc for doc in documents
                ],
                "provider_info": None,
                "cost": None,
            },
        }

    async def _invoke_model_handler(
        self, endpoint: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke a MODEL endpoint handler.

        This method is used by both HTTP handlers and tunnel mode.

        Args:
            endpoint: The registered endpoint dict.
            payload: Request payload with 'messages' list.

        Returns:
            Response dict with 'summary' containing model response.
        """
        fn = endpoint["fn"]
        raw_messages = payload.get("messages", [])

        # Convert to Message objects if they're dicts
        messages = [Message(**m) if isinstance(m, dict) else m for m in raw_messages]

        # Call user's async function
        response_content = await fn(messages=messages)

        # Generate unique response ID (OpenAI-style format)
        response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        # Format response
        return {
            "summary": {
                "id": response_id,
                "model": endpoint["slug"],
                "message": {
                    "role": "assistant",
                    "content": response_content,
                    "tokens": None,
                },
                "finish_reason": "stop",
                "usage": None,
                "cost": None,
                "provider_info": None,
            },
            "references": None,
        }

    def _build_fastapi_app(self) -> FastAPI:
        """Build the FastAPI application with registered endpoints."""
        app = FastAPI(title="SyftAI Space", lifespan=self._lifespan)

        # Add user-defined middleware classes (in reverse order for correct execution)
        for middleware_class, options in reversed(self._middleware):
            app.add_middleware(middleware_class, **options)

        # Add custom middleware dispatch functions
        for dispatch_fn in self._middleware_dispatch:
            app.add_middleware(BaseHTTPMiddleware, dispatch=dispatch_fn)

        # Build router with endpoints
        router = APIRouter(prefix="/api/v1/endpoints")

        for endpoint in self.endpoints:
            if endpoint["type"] == EndpointType.DATA_SOURCE:
                ds_handler = self._create_datasource_handler(endpoint)
                router.add_api_route(
                    f"/{endpoint['slug']}/query",
                    ds_handler,
                    methods=["POST"],
                    response_model=DataSourceQueryResponse,
                )
            elif endpoint["type"] == EndpointType.MODEL:
                model_handler = self._create_model_handler(endpoint)
                router.add_api_route(
                    f"/{endpoint['slug']}/query",
                    model_handler,
                    methods=["POST"],
                    response_model=ModelQueryResponse,
                )

        app.include_router(router)
        return app

    def get_app(self) -> FastAPI:
        """
        Get the underlying FastAPI application.

        This is useful for advanced customization or testing with TestClient.
        Note: This builds a new app instance each time it's called.

        Returns:
            FastAPI application instance.

        Example:
            from fastapi.testclient import TestClient

            app = SyftAPI(...)
            fastapi_app = app.get_app()
            client = TestClient(fastapi_app)
            response = client.post("/api/v1/endpoints/my-endpoint/query", json={...})
        """
        return self._build_fastapi_app()

    def _create_datasource_handler(
        self, endpoint: dict[str, Any]
    ) -> Callable[[DataSourceQueryRequest], Coroutine[Any, Any, DataSourceQueryResponse]]:
        """Create a request handler for a data source endpoint."""

        async def handler(request: DataSourceQueryRequest) -> DataSourceQueryResponse:
            payload = {
                "messages": request.messages,
                "limit": request.limit,
                "similarity_threshold": request.similarity_threshold,
                "include_metadata": request.include_metadata,
                "transaction_token": request.transaction_token,
            }
            result = await self._invoke_datasource_handler(endpoint, payload)
            return DataSourceQueryResponse(**result)

        return handler

    def _create_model_handler(
        self, endpoint: dict[str, Any]
    ) -> Callable[[ModelQueryRequest], Coroutine[Any, Any, ModelQueryResponse]]:
        """Create a request handler for a model endpoint."""

        async def handler(request: ModelQueryRequest) -> ModelQueryResponse:
            payload = {
                "messages": [m.model_dump() for m in request.messages],
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": request.stream,
                "stop_sequences": request.stop_sequences,
                "transaction_token": request.transaction_token,
            }
            result = await self._invoke_model_handler(endpoint, payload)
            return ModelQueryResponse(**result)

        return handler

    async def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Start the SyftAI Space server.

        This method:
        1. Synchronizes endpoints with the SyftHub backend (unless _skip_sync is True)
        2. Starts the heartbeat manager (if enabled)
        3. Starts either HTTP server or tunnel consumer based on space_url

        In HTTP mode (space_url starts with http:// or https://):
            - Builds the FastAPI application
            - Starts the uvicorn server on host:port

        In tunneling mode (space_url starts with tunneling:):
            - Starts MQ consumer loop
            - Processes requests via message queue
            - host and port parameters are ignored

        Args:
            host: Host to bind to (default: "0.0.0.0"). Ignored in tunneling mode.
            port: Port to bind to (default: 8000). Ignored in tunneling mode.
        """
        if not self._skip_sync:
            await self._sync_endpoints()
        else:
            self._logger.info("Skipping endpoint sync (skip_sync=True)")

        # Start heartbeat after successful sync/auth
        await self._start_heartbeat()

        try:
            if self._is_tunneling:
                self._logger.info("Starting in tunneling mode")
                await self._run_tunnel_mode()
            else:
                self._logger.info("Starting HTTP server on %s:%d", host, port)
                await self._run_http_mode(host, port)
        finally:
            # Stop heartbeat on shutdown
            await self._stop_heartbeat()

    async def _run_http_mode(self, host: str, port: int) -> None:
        """Run the HTTP server (standard mode).

        Args:
            host: Host to bind to.
            port: Port to bind to.
        """
        app = self._build_fastapi_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    async def _run_tunnel_mode(self) -> None:
        """Run in tunneling mode - consume messages from MQ."""
        self._logger.info("Tunnel mode: Starting message consumer")

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self._initiate_tunnel_shutdown()))

        # Run startup hooks
        self._logger.debug("Running %d startup hooks...", len(self._on_startup))
        for hook in self._on_startup:
            try:
                self._logger.debug("Running startup hook: %s", hook.__name__)
                await hook()
            except Exception as e:
                self._logger.error("Startup hook '%s' failed: %s", hook.__name__, e)
                raise

        try:
            await self._tunnel_consumer_loop()
        except asyncio.CancelledError:
            self._logger.info("Tunnel consumer cancelled")
        finally:
            # Run shutdown hooks
            self._logger.debug("Running %d shutdown hooks...", len(self._on_shutdown))
            for hook in self._on_shutdown:
                try:
                    self._logger.debug("Running shutdown hook: %s", hook.__name__)
                    await hook()
                except Exception as e:
                    self._logger.error("Shutdown hook '%s' failed: %s", hook.__name__, e)

    async def _initiate_tunnel_shutdown(self) -> None:
        """Signal the tunnel consumer to shut down gracefully."""
        self._logger.info("Initiating tunnel shutdown...")
        self._tunnel_shutdown = True

        # Cancel any pending response futures
        for correlation_id, future in self._pending_responses.items():
            if not future.done():
                self._logger.debug("Cancelling pending response for %s", correlation_id[:8])
                future.cancel()

    async def _tunnel_consumer_loop(self) -> None:
        """Main loop: consume and process messages from the queue."""
        self._logger.info("Tunnel consumer loop started")

        while not self._tunnel_shutdown:
            try:
                if self._client is None:
                    self._logger.error("Client not authenticated, cannot consume messages")
                    await asyncio.sleep(self._tunnel_poll_interval)
                    continue

                # Consume messages from our queue
                response = await asyncio.to_thread(
                    self._client.mq.consume, limit=self._tunnel_batch_size  # type: ignore[attr-defined]
                )

                if response.messages:
                    self._logger.debug("Consumed %d messages", len(response.messages))

                    # Process each message concurrently
                    tasks = [self._process_tunnel_message(msg) for msg in response.messages]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Log any errors
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            self._logger.error(
                                "Error processing message %d: %s", i, result, exc_info=result
                            )
                else:
                    # No messages, wait before polling again
                    await asyncio.sleep(self._tunnel_poll_interval)

            except Exception as e:
                self._logger.error("Error in tunnel consumer loop: %s", e)
                await asyncio.sleep(self._tunnel_poll_interval)

        self._logger.info("Tunnel consumer loop stopped")

    async def _process_tunnel_message(self, msg: Any) -> None:
        """Process a single message from the queue.

        Args:
            msg: Message object with id, from_username, from_user_id, message, queued_at
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Parse the message payload
            try:
                data = json.loads(msg.message)
            except json.JSONDecodeError:
                self._logger.warning("Non-JSON message from %s, ignoring", msg.from_username)
                return

            # Check protocol version
            protocol = data.get("protocol", "")
            if not protocol.startswith("syfthub-tunnel/"):
                self._logger.debug("Unknown protocol '%s' from %s", protocol, msg.from_username)
                return

            # Route by message type
            msg_type = data.get("type")

            if msg_type == "endpoint_request":
                await self._handle_tunnel_request(data, msg, start_time)
            elif msg_type == "endpoint_response":
                await self._handle_tunnel_response(data, msg)
            else:
                self._logger.warning("Unknown message type '%s' from %s", msg_type, msg.from_username)

        except Exception as e:
            self._logger.exception("Error processing message %s: %s", msg.id, e)
            # Try to send error response if we have enough context
            if "data" in locals() and isinstance(data, dict) and data.get("correlation_id"):
                try:
                    await self._send_tunnel_error(
                        reply_to=data.get("reply_to", msg.from_username),
                        correlation_id=data["correlation_id"],
                        endpoint_slug=data.get("endpoint", {}).get("slug", "unknown"),
                        code=TunnelErrorCode.PROCESSING_ERROR,
                        message=str(e),
                    )
                except Exception as send_error:
                    self._logger.error("Failed to send error response: %s", send_error)

    async def _handle_tunnel_request(
        self, data: dict[str, Any], msg: Any, start_time: datetime
    ) -> None:
        """Handle an incoming endpoint request via tunnel.

        Args:
            data: Parsed message data.
            msg: Original message object.
            start_time: When processing started.
        """
        # Extract request fields
        correlation_id = data.get("correlation_id")
        reply_to = data.get("reply_to", msg.from_username)
        endpoint_info = data.get("endpoint", {})
        endpoint_slug = endpoint_info.get("slug")
        endpoint_type = endpoint_info.get("type")
        payload = data.get("payload", {})

        self._logger.info(
            "Processing tunnel request: endpoint=%s, correlation_id=%s, from=%s",
            endpoint_slug,
            correlation_id[:8] if correlation_id else "none",
            msg.from_username,
        )

        # Validate required fields
        if not correlation_id or not endpoint_slug:
            self._logger.warning("Invalid request: missing correlation_id or endpoint_slug")
            return

        # Find the endpoint
        endpoint = self._find_endpoint_by_slug(endpoint_slug)

        if not endpoint:
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.ENDPOINT_NOT_FOUND,
                message=f"No endpoint registered with slug '{endpoint_slug}'",
            )
            return

        # Verify endpoint type matches
        if endpoint["type"].value != endpoint_type:
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.ENDPOINT_TYPE_MISMATCH,
                message=f"Endpoint '{endpoint_slug}' is {endpoint['type'].value}, not {endpoint_type}",
            )
            return

        # Invoke the handler
        try:
            if endpoint["type"] == EndpointType.DATA_SOURCE:
                result = await self._invoke_datasource_handler(endpoint, payload)
            else:
                result = await self._invoke_model_handler(endpoint, payload)

            # Send success response
            await self._send_tunnel_success(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                payload=result,
                start_time=start_time,
            )

            self._logger.info(
                "Tunnel request completed: endpoint=%s, correlation_id=%s",
                endpoint_slug,
                correlation_id[:8],
            )

        except Exception as e:
            self._logger.exception("Handler error for %s: %s", endpoint_slug, e)
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.HANDLER_ERROR,
                message=str(e),
            )

    async def _handle_tunnel_response(self, data: dict[str, Any], msg: Any) -> None:
        """Handle an incoming response to our outgoing request.

        This is used when this SDK acts as a requester to another tunneling Space.

        Args:
            data: Parsed message data.
            msg: Original message object.
        """
        correlation_id = data.get("correlation_id")

        if not correlation_id:
            self._logger.warning("Received response without correlation_id from %s", msg.from_username)
            return

        # Check if we're waiting for this response
        future = self._pending_responses.get(correlation_id)

        if future and not future.done():
            # Resolve the waiting future
            future.set_result(data)
            self._logger.debug("Resolved response for correlation_id=%s", correlation_id[:8])
        else:
            # Unexpected response - might be late/duplicate
            self._logger.warning(
                "Unexpected response for correlation_id=%s from %s",
                correlation_id[:8],
                msg.from_username,
            )

    async def _send_tunnel_success(
        self,
        reply_to: str,
        correlation_id: str,
        endpoint_slug: str,
        payload: dict[str, Any],
        start_time: datetime,
    ) -> None:
        """Send a success response via tunnel.

        Args:
            reply_to: Username to send response to.
            correlation_id: Request correlation ID.
            endpoint_slug: Endpoint that handled the request.
            payload: Response payload.
            start_time: When request processing started.
        """
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        response = TunnelResponse(
            correlation_id=correlation_id,
            status="success",
            endpoint_slug=endpoint_slug,
            payload=payload,
            error=None,
            timing=TunnelTiming(
                received_at=start_time.isoformat(),
                processed_at=end_time.isoformat(),
                duration_ms=duration_ms,
            ),
        )

        await self._publish_tunnel_message(reply_to, response.model_dump())

    async def _send_tunnel_error(
        self,
        reply_to: str,
        correlation_id: str,
        endpoint_slug: str,
        code: TunnelErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Send an error response via tunnel.

        Args:
            reply_to: Username to send response to.
            correlation_id: Request correlation ID.
            endpoint_slug: Endpoint that was requested.
            code: Error code.
            message: Error message.
            details: Optional additional error details.
        """
        response = TunnelResponse(
            correlation_id=correlation_id,
            status="error",
            endpoint_slug=endpoint_slug,
            payload=None,
            error=TunnelError(
                code=code.value,
                message=message,
                details=details,
            ),
        )

        await self._publish_tunnel_message(reply_to, response.model_dump())
        self._logger.warning(
            "Sent error response: endpoint=%s, code=%s, message=%s",
            endpoint_slug,
            code.value,
            message,
        )

    async def _publish_tunnel_message(self, target_username: str, message: dict[str, Any]) -> None:
        """Publish a message to another user's queue.

        Args:
            target_username: Username to send message to.
            message: Message payload to send.
        """
        if self._client is None:
            self._logger.error("Cannot publish: client not authenticated")
            raise RuntimeError("Client not authenticated")

        try:
            await asyncio.to_thread(
                self._client.mq.publish,  # type: ignore[attr-defined]
                target_username=target_username,
                message=json.dumps(message),
            )
            self._logger.debug("Published tunnel message to %s", target_username)
        except Exception as e:
            self._logger.error("Failed to publish tunnel message to %s: %s", target_username, e)
            raise
