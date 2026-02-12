"""
File-based endpoint provider for SyftHub API.

This module provides the FileBasedEndpointProvider that orchestrates
loading endpoints from a folder structure with hot-reload support.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .executors import EndpointExecutor, ExecutorFactory, get_executor_factory
from .loader import EndpointLoader, EndpointLoadError
from .policy_loader import PolicyFactory
from .watcher import FileSystemWatcher

logger = logging.getLogger(__name__)


class FileBasedEndpointProvider:
    """
    Orchestrates file-based endpoint loading and hot-reloading.

    This provider:
    1. Scans a directory for endpoint folders on startup
    2. Loads endpoints from README.md + runner.py + policy/
    3. Optionally watches for changes and hot-reloads endpoints

    Example usage:
        provider = FileBasedEndpointProvider(
            path=Path("/endpoints"),
            watch_enabled=True,
        )
        provider.on_change = my_reload_callback

        endpoints = await provider.load_all()
        await provider.start_watching()

        # ... later
        await provider.stop_watching()
    """

    def __init__(
        self,
        path: Path | str,
        watch_enabled: bool = True,
        debounce_seconds: float = 1.0,
        ignore_patterns: list[str] | None = None,
        policy_factory: PolicyFactory | None = None,
        executor_factory: ExecutorFactory | None = None,
    ) -> None:
        """
        Initialize the file-based endpoint provider.

        Args:
            path: Root directory containing endpoint folders.
            watch_enabled: Whether to enable file watching for hot-reload.
            debounce_seconds: Delay before triggering reload after changes.
            ignore_patterns: Glob patterns for files/folders to ignore.
            policy_factory: Optional custom PolicyFactory for loading policies.
            executor_factory: Optional custom ExecutorFactory for creating executors.
        """
        self._path = Path(path).resolve()
        self._watch_enabled = watch_enabled
        self._debounce_seconds = debounce_seconds
        self._ignore_patterns = ignore_patterns

        self._loader = EndpointLoader(policy_factory=policy_factory)
        self._executor_factory = executor_factory or get_executor_factory()
        self._watcher: FileSystemWatcher | None = None

        # Current endpoints (thread-safe via asyncio lock)
        self._endpoints: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

        # Executors for each endpoint (keyed by slug)
        self._executors: dict[str, EndpointExecutor] = {}

        # Callback for when endpoints change
        self.on_change: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None

    @property
    def path(self) -> Path:
        """Get the endpoints root path."""
        return self._path

    @property
    def endpoints(self) -> list[dict[str, Any]]:
        """Get current list of loaded endpoints."""
        return list(self._endpoints)

    @property
    def is_watching(self) -> bool:
        """Check if file watching is active."""
        return self._watcher is not None and self._watcher.is_running

    @property
    def executors(self) -> dict[str, EndpointExecutor]:
        """Get current executors (keyed by endpoint slug)."""
        return dict(self._executors)

    def get_executor(self, slug: str) -> EndpointExecutor | None:
        """
        Get the executor for an endpoint.

        Args:
            slug: The endpoint slug.

        Returns:
            EndpointExecutor if found, None otherwise.
        """
        return self._executors.get(slug)

    async def load_all(self) -> list[dict[str, Any]]:
        """
        Load all endpoints from the configured path.

        Scans for subdirectories (excluding those starting with _ or .)
        and attempts to load each as an endpoint.

        Returns:
            List of loaded endpoint dicts compatible with SyftAPI.

        Note:
            Invalid endpoints are logged and skipped, not raised.
            This allows partial loading when some endpoints have errors.
        """
        if not self._path.exists():
            logger.warning("Endpoints path does not exist: %s", self._path)
            return []

        if not self._path.is_dir():
            logger.error("Endpoints path is not a directory: %s", self._path)
            return []

        endpoints: list[dict[str, Any]] = []
        folders = self._get_endpoint_folders()

        logger.info("Scanning %d potential endpoint folders in %s", len(folders), self._path)

        for folder in folders:
            try:
                endpoint = await self._loader.load(folder)
                endpoints.append(endpoint)

                # Create and start executor for this endpoint
                await self._create_and_start_executor(endpoint)

            except EndpointLoadError as e:
                if "is disabled" in str(e):
                    logger.debug("Skipping disabled endpoint: %s", folder.name)
                else:
                    logger.error("Failed to load endpoint from %s: %s", folder.name, e)
            except Exception as e:
                logger.exception("Unexpected error loading endpoint from %s: %s", folder.name, e)

        async with self._lock:
            self._endpoints = endpoints

        logger.info(
            "Loaded %d endpoints from %s (%d folders scanned)",
            len(endpoints),
            self._path,
            len(folders),
        )

        return endpoints

    async def _create_and_start_executor(self, endpoint: dict[str, Any]) -> None:
        """
        Create and start an executor for an endpoint.

        Handles cleanup on failure to prevent resource leaks. If the primary
        executor mode fails, attempts fallback to in_process mode.

        Args:
            endpoint: Endpoint data dictionary.
        """
        slug = endpoint.get("slug", "")
        runtime = endpoint.get("_runtime", {})
        mode = runtime.get("mode", "in_process")
        executor = None

        try:
            # Stop existing executor if present
            if slug in self._executors:
                old_executor = self._executors[slug]
                await old_executor.stop()
                del self._executors[slug]

            # Create new executor
            executor = self._executor_factory.create_from_endpoint(endpoint)

            # Start the executor (may fail for venv creation, pip install, etc.)
            await executor.start()

            # Store it only after successful start
            self._executors[slug] = executor
            endpoint["_executor"] = executor  # Reference for direct access

            logger.info(
                "Created %s executor for endpoint '%s'",
                mode,
                slug,
            )

        except NotImplementedError as e:
            # Container mode not yet implemented - fallback to in_process
            logger.warning(
                "Executor creation failed for '%s': %s. Falling back to in_process.",
                slug,
                e,
            )
            try:
                # Fall back to in_process
                runtime["mode"] = "in_process"
                endpoint["_runtime"] = runtime
                executor = self._executor_factory.create_from_endpoint(endpoint)
                await executor.start()
                self._executors[slug] = executor
                endpoint["_executor"] = executor
            except Exception as fallback_error:
                logger.error(
                    "Fallback executor also failed for '%s': %s",
                    slug,
                    fallback_error,
                )
                # Ensure cleanup if executor was created but start failed
                if executor is not None and executor.is_started:
                    try:
                        await executor.stop()
                    except Exception:
                        pass  # Best effort cleanup

        except Exception as e:
            logger.error(
                "Failed to create/start executor for endpoint '%s': %s",
                slug,
                e,
            )
            # Ensure cleanup if executor was created but start failed
            if executor is not None:
                try:
                    await executor.stop()
                except Exception:
                    pass  # Best effort cleanup

    async def start_watching(self) -> None:
        """
        Start watching for file changes.

        When changes are detected, affected endpoints are reloaded
        and the on_change callback is invoked.
        """
        if not self._watch_enabled:
            logger.debug("File watching is disabled")
            return

        if self._watcher is not None and self._watcher.is_running:
            logger.warning("File watcher is already running")
            return

        self._watcher = FileSystemWatcher(
            path=self._path,
            callback=self._handle_changes,
            debounce_seconds=self._debounce_seconds,
            ignore_patterns=self._ignore_patterns,
        )

        await self._watcher.start()
        logger.info("Started file watching for hot-reload")

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self._watcher is not None:
            await self._watcher.stop()
            self._watcher = None
            logger.info("Stopped file watching")

    async def reload_endpoint(self, folder: Path) -> dict[str, Any] | None:
        """
        Reload a single endpoint from its folder.

        Handles executor lifecycle intelligently:
        - If dependencies changed (pyproject.toml): full restart to rebuild venv
        - If only code changed (runner.py): hot-reload if supported
        - If env changed (.env): full restart to propagate new env vars

        Args:
            folder: Path to the endpoint folder.

        Returns:
            Loaded endpoint dict, or None if loading failed.
        """
        try:
            endpoint = await self._loader.load(folder)
            slug = endpoint["slug"]

            # Handle executor update
            old_executor = self._executors.get(slug)
            if old_executor is not None:
                # Check if dependencies changed (requires full restart for venv rebuild)
                old_req_hash = getattr(old_executor, "requirements_hash", "")
                new_req_hash = endpoint.get("_requirements_hash", "")
                dependencies_changed = old_req_hash != new_req_hash

                # Check if env vars changed (requires restart to propagate)
                old_env = old_executor.env_vars or {}
                new_env = endpoint.get("_env", {})
                env_changed = old_env != new_env

                if dependencies_changed:
                    logger.info(
                        "Dependencies changed for '%s' (hash: %s -> %s), "
                        "performing full restart to rebuild venv",
                        slug,
                        old_req_hash[:8] if old_req_hash else "none",
                        new_req_hash[:8] if new_req_hash else "none",
                    )
                    await old_executor.stop()
                    del self._executors[slug]
                    # Fall through to create new executor

                elif env_changed:
                    logger.info(
                        "Environment variables changed for '%s', "
                        "performing full restart",
                        slug,
                    )
                    await old_executor.stop()
                    del self._executors[slug]
                    # Fall through to create new executor

                elif old_executor.supports_hot_reload():
                    # Only code changed - can hot-reload
                    new_handler = endpoint.get("fn")
                    if new_handler is not None:
                        await old_executor.reload_handler(new_handler)
                        endpoint["_executor"] = old_executor
                        logger.info("Hot-reloaded endpoint: %s", slug)
                        return endpoint

                else:
                    # Doesn't support hot-reload - full restart
                    await old_executor.stop()
                    del self._executors[slug]

            # Create new executor
            await self._create_and_start_executor(endpoint)
            logger.info("Reloaded endpoint: %s", slug)
            return endpoint

        except EndpointLoadError as e:
            if "is disabled" in str(e):
                logger.info("Endpoint disabled: %s", folder.name)
                # Stop executor if endpoint was disabled
                await self._stop_executor_for_folder(folder)
            else:
                logger.error("Failed to reload endpoint %s: %s", folder.name, e)
            return None
        except Exception as e:
            logger.exception("Unexpected error reloading %s: %s", folder.name, e)
            return None

    async def _stop_executor_for_folder(self, folder: Path) -> None:
        """Stop executor for an endpoint folder."""
        source_path = str(folder.absolute())
        for slug, executor in list(self._executors.items()):
            if str(executor.endpoint_path.absolute()) == source_path:
                await executor.stop()
                del self._executors[slug]
                logger.debug("Stopped executor for %s", slug)
                break

    async def _handle_changes(self, folders: set[Path]) -> None:
        """
        Handle file change notifications from watcher.

        Uses narrow lock scope to avoid blocking during I/O-heavy operations
        like endpoint reloading and executor lifecycle management.

        Args:
            folders: Set of endpoint folders that changed.
        """
        logger.info("Processing changes in %d endpoint folder(s)", len(folders))

        # Phase 1: Snapshot current state under lock (fast)
        async with self._lock:
            current_endpoints = list(self._endpoints)

        # Phase 2: Process changes outside lock (slow I/O operations)
        paths_to_remove: set[str] = set()
        reloaded_endpoints: list[dict[str, Any]] = []

        for folder in folders:
            source_path = str(folder.absolute())
            paths_to_remove.add(source_path)

            # Reload if folder still exists
            if folder.exists() and folder.is_dir():
                endpoint = await self.reload_endpoint(folder)
                if endpoint is not None:
                    reloaded_endpoints.append(endpoint)
            else:
                # Folder removed - stop executor
                logger.info("Endpoint folder removed: %s", folder.name)
                await self._stop_executor_for_folder(folder)

        # Phase 3: Apply changes under lock (fast)
        async with self._lock:
            # Remove old versions and add reloaded ones
            new_endpoints = [
                ep for ep in current_endpoints
                if ep.get("_source_path") not in paths_to_remove
            ]
            new_endpoints.extend(reloaded_endpoints)
            self._endpoints = new_endpoints

        # Notify callback (outside lock)
        if self.on_change is not None:
            try:
                await self.on_change(list(self._endpoints))
            except Exception as e:
                logger.exception("Error in on_change callback: %s", e)

    def _get_endpoint_folders(self) -> list[Path]:
        """
        Get list of valid endpoint folders.

        Returns folders that:
        - Are directories
        - Don't start with _ or .
        - Contain README.md
        """
        folders = []

        for item in sorted(self._path.iterdir()):
            if not item.is_dir():
                continue

            # Skip hidden and disabled folders
            if item.name.startswith("_") or item.name.startswith("."):
                continue

            # Check for README.md
            readme = item / "README.md"
            if not readme.exists():
                logger.debug("Skipping %s: no README.md", item.name)
                continue

            folders.append(item)

        return folders

    def get_endpoint_by_slug(self, slug: str) -> dict[str, Any] | None:
        """
        Find an endpoint by its slug.

        Args:
            slug: The endpoint slug to find.

        Returns:
            Endpoint dict if found, None otherwise.
        """
        for endpoint in self._endpoints:
            if endpoint["slug"] == slug:
                return endpoint
        return None

    def get_endpoint_by_path(self, path: Path | str) -> dict[str, Any] | None:
        """
        Find an endpoint by its source path.

        Args:
            path: The source folder path.

        Returns:
            Endpoint dict if found, None otherwise.
        """
        source_path = str(Path(path).absolute())
        for endpoint in self._endpoints:
            if endpoint.get("_source_path") == source_path:
                return endpoint
        return None

    async def cleanup(self) -> None:
        """
        Clean up provider resources.

        Stops all executors, file watching, and unloads all endpoint modules.
        """
        # Stop all executors
        for slug, executor in list(self._executors.items()):
            try:
                await executor.stop()
                logger.debug("Stopped executor for %s", slug)
            except Exception as e:
                logger.error("Error stopping executor for %s: %s", slug, e)

        self._executors.clear()

        # Stop file watching
        await self.stop_watching()

        # Cleanup loader
        self._loader.cleanup()
        self._endpoints.clear()

        logger.info("FileBasedEndpointProvider cleaned up")
