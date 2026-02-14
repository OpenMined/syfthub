"""
SyftHub API Framework - Core Application Module

Provides the SyftAPI class for building SyftAI Spaces with a FastAPI-like interface.
"""

# Standard library
import asyncio
import inspect
import os
import re
import signal
import typing
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, TYPE_CHECKING

# Third-party
import uvicorn
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from policy_manager.context import RequestContext
from policy_manager.policies.base import Policy
from policy_manager.result import PolicyResult
from policy_manager.stores.base import Store
from policy_manager.stores.memory import InMemoryStore
from syfthub_sdk import SyftHubClient, User, Visibility

# Local
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    EndpointRegistrationError,
    PolicyDeniedError,
    SyncError,
)
from .heartbeat import HeartbeatManager
from .logging import setup_logging
from .config import TUNNELING_PREFIX, derive_nats_ws_url
from .nats_transport import NATSSpaceTransport
from .schemas import (
    UserContext,
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

if TYPE_CHECKING:
    from .file_mode import FileBasedEndpointProvider

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
        api_key: str | None = None,
        space_url: str | None = None,
        log_level: str = "INFO",
        heartbeat_enabled: bool | None = None,
        heartbeat_ttl_seconds: int | None = None,
        heartbeat_interval_multiplier: float | None = None,
        store: Store | None = None,
        # File-based endpoint mode parameters
        endpoints_path: str | Path | None = None,
        watch_enabled: bool = True,
        watch_debounce_seconds: float = 1.0,
    ) -> None:
        """
        Initialize the SyftAPI application.

        Args:
            syfthub_url: URL of the SyftHub backend. Falls back to SYFTHUB_URL env var.
            api_key: SyftHub API token (PAT) for authentication.
                Falls back to SYFTHUB_API_KEY env var.
            space_url: Public URL of this SyftAI Space. Falls back to SPACE_URL env var.
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                Falls back to LOG_LEVEL env var. Defaults to INFO.
            heartbeat_enabled: Enable periodic heartbeat to SyftHub.
                Falls back to HEARTBEAT_ENABLED env var. Defaults to True.
            heartbeat_ttl_seconds: Heartbeat TTL in seconds (1-3600, server caps at 600).
                Falls back to HEARTBEAT_TTL_SECONDS env var. Defaults to 300.
            heartbeat_interval_multiplier: Send heartbeat at TTL * multiplier.
                Falls back to HEARTBEAT_INTERVAL_MULTIPLIER env var. Defaults to 0.8.
            store: Policy store backend for persisting policy state.
                Defaults to InMemoryStore when policies are used.
            endpoints_path: Path to directory containing file-based endpoints.
                When provided, enables file-based endpoint mode. Each subdirectory
                becomes an endpoint with README.md (config) and runner.py (logic).
                Falls back to ENDPOINTS_PATH env var.
            watch_enabled: Enable file watching for hot-reload of file-based endpoints.
                Falls back to WATCH_ENABLED env var. Defaults to True.
            watch_debounce_seconds: Delay before triggering reload after file changes.
                Falls back to WATCH_DEBOUNCE_SECONDS env var. Defaults to 1.0.

        Raises:
            ConfigurationError: If required configuration is missing.
        """
        # Setup logging
        effective_log_level = log_level or os.environ.get("LOG_LEVEL", "INFO")
        self._logger = setup_logging(level=effective_log_level)

        self.endpoints: list[dict[str, Any]] = []
        self._syfthub_url = syfthub_url or os.environ.get("SYFTHUB_URL")
        self._api_key = api_key or os.environ.get("SYFTHUB_API_KEY")
        self._space_url = space_url or os.environ.get("SPACE_URL")

        if not self._syfthub_url:
            raise ConfigurationError("syfthub_url must be provided or set as SYFTHUB_URL env var")
        if not self._api_key:
            raise ConfigurationError("api_key must be provided or set as SYFTHUB_API_KEY env var")
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
        self._pending_responses: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._shutdown_event: asyncio.Event | None = None

        # NATS transport (initialized in _run_tunnel_mode)
        self._nats_transport: NATSSpaceTransport | None = None
        self._nats_auth_token: str | None = None  # fetched from hub after login

        # Policy enforcement
        self._store: Store | None = store
        self._global_policies: list[Policy] = []

        # File-based endpoint mode
        endpoints_path_str = endpoints_path or os.environ.get("ENDPOINTS_PATH")
        self._endpoints_path: Path | None = Path(endpoints_path_str) if endpoints_path_str else None

        # Watch configuration (from args or env vars)
        if watch_enabled is not None:
            self._watch_enabled = watch_enabled
        else:
            env_val = os.environ.get("WATCH_ENABLED", "true")
            self._watch_enabled = env_val.lower() in ("true", "1", "yes")

        self._watch_debounce_seconds = watch_debounce_seconds or float(
            os.environ.get("WATCH_DEBOUNCE_SECONDS", "1.0")
        )

        # File-based endpoint provider (initialized lazily in run())
        self._file_provider: "FileBasedEndpointProvider | None" = None

        self._logger.debug(
            "SyftAPI initialized with syfthub_url=%s, space_url=%s, heartbeat_enabled=%s, tunneling=%s, file_mode=%s",
            self._syfthub_url,
            self._space_url,
            self._heartbeat_enabled,
            self._is_tunneling,
            self._endpoints_path is not None,
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

    # ── Policy registration ──────────────────────────────────────────

    def add_policy(self, policy: Policy) -> None:
        """Add a global policy that applies to all endpoints.

        Global policies execute before any per-endpoint policies, in
        the order they are registered.

        Policy ``setup()`` is deferred to :meth:`run` — no async needed here.

        Args:
            policy: A :class:`~policy_manager.policies.base.Policy` instance.

        Example:
            from policy_manager.policies import RateLimitPolicy

            app.add_policy(RateLimitPolicy(max_requests=100, window_seconds=3600))
        """
        self._global_policies.append(policy)

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
        policies: list[Policy] | None = None,
    ) -> None:
        """
        Register an endpoint internally.

        Args:
            endpoint_type: Type of endpoint (DATA_SOURCE or MODEL).
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the endpoint.
            fn: Async function that handles requests.
            policies: Per-endpoint policies (run after global policies).

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
                "policies": list(policies) if policies else [],
            }
        )

    def datasource(
        self,
        slug: str,
        name: str,
        description: str,
        policies: list[Policy] | None = None,
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, list[Document]]]],
        Callable[..., Coroutine[Any, Any, list[Document]]],
    ]:
        """
        Decorator to register a data source endpoint.

        The decorated function should accept a ``query: str`` parameter and return
        a list of Document objects.  Optionally accepts a
        ``ctx: RequestContext`` parameter to access policy metadata.

        Args:
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the data source.
            policies: Per-endpoint policies.  These execute after any global
                policies registered via :meth:`add_policy`.

        Returns:
            Decorator function.

        Example:
            @app.datasource(
                slug="papers",
                name="Papers",
                description="Scientific papers",
                policies=[TokenLimitPolicy(max_input_tokens=500)],
            )
            async def search_papers(query: str, ctx: RequestContext) -> list[Document]:
                return [Document(...), ...]
        """

        def decorator(
            fn: Callable[..., Coroutine[Any, Any, list[Document]]],
        ) -> Callable[..., Coroutine[Any, Any, list[Document]]]:
            self._register_endpoint(
                EndpointType.DATA_SOURCE, slug, name, description, fn, policies
            )

            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> list[Document]:
                return await fn(*args, **kwargs)

            return wrapper

        return decorator

    def model(
        self,
        slug: str,
        name: str,
        description: str,
        policies: list[Policy] | None = None,
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, str]]],
        Callable[..., Coroutine[Any, Any, str]],
    ]:
        """
        Decorator to register a model endpoint.

        The decorated function should accept a ``messages: list[Message]`` parameter
        and return a string response.  Optionally accepts a
        ``ctx: RequestContext`` parameter to access policy metadata.

        Args:
            slug: URL-safe identifier for the endpoint.
            name: Human-readable name.
            description: Description of the model.
            policies: Per-endpoint policies.  These execute after any global
                policies registered via :meth:`add_policy`.

        Returns:
            Decorator function.

        Example:
            @app.model(
                slug="echo",
                name="Echo Model",
                description="Echoes input",
                policies=[TokenLimitPolicy(max_input_tokens=2000)],
            )
            async def echo(messages: list[Message]) -> str:
                return messages[-1].content
        """

        def decorator(
            fn: Callable[..., Coroutine[Any, Any, str]],
        ) -> Callable[..., Coroutine[Any, Any, str]]:
            self._register_endpoint(
                EndpointType.MODEL, slug, name, description, fn, policies
            )

            @wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> str:
                return await fn(*args, **kwargs)

            return wrapper

        return decorator

    # ── Policy setup ───────────────────────────────────────────────────

    async def _setup_policies(self) -> None:
        """Initialize policy stores and build resolved policy chains.

        Called once during :meth:`run` before the server starts.

        For each endpoint the resolved chain is
        ``global_policies + endpoint_policies``.  Each unique policy
        instance has ``setup(store)`` called exactly once.
        """
        has_any = bool(self._global_policies) or any(
            ep.get("policies") for ep in self.endpoints
        )
        if not has_any:
            return

        # Ensure a store exists
        if self._store is None:
            self._store = InMemoryStore()

        # Call setup() on each unique policy instance exactly once
        seen: set[int] = set()
        all_policies: list[Policy] = list(self._global_policies)
        for ep in self.endpoints:
            all_policies.extend(ep.get("policies", []))

        for policy in all_policies:
            pid = id(policy)
            if pid not in seen:
                await policy.setup(self._store)
                seen.add(pid)

        # Build the resolved (flat) policy list per endpoint
        for ep in self.endpoints:
            ep["_resolved_policies"] = list(self._global_policies) + list(
                ep.get("policies", [])
            )

        policy_count = len(seen)
        global_count = len(self._global_policies)
        self._logger.info(
            "Policies initialized: %d unique policies (%d global), store=%s",
            policy_count,
            global_count,
            type(self._store).__name__,
        )

        # Register store cleanup on shutdown (e.g. SQLiteStore.close)
        if hasattr(self._store, "close") and callable(self._store.close):
            store = self._store

            async def _close_store() -> None:
                await store.close()  # type: ignore[union-attr]

            self._on_shutdown.append(_close_store)

    async def _check_pre_exec_policies(
        self,
        policies: list[Policy],
        context: RequestContext,
    ) -> None:
        """Run the pre-execution policy chain.

        Raises:
            PolicyDeniedError: On the first denial or pending result.
        """
        for policy in policies:
            result = await policy.pre_execute(context)
            if not result.allowed:
                raise PolicyDeniedError(result)

    async def _check_post_exec_policies(
        self,
        policies: list[Policy],
        context: RequestContext,
    ) -> None:
        """Run the post-execution policy chain.

        Raises:
            PolicyDeniedError: On the first denial or pending result.
        """
        for policy in policies:
            result = await policy.post_execute(context)
            if not result.allowed:
                raise PolicyDeniedError(result)

    def _serialize_policy(self, policy: Policy) -> dict[str, Any]:
        """
        Serialize a Policy object to the dict format expected by SyftHub backend.

        The backend expects:
        - type: str (policy class name, e.g., "RateLimitPolicy")
        - version: str (default "1.0")
        - enabled: bool (default True)
        - description: str (default "")
        - config: Dict[str, Any] (policy-specific configuration)

        Args:
            policy: A Policy instance from policy_manager.

        Returns:
            Dict matching the backend's Policy schema.
        """
        # Get the policy class name as the type
        policy_type = type(policy).__name__

        # Extract config from policy attributes
        # Exclude private attributes, methods, and non-serializable objects
        config: dict[str, Any] = {}
        # Attributes to exclude from serialization
        exclude_attrs = {"store"}  # Store is set by policy.setup() and isn't serializable
        for key, value in policy.__dict__.items():
            # Skip private attributes (start with _)
            if key.startswith("_"):
                continue
            # Skip explicitly excluded attributes
            if key in exclude_attrs:
                continue
            # Skip non-serializable types
            if callable(value):
                continue
            config[key] = value

        return {
            "type": policy_type,
            "version": "1.0",
            "enabled": True,
            "description": f"{policy_type}: {policy.name}",
            "config": config,
        }

    async def _sync_endpoints(self) -> None:
        """
        Synchronize registered endpoints with the SyftHub backend.

        Raises:
            AuthenticationError: If authentication with SyftHub fails.
            SyncError: If endpoint synchronization fails.
        """
        self._logger.info("Authenticating with SyftHub at %s...", self._syfthub_url)

        # Use API token authentication (no login needed)
        assert self._api_key is not None  # Validated in __init__
        client = SyftHubClient(base_url=self._syfthub_url, api_token=self._api_key)

        try:
            # Verify authentication by fetching current user
            user: User = await asyncio.to_thread(client.auth.me)
            self._logger.info("Successfully authenticated as user: %s", user.username)

            # Update user's domain
            updated_user = await asyncio.to_thread(client.users.update, domain=self._space_url)
            self._logger.info("User domain updated to: %s", updated_user.domain)

            # Store client for heartbeat use
            self._client = client

            # Fetch NATS credentials from hub (only needed in tunneling mode)
            if self._is_tunneling:
                try:
                    nats_creds = await asyncio.to_thread(client.users.get_nats_credentials)
                    self._nats_auth_token = nats_creds.nats_auth_token
                    self._logger.info("Fetched NATS credentials from hub")
                except Exception as e:
                    self._logger.error("Failed to fetch NATS credentials: %s", e)
                    raise AuthenticationError(
                        f"Failed to fetch NATS credentials from hub: {e}", cause=e
                    ) from e

        except AuthenticationError:
            # Re-raise if already wrapped
            raise
        except Exception as e:
            self._logger.error("Authentication failed: %s", e)
            raise AuthenticationError(f"Failed to authenticate with SyftHub: {e}", cause=e) from e

        self._logger.info("Syncing %d endpoints with SyftHub...", len(self.endpoints))
        endpoints_to_sync = []
        for endpoint in self.endpoints:
            # Serialize policies for this endpoint
            policies = endpoint.get("policies", [])
            serialized_policies = [self._serialize_policy(p) for p in policies]

            # Convert version to semver format (e.g., "1.0" -> "1.0.0")
            version = endpoint.get("version", "0.1.0")
            version_parts = version.split(".")
            while len(version_parts) < 3:
                version_parts.append("0")
            semver_version = ".".join(version_parts[:3])

            # Get README body content (from file-based endpoints)
            readme_body = endpoint.get("_readme_body", "")

            endpoints_to_sync.append(
                {
                    "name": endpoint["name"],
                    "slug": endpoint["slug"],
                    "type": endpoint["type"].value,
                    "description": endpoint["description"],
                    "version": semver_version,
                    "readme": readme_body,
                    "visibility": Visibility.PUBLIC.value,
                    "connect": [{"type": "http", "config": {"url": self._space_url}}],
                    "policies": serialized_policies,
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

    async def _verify_satellite_token(self, token: str) -> UserContext:
        """Verify a satellite token via the Hub's /verify endpoint.

        The space authenticates itself to the Hub. The Hub uses the space's
        username as the authorized audience, ensuring only tokens intended
        for this space are accepted.

        Args:
            token: The satellite token string to verify.

        Returns:
            UserContext with the verified user's identity.

        Raises:
            AuthenticationError: If verification fails or the Hub is unreachable.
        """
        if self._client is None:
            raise AuthenticationError(
                "Hub client not available. Cannot verify satellite tokens "
                "before authentication with SyftHub."
            )

        try:
            response = await asyncio.to_thread(
                self._client._http.post,
                "/api/v1/verify",
                json={"token": token},
            )
        except Exception as e:
            raise AuthenticationError(
                f"Failed to reach Hub for token verification: {e}", cause=e
            ) from e

        data = response if isinstance(response, dict) else {}

        if not data.get("valid"):
            error = data.get("error", "verification_failed")
            message = data.get("message", "Satellite token verification failed.")
            raise AuthenticationError(f"Token verification failed: {error} — {message}")

        return UserContext(
            sub=data["sub"],
            email=data["email"],
            username=data["username"],
            role=data["role"],
        )

    @staticmethod
    def _extract_bearer_token(request: Request) -> str:
        """Extract Bearer token from Authorization header.

        Raises:
            AuthenticationError: If the header is missing or malformed.
        """
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            raise AuthenticationError(
                "Missing or invalid Authorization header. "
                "Expected: Authorization: Bearer <satellite_token>"
            )
        token = auth_header[7:].strip()
        if not token:
            raise AuthenticationError("Empty Bearer token in Authorization header.")
        return token

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

    def _build_request_context(
        self,
        endpoint: dict[str, Any],
        payload: dict[str, Any],
        user: UserContext,
        *,
        input_dict: dict[str, Any],
    ) -> RequestContext:
        """Build a :class:`RequestContext` for policy evaluation.

        Args:
            endpoint: The registered endpoint dict.
            payload: Raw request payload.
            user: Verified user identity.
            input_dict: Pre-built input dict for the context.

        Returns:
            A new :class:`RequestContext` ready for the policy chain.
        """
        metadata: dict[str, Any] = {
            "endpoint_slug": endpoint["slug"],
            "endpoint_type": endpoint["type"].value,
            "user_email": user.email,
            "user_role": user.role,
        }
        if payload.get("transaction_token"):
            metadata["transaction_token"] = payload["transaction_token"]

        # Include endpoint-specific environment variables (from file-based endpoints)
        if endpoint.get("_env"):
            metadata["env"] = endpoint["_env"]

        return RequestContext(
            user_id=user.username,
            input=input_dict,
            metadata=metadata,
        )

    async def _invoke_datasource_handler(
        self,
        endpoint: dict[str, Any],
        payload: dict[str, Any],
        user: UserContext,
    ) -> dict[str, Any]:
        """Invoke a DATA_SOURCE endpoint handler.

        This method is used by both HTTP handlers and tunnel mode.

        Args:
            endpoint: The registered endpoint dict.
            payload: Request payload with 'messages' (query), 'limit', etc.
            user: Verified user identity, injected if the handler declares it.

        Returns:
            Response dict with 'references' containing documents.

        Raises:
            PolicyDeniedError: If a policy denies the request.
        """
        fn = endpoint["fn"]
        query = payload.get("messages", "")
        resolved_policies: list[Policy] = endpoint.get("_resolved_policies", [])

        # ── Build policy context ────────────────────────────────
        policy_context = self._build_request_context(
            endpoint,
            payload,
            user,
            input_dict={
                "query": query,
                "limit": payload.get("limit"),
                "similarity_threshold": payload.get("similarity_threshold"),
            },
        )

        # ── Pre-execution policy check ──────────────────────────
        if resolved_policies:
            await self._check_pre_exec_policies(resolved_policies, policy_context)

        # ── Build handler kwargs ────────────────────────────────
        kwargs: dict[str, Any] = {"query": query}

        # Inject UserContext / RequestContext if handler declares them.
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        for param_name, hint in hints.items():
            if hint is UserContext:
                kwargs[param_name] = user
            elif hint is RequestContext:
                kwargs[param_name] = policy_context

        # Call user's async function
        documents = await fn(**kwargs)

        # ── Post-execution policy check ─────────────────────────
        if resolved_policies:
            doc_contents = " ".join(
                doc.content if hasattr(doc, "content") else str(doc)
                for doc in documents
            )
            policy_context.output = {
                "response": doc_contents,
                "documents": [
                    doc.model_dump() if hasattr(doc, "model_dump") else doc
                    for doc in documents
                ],
            }
            await self._check_post_exec_policies(resolved_policies, policy_context)

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
        self,
        endpoint: dict[str, Any],
        payload: dict[str, Any],
        user: UserContext,
    ) -> dict[str, Any]:
        """Invoke a MODEL endpoint handler.

        This method is used by both HTTP handlers and tunnel mode.

        Args:
            endpoint: The registered endpoint dict.
            payload: Request payload with 'messages' list.
            user: Verified user identity, injected if the handler declares it.

        Returns:
            Response dict with 'summary' containing model response.

        Raises:
            PolicyDeniedError: If a policy denies the request.
        """
        fn = endpoint["fn"]
        raw_messages = payload.get("messages", [])
        resolved_policies: list[Policy] = endpoint.get("_resolved_policies", [])

        # Convert to Message objects if they're dicts
        messages = [Message(**m) if isinstance(m, dict) else m for m in raw_messages]

        # Derive a "query" string for policies (last user message)
        last_user_content = ""
        for msg in reversed(messages):
            role = msg.role if hasattr(msg, "role") else msg.get("role", "")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            if role == "user":
                last_user_content = content
                break

        # ── Build policy context ────────────────────────────────
        policy_context = self._build_request_context(
            endpoint,
            payload,
            user,
            input_dict={
                "query": last_user_content,
                "messages": [
                    m.model_dump() if hasattr(m, "model_dump") else m for m in messages
                ],
                "max_tokens": payload.get("max_tokens"),
                "temperature": payload.get("temperature"),
            },
        )

        # ── Pre-execution policy check ──────────────────────────
        if resolved_policies:
            await self._check_pre_exec_policies(resolved_policies, policy_context)

        # ── Build handler kwargs ────────────────────────────────
        kwargs: dict[str, Any] = {"messages": messages}

        # Inject UserContext / RequestContext if handler declares them.
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        for param_name, hint in hints.items():
            if hint is UserContext:
                kwargs[param_name] = user
            elif hint is RequestContext:
                kwargs[param_name] = policy_context

        # Call handler - use executor if available (for subprocess/container mode)
        executor = endpoint.get("_executor")
        if executor is not None and executor.is_started:
            # Use the executor for isolated execution with venv dependencies
            self._logger.info(
                "Invoking endpoint '%s' via %s executor",
                endpoint["slug"],
                type(executor).__name__,
            )
            result = await executor.execute(messages, policy_context)
            if result.success:
                response_content = result.result
            else:
                raise RuntimeError(result.error or "Executor execution failed")
        else:
            # Direct call (in_process mode or no executor)
            self._logger.info(
                "Invoking endpoint '%s' directly (in_process mode)",
                endpoint["slug"],
            )
            response_content = await fn(**kwargs)

        # ── Post-execution policy check ─────────────────────────
        if resolved_policies:
            policy_context.output = {"response": response_content}
            await self._check_post_exec_policies(resolved_policies, policy_context)

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

        # Add exception handler for AuthenticationError -> HTTP 401
        @app.exception_handler(AuthenticationError)
        async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
            return JSONResponse(status_code=401, content={"detail": str(exc)})

        # Add exception handler for PolicyDeniedError -> HTTP 403
        @app.exception_handler(PolicyDeniedError)
        async def policy_denied_handler(
            request: Request, exc: PolicyDeniedError
        ) -> JSONResponse:
            result = exc.result
            return JSONResponse(
                status_code=403,
                content={
                    "detail": str(exc),
                    "policy": result.policy_name,
                    "reason": result.reason,
                    "pending": result.pending,
                    "metadata": result.metadata,
                },
            )

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

    def _create_datasource_handler(self, endpoint: dict[str, Any]) -> Any:
        """Create a request handler for a data source endpoint."""

        async def handler(
            request_body: DataSourceQueryRequest,
            request: Request,
        ) -> DataSourceQueryResponse:
            token = self._extract_bearer_token(request)
            user = await self._verify_satellite_token(token)

            payload = {
                "messages": request_body.messages,
                "limit": request_body.limit,
                "similarity_threshold": request_body.similarity_threshold,
                "include_metadata": request_body.include_metadata,
                "transaction_token": request_body.transaction_token,
            }
            result = await self._invoke_datasource_handler(endpoint, payload, user=user)
            return DataSourceQueryResponse(**result)

        return handler

    def _create_model_handler(self, endpoint: dict[str, Any]) -> Any:
        """Create a request handler for a model endpoint."""

        async def handler(
            request_body: ModelQueryRequest,
            request: Request,
        ) -> ModelQueryResponse:
            token = self._extract_bearer_token(request)
            user = await self._verify_satellite_token(token)

            payload = {
                "messages": [m.model_dump() for m in request_body.messages],
                "max_tokens": request_body.max_tokens,
                "temperature": request_body.temperature,
                "stream": request_body.stream,
                "stop_sequences": request_body.stop_sequences,
                "transaction_token": request_body.transaction_token,
            }
            result = await self._invoke_model_handler(endpoint, payload, user=user)
            return ModelQueryResponse(**result)

        return handler

    async def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Start the SyftAI Space server.

        This method:
        1. Loads file-based endpoints (if endpoints_path is configured)
        2. Synchronizes endpoints with the SyftHub backend (unless _skip_sync is True)
        3. Starts file watching for hot-reload (if enabled)
        4. Starts the heartbeat manager (if enabled)
        5. Starts either HTTP server or tunnel consumer based on space_url

        In HTTP mode (space_url starts with http:// or https://):
            - Builds the FastAPI application
            - Starts the uvicorn server on host:port

        In tunneling mode (space_url starts with tunneling:):
            - Connects to NATS via WebSocket
            - Processes requests via pub/sub
            - host and port parameters are ignored

        Args:
            host: Host to bind to (default: "0.0.0.0"). Ignored in tunneling mode.
            port: Port to bind to (default: 8000). Ignored in tunneling mode.
        """
        # Load file-based endpoints if configured
        if self._endpoints_path is not None:
            await self._load_file_based_endpoints()

        if not self._skip_sync:
            await self._sync_endpoints()
        else:
            self._logger.info("Skipping endpoint sync (skip_sync=True)")

        # Initialize policy chains (before heartbeat/server start)
        await self._setup_policies()

        # Start file watching for hot-reload
        if self._file_provider is not None and self._watch_enabled:
            self._file_provider.on_change = self._handle_endpoint_reload
            await self._file_provider.start_watching()
            self._logger.info("File watching enabled for hot-reload")

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
            # Stop file watching
            if self._file_provider is not None:
                await self._file_provider.stop_watching()

            # Stop heartbeat on shutdown
            await self._stop_heartbeat()

    async def _load_file_based_endpoints(self) -> None:
        """
        Load endpoints from the configured endpoints_path.

        This method initializes the FileBasedEndpointProvider and loads
        all endpoints from the directory structure.
        """
        if self._endpoints_path is None:
            return

        self._logger.info("Loading file-based endpoints from %s", self._endpoints_path)

        # Import here to avoid circular imports
        from .file_mode import FileBasedEndpointProvider

        self._file_provider = FileBasedEndpointProvider(
            path=self._endpoints_path,
            watch_enabled=self._watch_enabled,
            debounce_seconds=self._watch_debounce_seconds,
        )

        file_endpoints = await self._file_provider.load_all()
        self.endpoints.extend(file_endpoints)

        self._logger.info(
            "Loaded %d file-based endpoints (total: %d)",
            len(file_endpoints),
            len(self.endpoints),
        )

    async def _handle_endpoint_reload(self, new_file_endpoints: list[dict[str, Any]]) -> None:
        """
        Handle hot-reload of file-based endpoints.

        Called by FileBasedEndpointProvider when files change.
        Performs atomic swap of file-based endpoints while preserving
        decorator-registered endpoints.

        Args:
            new_file_endpoints: Updated list of file-based endpoints.
        """
        # Separate decorator-based endpoints (no _file_mode marker)
        decorator_endpoints = [
            ep for ep in self.endpoints
            if not ep.get("_file_mode")
        ]

        # Combine with new file-based endpoints
        self.endpoints = decorator_endpoints + new_file_endpoints

        self._logger.info(
            "Hot-reloaded endpoints: %d decorator + %d file-based = %d total",
            len(decorator_endpoints),
            len(new_file_endpoints),
            len(self.endpoints),
        )

        # Re-setup policies for new endpoints
        await self._setup_policies()

        # Re-sync with SyftHub if client is authenticated
        if not self._skip_sync and self._client is not None:
            try:
                await self._sync_endpoints()
            except Exception as e:
                self._logger.error("Failed to re-sync endpoints after hot-reload: %s", e)
                # Don't raise - endpoints are still updated locally

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
        """Run in tunneling mode - consume messages via NATS pub/sub."""
        self._logger.info("Tunnel mode: Starting NATS consumer")
        self._shutdown_event = asyncio.Event()

        # Set up signal handlers for graceful shutdown (only works in main thread)
        import threading

        if threading.current_thread() is threading.main_thread():
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self._initiate_tunnel_shutdown()))
        else:
            self._logger.debug("Running in non-main thread, signal handlers not registered")

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
            # Start NATS transport (sole transport for tunneling)
            await self._start_nats_consumer()

            # Block until shutdown is signalled
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            self._logger.info("Tunnel consumer cancelled")
        finally:
            # Stop NATS transport
            if self._nats_transport is not None:
                await self._nats_transport.close()
                self._nats_transport = None

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

        # Cancel any pending response futures
        for correlation_id, future in self._pending_responses.items():
            if not future.done():
                self._logger.debug("Cancelling pending response for %s", correlation_id[:8])
                future.cancel()

        # Signal the shutdown event to unblock _run_tunnel_mode
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    # =========================================================================
    # NATS Transport Methods
    # =========================================================================

    def _get_tunnel_username(self) -> str:
        """Extract the tunnel username from the space URL."""
        assert self._space_url is not None
        return self._space_url[len(TUNNELING_PREFIX):]

    async def _start_nats_consumer(self) -> None:
        """Start the NATS transport for receiving tunnel requests."""
        tunnel_username = self._get_tunnel_username()
        assert self._syfthub_url is not None
        assert self._nats_auth_token is not None

        nats_url = derive_nats_ws_url(self._syfthub_url)
        self._logger.info(
            "Starting NATS consumer for %s at %s",
            tunnel_username,
            nats_url,
        )

        self._nats_transport = NATSSpaceTransport(
            username=tunnel_username,
            nats_url=nats_url,
            nats_auth_token=self._nats_auth_token,
        )

        await self._nats_transport.connect()
        await self._nats_transport.subscribe(self._handle_tunnel_message)
        self._logger.info("NATS consumer started, listening on %s", self._nats_transport.subject)

    async def _handle_tunnel_message(self, data: dict[str, Any], subject: str) -> None:
        """Handle an incoming tunnel message from NATS.

        Args:
            data: Parsed JSON message data.
            subject: NATS subject the message was received on.
        """
        start_time = datetime.now(timezone.utc)

        # Check protocol version
        protocol = data.get("protocol", "")
        if not protocol.startswith("syfthub-tunnel/"):
            self._logger.debug("Unknown protocol '%s' on subject %s", protocol, subject)
            return

        msg_type = data.get("type")

        if msg_type == "endpoint_request":
            await self._handle_tunnel_request(data, start_time)
        elif msg_type == "endpoint_response":
            # Handle response (for peer-to-peer scenarios)
            correlation_id = data.get("correlation_id")
            if correlation_id:
                future = self._pending_responses.get(correlation_id)
                if future and not future.done():
                    future.set_result(data)
        else:
            self._logger.warning("Unknown tunnel message type: %s", msg_type)

    async def _handle_tunnel_request(
        self, data: dict[str, Any], start_time: datetime
    ) -> None:
        """Handle a tunnel request received via NATS.

        Args:
            data: Parsed TunnelRequest message.
            start_time: When processing started.
        """
        correlation_id = data.get("correlation_id")
        reply_to = data.get("reply_to")
        endpoint_info = data.get("endpoint", {})
        endpoint_slug = endpoint_info.get("slug")
        endpoint_type = endpoint_info.get("type")
        payload = data.get("payload", {})

        self._logger.info(
            "Tunnel request: endpoint=%s, correlation_id=%s, reply_to=%s",
            endpoint_slug,
            correlation_id[:8] if correlation_id else "none",
            reply_to,
        )

        if not correlation_id or not endpoint_slug or not reply_to:
            self._logger.warning("Invalid tunnel request: missing required fields")
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

        # Verify endpoint type
        if endpoint["type"].value != endpoint_type:
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.ENDPOINT_TYPE_MISMATCH,
                message=f"Endpoint '{endpoint_slug}' is {endpoint['type'].value}, not {endpoint_type}",
            )
            return

        # Auth check — all endpoints require satellite token
        satellite_token = data.get("satellite_token")
        if not satellite_token:
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.AUTH_FAILED,
                message="Satellite token required.",
            )
            return
        try:
            user = await self._verify_satellite_token(satellite_token)
        except AuthenticationError as e:
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.AUTH_FAILED,
                message=str(e),
            )
            return

        # Invoke the handler
        try:
            if endpoint["type"] == EndpointType.DATA_SOURCE:
                result = await self._invoke_datasource_handler(endpoint, payload, user=user)
            else:
                result = await self._invoke_model_handler(endpoint, payload, user=user)

            # Send success response via NATS
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            response = TunnelResponse(
                correlation_id=correlation_id,
                status="success",
                endpoint_slug=endpoint_slug,
                payload=result,
                error=None,
                timing=TunnelTiming(
                    received_at=start_time.isoformat(),
                    processed_at=end_time.isoformat(),
                    duration_ms=duration_ms,
                ),
            )

            if self._nats_transport:
                await self._nats_transport.publish_response(
                    reply_to, response.model_dump()
                )

            self._logger.info(
                "Tunnel request completed: endpoint=%s, correlation_id=%s, %dms",
                endpoint_slug,
                correlation_id[:8],
                duration_ms,
            )

        except PolicyDeniedError as e:
            self._logger.warning(
                "Policy denied for %s: %s", endpoint_slug, e.result.reason,
            )
            await self._send_tunnel_error(
                reply_to=reply_to,
                correlation_id=correlation_id,
                endpoint_slug=endpoint_slug,
                code=TunnelErrorCode.POLICY_DENIED,
                message=str(e),
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

    async def _send_tunnel_error(
        self,
        reply_to: str,
        correlation_id: str,
        endpoint_slug: str,
        code: TunnelErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Send an error response via NATS.

        Args:
            reply_to: Peer channel to send response to.
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

        if self._nats_transport:
            await self._nats_transport.publish_response(reply_to, response.model_dump())

        self._logger.warning(
            "Sent tunnel error response: endpoint=%s, code=%s, message=%s",
            endpoint_slug,
            code.value,
            message,
        )
