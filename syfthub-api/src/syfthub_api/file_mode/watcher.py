"""
File system watcher for hot-reloading endpoints.

This module provides a FileSystemWatcher that monitors an endpoints
directory for changes and triggers reload callbacks with debouncing.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Thread
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class FileSystemWatcher:
    """
    Watches an endpoints directory for changes with debouncing.

    When files change, the watcher identifies affected endpoint folders
    and triggers a callback after a debounce delay. This prevents
    rapid-fire reloads when multiple files change in quick succession.

    Example usage:
        watcher = FileSystemWatcher(
            path=Path("/endpoints"),
            callback=on_endpoints_changed,
            debounce_seconds=1.0,
        )
        await watcher.start()
        # ... later
        await watcher.stop()
    """

    # Default patterns to ignore
    DEFAULT_IGNORE_PATTERNS = [
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".git",
        ".gitignore",
        ".DS_Store",
        "*.swp",
        "*.swo",
        "*~",
        ".pytest_cache",
        ".mypy_cache",
        "*.egg-info",
        ".venv",  # Virtual environments (for isolated execution)
    ]

    def __init__(
        self,
        path: Path,
        callback: Callable[[set[Path]], Awaitable[None]],
        debounce_seconds: float = 1.0,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        """
        Initialize the file system watcher.

        Args:
            path: Root directory to watch (endpoints path).
            callback: Async function called with set of changed endpoint folders.
            debounce_seconds: Delay before triggering callback after changes.
            ignore_patterns: Glob patterns for files/folders to ignore.
        """
        self._path = path.resolve()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE_PATTERNS

        self._observer: Observer | None = None
        self._event_handler: _DebouncedEventHandler | None = None
        self._running = False

        # For async coordination
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running

    @property
    def path(self) -> Path:
        """Get the watched path."""
        return self._path

    async def start(self) -> None:
        """
        Start watching the directory.

        The watcher runs in a background thread but dispatches
        callbacks to the asyncio event loop.
        """
        if self._running:
            logger.warning("FileSystemWatcher is already running")
            return

        if not self._path.exists():
            raise ValueError(f"Watch path does not exist: {self._path}")

        if not self._path.is_dir():
            raise ValueError(f"Watch path is not a directory: {self._path}")

        self._loop = asyncio.get_running_loop()

        # Create event handler
        self._event_handler = _DebouncedEventHandler(
            root_path=self._path,
            callback=self._dispatch_callback,
            debounce_seconds=self._debounce_seconds,
            ignore_patterns=self._ignore_patterns,
            loop=self._loop,
        )

        # Create and configure observer
        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(self._path),
            recursive=True,
        )

        # Start observer in background thread
        self._observer.start()
        self._running = True

        logger.info(
            "FileSystemWatcher started: path=%s, debounce=%.1fs",
            self._path,
            self._debounce_seconds,
        )

    async def stop(self) -> None:
        """
        Stop watching the directory gracefully.

        Waits for any pending debounced callbacks to complete.
        """
        if not self._running:
            return

        self._running = False

        # Cancel pending debounce timer
        if self._event_handler:
            self._event_handler.cancel_pending()

        # Stop observer
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None

        self._event_handler = None
        self._loop = None

        logger.info("FileSystemWatcher stopped")

    async def _dispatch_callback(self, folders: set[Path]) -> None:
        """
        Dispatch callback to user.

        Args:
            folders: Set of endpoint folders that changed.
        """
        try:
            await self._callback(folders)
        except Exception as e:
            logger.exception("Error in file watcher callback: %s", e)


class _DebouncedEventHandler(FileSystemEventHandler):
    """
    Internal event handler with debouncing logic.

    Collects file system events and dispatches them after a delay,
    coalescing multiple rapid events into a single callback.
    """

    def __init__(
        self,
        root_path: Path,
        callback: Callable[[set[Path]], Awaitable[None]],
        debounce_seconds: float,
        ignore_patterns: list[str],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        super().__init__()
        self._root_path = root_path
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._ignore_patterns = ignore_patterns
        self._loop = loop

        # Pending changes
        self._pending_folders: set[Path] = set()
        self._timer_handle: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle any file system event."""
        # Ignore directory events (we care about files within)
        if event.is_directory and event.event_type not in ("created", "deleted"):
            return

        src_path = Path(event.src_path)

        # Check ignore patterns
        if self._should_ignore(src_path):
            return

        # Find the endpoint folder this file belongs to
        endpoint_folder = self._find_endpoint_folder(src_path)
        if endpoint_folder is None:
            return

        logger.debug(
            "File event: %s %s (endpoint: %s)",
            event.event_type,
            src_path.name,
            endpoint_folder.name,
        )

        # Schedule callback (thread-safe)
        self._loop.call_soon_threadsafe(
            self._schedule_callback, endpoint_folder
        )

    def _should_ignore(self, path: Path) -> bool:
        """Check if path matches any ignore patterns."""
        name = path.name

        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

            # Check parent folders too
            for parent in path.parents:
                if parent == self._root_path:
                    break
                if fnmatch.fnmatch(parent.name, pattern):
                    return True

        return False

    def _find_endpoint_folder(self, path: Path) -> Path | None:
        """
        Find the endpoint folder containing this path.

        Endpoint folders are direct children of the root path.
        Returns None if path is not within an endpoint folder.
        """
        try:
            # Get path relative to root
            rel_path = path.relative_to(self._root_path)
            parts = rel_path.parts

            if not parts:
                return None

            # First part is the endpoint folder name
            endpoint_name = parts[0]

            # Skip hidden/underscore-prefixed folders
            if endpoint_name.startswith("_") or endpoint_name.startswith("."):
                return None

            return self._root_path / endpoint_name

        except ValueError:
            # Path not relative to root
            return None

    def _schedule_callback(self, folder: Path) -> None:
        """Schedule debounced callback (called from event loop thread)."""
        self._pending_folders.add(folder)

        # Cancel existing timer
        if self._timer_handle:
            self._timer_handle.cancel()

        # Schedule new timer
        self._timer_handle = self._loop.call_later(
            self._debounce_seconds,
            self._fire_callback,
        )

    def _fire_callback(self) -> None:
        """Fire the callback with pending folders."""
        if not self._pending_folders:
            return

        folders = self._pending_folders.copy()
        self._pending_folders.clear()
        self._timer_handle = None

        logger.info(
            "Triggering reload for %d endpoint(s): %s",
            len(folders),
            [f.name for f in folders],
        )

        # Create task to run async callback
        asyncio.create_task(self._callback(folders))

    def cancel_pending(self) -> None:
        """Cancel any pending debounced callback."""
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        self._pending_folders.clear()
