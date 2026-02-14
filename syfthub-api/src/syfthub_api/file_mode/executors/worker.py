"""
Worker module for subprocess execution.

This module runs in the subprocess and handles:
- Loading the endpoint handler from runner.py
- Executing the handler with provided inputs
- Serializing results back to the main process

This file is executed in the virtual environment of the endpoint.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import traceback
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for async handler functions
AsyncHandler = Callable[..., Coroutine[Any, Any, Any]]

# Maximum number of handlers to cache per worker process.
# Prevents unbounded memory growth if a worker handles many endpoints.
_HANDLER_CACHE_MAX_SIZE = 32


@dataclass
class WorkerRequest:
    """Request sent to a worker process."""

    runner_path: str
    messages: list[dict[str, Any]]
    context_data: dict[str, Any] | None
    endpoint_slug: str
    venv_path: str | None = None  # Path to endpoint's .venv for site-packages


@dataclass
class WorkerResponse:
    """Response from a worker process."""

    success: bool
    result: Any = None
    error: str | None = None
    error_type: str | None = None
    traceback: str | None = None


# LRU handler cache for performance (avoid reimporting on every request).
# Uses OrderedDict for LRU behavior with bounded size.
# Key: endpoint_slug, Value: async handler function
_handler_cache: OrderedDict[str, AsyncHandler] = OrderedDict()


def _get_or_load_handler(runner_path: Path, endpoint_slug: str) -> AsyncHandler:
    """
    Get handler from cache or load if not cached.

    Uses LRU cache with bounded size to prevent unbounded memory growth.
    Caches handlers within a worker's lifetime for performance.
    Hot-reload is handled by restarting the worker pool, so workers
    always start fresh with no cache.

    Args:
        runner_path: Path to runner.py file.
        endpoint_slug: Endpoint identifier for caching.

    Returns:
        The handler function.
    """
    global _handler_cache

    if endpoint_slug in _handler_cache:
        # Move to end (most recently used)
        _handler_cache.move_to_end(endpoint_slug)
        return _handler_cache[endpoint_slug]

    handler = _load_handler(runner_path)

    # Add to cache with LRU eviction
    _handler_cache[endpoint_slug] = handler
    if len(_handler_cache) > _HANDLER_CACHE_MAX_SIZE:
        # Remove least recently used (first item)
        _handler_cache.popitem(last=False)

    return handler


def _load_handler(runner_path: Path) -> AsyncHandler:
    """
    Load the handler function from runner.py.

    Args:
        runner_path: Path to runner.py file.

    Returns:
        The async handler function.

    Raises:
        ImportError: If module cannot be loaded or handler not found.
    """
    module_name = f"_worker_endpoint_{runner_path.parent.name}"
    logger.info(
        "Worker loading handler from: %s",
        runner_path,
    )

    # Remove old module if exists
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Load module
    spec = importlib.util.spec_from_file_location(
        module_name,
        runner_path,
        submodule_search_locations=[str(runner_path.parent)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create module spec for {runner_path}")

    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(runner_path.parent)]  # type: ignore
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    handler = getattr(module, "handler", None)
    if handler is None:
        raise ImportError("runner.py must define a 'handler' function")

    logger.info(
        "Worker handler loaded successfully for endpoint: %s",
        runner_path.parent.name,
    )
    return handler


def _create_mock_context(context_data: dict[str, Any] | None) -> Any:
    """
    Create a mock RequestContext for subprocess execution.

    Since the actual RequestContext might not serialize well,
    we create a lightweight mock that provides the essential data.

    Args:
        context_data: Serialized context data.

    Returns:
        Mock context object.
    """
    if context_data is None:
        return None

    class MockRequestContext:
        """Lightweight mock of RequestContext for subprocess execution."""

        def __init__(self, data: dict[str, Any]) -> None:
            self.request_id = data.get("request_id", "")
            self.user_id = data.get("user_id")
            self.session_id = data.get("session_id")
            self.metadata = data.get("metadata", {})
            self._data = data

        def __getattr__(self, name: str) -> Any:
            return self._data.get(name)

    return MockRequestContext(context_data)


def _convert_messages(messages: list[dict[str, Any]]) -> list[Any]:
    """
    Convert serialized message dicts back to Message objects.

    Args:
        messages: List of message dictionaries.

    Returns:
        List of Message objects.
    """
    # Import Message inside function to use endpoint's environment
    try:
        from syfthub_api.schemas import Message

        return [Message(**msg) for msg in messages]
    except ImportError:
        # If syfthub_api not available, create simple dataclass
        from dataclasses import dataclass as dc
        from typing import Optional

        @dc
        class SimpleMessage:
            role: str
            content: str
            name: Optional[str] = None

        return [SimpleMessage(**msg) for msg in messages]


async def _execute_handler_async(
    handler: Any,
    messages: list[Any],
    context: Any,
) -> Any:
    """Execute the async handler."""
    return await handler(messages=messages, ctx=context)


def _setup_venv_environment(venv_path: str) -> None:
    """
    Set up the virtual environment for the worker process.

    Adds the venv's site-packages to sys.path so the handler
    can import dependencies installed in the endpoint's venv.

    Args:
        venv_path: Path to the endpoint's .venv directory.
    """
    import site

    venv = Path(venv_path)
    logger.info(
        "Worker initializing with venv environment: %s",
        venv_path,
    )

    # Determine site-packages path based on platform
    if sys.platform == "win32":
        site_packages = venv / "Lib" / "site-packages"
    else:
        # Find the Python version directory
        lib_path = venv / "lib"
        if lib_path.exists():
            # Find python3.X directory
            python_dirs = list(lib_path.glob("python3.*"))
            if python_dirs:
                site_packages = python_dirs[0] / "site-packages"
            else:
                site_packages = lib_path / "site-packages"
        else:
            logger.warning("Venv lib path not found: %s", lib_path)
            return

    if site_packages.exists():
        # Add to beginning of sys.path for priority
        site_packages_str = str(site_packages)
        if site_packages_str not in sys.path:
            sys.path.insert(0, site_packages_str)
            # Also add using site module to ensure proper initialization
            site.addsitedir(site_packages_str)
            logger.info(
                "Worker sys.path updated with venv site-packages: %s",
                site_packages_str,
            )
    else:
        logger.warning("Venv site-packages not found: %s", site_packages)


def execute_in_worker(request: WorkerRequest) -> WorkerResponse:
    """
    Execute an endpoint handler in the worker process.

    This function is called by loky in the subprocess.

    Args:
        request: WorkerRequest with execution details.

    Returns:
        WorkerResponse with the result or error.
    """
    try:
        runner_path = Path(request.runner_path)

        # Set up venv environment if specified
        if request.venv_path:
            _setup_venv_environment(request.venv_path)

        # Load handler (cached within worker lifetime for performance)
        handler = _get_or_load_handler(
            runner_path=runner_path,
            endpoint_slug=request.endpoint_slug,
        )

        # Prepare inputs
        messages = _convert_messages(request.messages)
        context = _create_mock_context(request.context_data)

        # Execute handler (it's async, so we need an event loop)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _execute_handler_async(handler, messages, context)
            )
        finally:
            loop.close()

        return WorkerResponse(
            success=True,
            result=result,
        )

    except ModuleNotFoundError as e:
        # Provide helpful hint about missing dependencies
        module_name = getattr(e, "name", str(e))
        error_msg = (
            f"Missing module '{module_name}' in endpoint '{request.endpoint_slug}'. "
            f"Add '{module_name}' to the dependencies list in pyproject.toml and restart."
        )
        logger.error(error_msg)
        return WorkerResponse(
            success=False,
            error=error_msg,
            error_type="ModuleNotFoundError",
            traceback=traceback.format_exc(),
        )

    except Exception as e:
        return WorkerResponse(
            success=False,
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
        )


# For testing the worker directly
if __name__ == "__main__":
    import json

    # Read request from stdin
    request_data = json.loads(sys.stdin.read())
    request = WorkerRequest(**request_data)

    # Execute
    response = execute_in_worker(request)

    # Write response to stdout
    print(
        json.dumps(
            {
                "success": response.success,
                "result": response.result,
                "error": response.error,
                "error_type": response.error_type,
                "traceback": response.traceback,
            }
        )
    )
