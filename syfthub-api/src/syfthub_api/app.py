"""
SyftHub API Framework - Core Application Module

Provides the SyftAPI class for building SyftAI Spaces with a FastAPI-like interface.
"""

# Standard library
import asyncio
import inspect
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
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
from .schemas import (
    DataSourceQueryRequest,
    DataSourceQueryResponse,
    Document,
    EndpointType,
    ModelQueryRequest,
    ModelQueryResponse,
    ModelSummary,
    References,
    ResponseMessage,
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

        self._logger.debug(
            "SyftAPI initialized with syfthub_url=%s, space_url=%s, heartbeat_enabled=%s",
            self._syfthub_url,
            self._space_url,
            self._heartbeat_enabled,
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
                ds_handler = self._create_datasource_handler(endpoint["fn"])
                router.add_api_route(
                    f"/{endpoint['slug']}/query",
                    ds_handler,
                    methods=["POST"],
                    response_model=DataSourceQueryResponse,
                )
            elif endpoint["type"] == EndpointType.MODEL:
                model_handler = self._create_model_handler(endpoint["fn"], endpoint["slug"])
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
        self, fn: Callable[..., Coroutine[Any, Any, list[Document]]]
    ) -> Callable[[DataSourceQueryRequest], Coroutine[Any, Any, DataSourceQueryResponse]]:
        """Create a request handler for a data source endpoint."""

        async def handler(request: DataSourceQueryRequest) -> DataSourceQueryResponse:
            docs = await fn(query=request.messages)
            return DataSourceQueryResponse(references=References(documents=docs))

        return handler

    def _create_model_handler(
        self, fn: Callable[..., Coroutine[Any, Any, str]], slug: str
    ) -> Callable[[ModelQueryRequest], Coroutine[Any, Any, ModelQueryResponse]]:
        """Create a request handler for a model endpoint."""

        async def handler(request: ModelQueryRequest) -> ModelQueryResponse:
            response_content = await fn(messages=request.messages)

            # Generate unique response ID (OpenAI-style format)
            response_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

            return ModelQueryResponse(
                summary=ModelSummary(
                    id=response_id,
                    model=slug,
                    message=ResponseMessage(content=response_content),
                    finish_reason="stop",
                    usage=None,
                )
            )

        return handler

    async def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Start the SyftAI Space server.

        This method:
        1. Synchronizes endpoints with the SyftHub backend (unless _skip_sync is True)
        2. Starts the heartbeat manager (if enabled)
        3. Builds the FastAPI application
        4. Starts the uvicorn server
        5. Stops the heartbeat manager on shutdown

        Args:
            host: Host to bind to (default: "0.0.0.0").
            port: Port to bind to (default: 8000).
        """
        if not self._skip_sync:
            await self._sync_endpoints()
        else:
            self._logger.info("Skipping endpoint sync (skip_sync=True)")

        # Start heartbeat after successful sync/auth
        await self._start_heartbeat()

        try:
            app = self._build_fastapi_app()

            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        finally:
            # Stop heartbeat on shutdown
            await self._stop_heartbeat()
