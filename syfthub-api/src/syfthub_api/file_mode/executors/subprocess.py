"""
Subprocess endpoint executor with virtual environment isolation.

Executes handlers in isolated subprocess workers with per-endpoint
virtual environments for dependency isolation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any

from loky import get_reusable_executor
from policy_manager.context import RequestContext

from ..venv_manager import VenvManager
from .base import EndpointExecutor, ExecutionResult
from .worker import WorkerRequest, WorkerResponse, execute_in_worker

logger = logging.getLogger(__name__)

# Extra time (in seconds) added to asyncio timeout beyond the worker timeout.
# This allows the worker's internal timeout to fire first and return a proper
# TimeoutError, rather than having asyncio cancel the future mid-flight.
# Without this buffer, we might get BrokenProcessPool errors instead of clean timeouts.
_ASYNCIO_TIMEOUT_BUFFER_SECONDS = 1


class SubprocessExecutor(EndpointExecutor):
    """
    Executes endpoint handlers in isolated subprocesses.

    This executor provides:
    - Process-level isolation (crashes don't affect main process)
    - Virtual environment isolation (custom dependencies per endpoint)
    - Environment variable isolation
    - Configurable worker pool size
    - Timeout handling
    - Hot-reload support (workers detect version changes)

    Use this for:
    - Endpoints with custom dependencies (numpy, pandas, etc.)
    - Untrusted or experimental code
    - Resource-intensive operations
    - Production deployments requiring isolation

    Note:
    - Higher latency than in-process (~10-50ms overhead per call)
    - First request after hot-reload has module import latency
    - Requires serializable inputs/outputs
    """

    def __init__(
        self,
        endpoint_path: Path,
        endpoint_slug: str,
        handler_fn: Any,  # Not used directly, we reload in subprocess
        env_vars: dict[str, str] | None = None,
        workers: int = 2,
        timeout: int = 30,
        idle_timeout: int = 300,
        requirements_hash: str = "",
        extras: list[str] | None = None,
    ) -> None:
        """
        Initialize the subprocess executor.

        Args:
            endpoint_path: Path to the endpoint folder.
            endpoint_slug: Endpoint slug for identification.
            handler_fn: Handler function (for compatibility, not used).
            env_vars: Endpoint-specific environment variables.
            workers: Number of worker processes.
            timeout: Execution timeout in seconds.
            idle_timeout: Worker idle timeout before termination.
            requirements_hash: Hash of dependencies for change detection.
            extras: Optional extras to install from pyproject.toml.
        """
        super().__init__(endpoint_path, endpoint_slug, handler_fn, env_vars)
        self.workers = workers
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.requirements_hash = requirements_hash
        self.extras = extras

        self._venv_manager: VenvManager | None = None
        self._executor: Any = None
        self._runner_path = endpoint_path / "runner.py"

    async def start(self) -> None:
        """
        Initialize the executor.

        Creates/updates the virtual environment if needed,
        then initializes the loky worker pool.
        """
        if self._started:
            logger.debug(
                "SubprocessExecutor for '%s' already started",
                self.endpoint_slug,
            )
            return

        logger.info(
            "Starting SubprocessExecutor for endpoint '%s' (workers=%d, timeout=%ds)",
            self.endpoint_slug,
            self.workers,
            self.timeout,
        )

        # Create/update virtual environment if dependencies declared
        if self.requirements_hash:
            self._venv_manager = VenvManager(self.endpoint_path)

            if self._venv_manager.needs_rebuild(self.requirements_hash):
                logger.info(
                    "Creating/updating venv for endpoint '%s'",
                    self.endpoint_slug,
                )
                await self._venv_manager.create_or_update(
                    requirements_hash=self.requirements_hash,
                    extras=self.extras,
                )

        # Initialize the loky executor
        # Note: loky reuses workers across calls for efficiency
        self._executor = get_reusable_executor(
            max_workers=self.workers,
            timeout=self.idle_timeout,
            context="loky",  # Use loky's robust process spawning
        )

        self._started = True
        logger.info(
            "SubprocessExecutor for '%s' started with %d workers",
            self.endpoint_slug,
            self.workers,
        )

    async def stop(self) -> None:
        """
        Stop the executor and cleanup resources.

        Uses a two-phase shutdown strategy:
        1. First attempts graceful shutdown with a timeout
        2. If workers don't stop, forcefully terminates them

        This prevents zombie processes when workers are stuck or unresponsive.
        """
        if not self._started:
            return

        logger.info(
            "Stopping SubprocessExecutor for endpoint '%s'",
            self.endpoint_slug,
        )

        if self._executor is not None:
            try:
                # Phase 1: Graceful shutdown with short timeout
                # Give workers 2 seconds to finish current work
                logger.debug(
                    "SubprocessExecutor '%s': attempting graceful shutdown",
                    self.endpoint_slug,
                )
                self._executor.shutdown(wait=True, kill_workers=False)
            except Exception as e:
                logger.warning(
                    "SubprocessExecutor '%s': graceful shutdown failed: %s",
                    self.endpoint_slug,
                    e,
                )
            finally:
                # Phase 2: Force kill any remaining workers
                # This ensures no zombie processes are left
                try:
                    logger.debug(
                        "SubprocessExecutor '%s': forcing worker termination",
                        self.endpoint_slug,
                    )
                    self._executor.shutdown(wait=False, kill_workers=True)
                except Exception as e:
                    logger.warning(
                        "SubprocessExecutor '%s': force shutdown error (may be already stopped): %s",
                        self.endpoint_slug,
                        e,
                    )
                self._executor = None

        self._started = False
        logger.info(
            "SubprocessExecutor for '%s' stopped",
            self.endpoint_slug,
        )

    async def execute(
        self,
        messages: list[Any],
        context: RequestContext | None,
    ) -> ExecutionResult:
        """
        Execute the handler in a subprocess.

        Serializes the request, submits to worker pool, and
        deserializes the response.

        Args:
            messages: List of messages to pass to the handler.
            context: RequestContext for the execution.

        Returns:
            ExecutionResult with the result or error.
        """
        if not self._started or self._executor is None:
            return ExecutionResult.from_error(
                RuntimeError("Executor not started"),
                executor_type="subprocess",
            )

        start_time = time.perf_counter()

        try:
            # Prepare request
            request = self._prepare_request(messages, context)

            # Submit to worker pool
            future = self._executor.submit(execute_in_worker, request)

            # Wait for result with timeout
            # Run in thread to not block event loop
            response: WorkerResponse = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: future.result(timeout=self.timeout),
                ),
                timeout=self.timeout + _ASYNCIO_TIMEOUT_BUFFER_SECONDS,
            )

            execution_time = (time.perf_counter() - start_time) * 1000

            if response.success:
                logger.debug(
                    "SubprocessExecutor '%s' completed in %.2fms",
                    self.endpoint_slug,
                    execution_time,
                )
                return ExecutionResult.from_success(
                    result=response.result,
                    execution_time_ms=execution_time,
                    executor_type="subprocess",
                )
            else:
                logger.error(
                    "SubprocessExecutor '%s' failed: %s\n%s",
                    self.endpoint_slug,
                    response.error,
                    response.traceback,
                )
                # Re-create exception for proper error handling
                error = Exception(response.error or "Unknown error")
                error.__class__.__name__ = response.error_type or "Exception"
                return ExecutionResult(
                    success=False,
                    error=response.error,
                    error_type=response.error_type,
                    execution_time_ms=execution_time,
                    metadata={
                        "executor_type": "subprocess",
                        "traceback": response.traceback,
                    },
                )

        except (asyncio.TimeoutError, FuturesTimeoutError) as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                "SubprocessExecutor '%s' timed out after %.2fms (limit: %ds)",
                self.endpoint_slug,
                execution_time,
                self.timeout,
            )
            return ExecutionResult.from_error(
                TimeoutError(f"Execution timed out after {self.timeout}s"),
                execution_time_ms=execution_time,
                executor_type="subprocess",
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                "SubprocessExecutor '%s' failed after %.2fms: %s",
                self.endpoint_slug,
                execution_time,
                e,
            )
            return ExecutionResult.from_error(
                error=e,
                execution_time_ms=execution_time,
                executor_type="subprocess",
            )

    def _prepare_request(
        self,
        messages: list[Any],
        context: RequestContext | None,
    ) -> WorkerRequest:
        """
        Prepare a serializable request for the worker.

        Args:
            messages: List of messages.
            context: RequestContext.

        Returns:
            WorkerRequest ready for serialization.
        """
        # Serialize messages to dicts
        serialized_messages = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                serialized_messages.append(msg.model_dump())
            elif hasattr(msg, "__dict__"):
                serialized_messages.append(msg.__dict__)
            else:
                serialized_messages.append({"role": "user", "content": str(msg)})

        # Serialize context
        context_data = None
        if context is not None:
            context_data = {
                "request_id": getattr(context, "request_id", ""),
                "user_id": getattr(context, "user_id", None),
                "session_id": getattr(context, "session_id", None),
                "metadata": getattr(context, "metadata", {}),
            }
            # Include env vars in metadata
            if self.env_vars:
                if "env" not in context_data["metadata"]:
                    context_data["metadata"]["env"] = {}
                context_data["metadata"]["env"].update(self.env_vars)

        return WorkerRequest(
            runner_path=str(self._runner_path),
            messages=serialized_messages,
            context_data=context_data,
            endpoint_slug=self.endpoint_slug,
        )

    def supports_hot_reload(self) -> bool:
        """
        Subprocess executor supports hot-reload via worker pool restart.

        When code changes, the entire worker pool is restarted to ensure
        all workers load fresh code. This is simpler and more reliable
        than version-based caching.
        """
        return True

    async def reload_handler(self, new_handler_fn: Any) -> None:
        """
        Hot-reload by restarting the worker pool.

        This ensures all workers load fresh code from disk.
        Takes ~2-3 seconds but guarantees clean state.

        Args:
            new_handler_fn: The new handler function (not used directly,
                           workers load fresh from runner.py).
        """
        logger.info(
            "Hot-reload triggered for endpoint '%s', restarting worker pool",
            self.endpoint_slug,
        )

        # Update the handler_fn reference for compatibility
        self.handler_fn = new_handler_fn

        # Restart the worker pool - simple and reliable
        await self.restart()

    async def restart(self) -> None:
        """
        Restart the executor (for dependency/handler changes).

        Stops the current workers and creates new ones.
        """
        logger.info(
            "Restarting SubprocessExecutor for endpoint '%s'",
            self.endpoint_slug,
        )
        await self.stop()
        await self.start()

    def __repr__(self) -> str:
        return (
            f"SubprocessExecutor("
            f"endpoint={self.endpoint_slug!r}, "
            f"workers={self.workers}, "
            f"timeout={self.timeout}s, "
            f"started={self._started})"
        )
