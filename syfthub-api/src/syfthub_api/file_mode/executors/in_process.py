"""
In-process endpoint executor.

Executes handlers directly in the main process without isolation.
This is the default mode - fastest but shares the process environment.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from policy_manager.context import RequestContext

from .base import EndpointExecutor, ExecutionResult

logger = logging.getLogger(__name__)


class InProcessExecutor(EndpointExecutor):
    """
    Executes endpoint handlers directly in the main process.

    This is the default executor that provides:
    - Fastest execution (no IPC overhead)
    - Direct access to handler function
    - Hot-reload support (handler can be replaced)
    - Shared process environment (no isolation)

    Use this for:
    - Development and debugging
    - Endpoints that don't need custom dependencies
    - Performance-critical endpoints with trusted code
    """

    async def start(self) -> None:
        """
        Initialize the executor.

        For in-process execution, this is a no-op since we
        execute directly without any setup.
        """
        if self._started:
            logger.debug(
                "InProcessExecutor for '%s' already started",
                self.endpoint_slug,
            )
            return

        logger.debug(
            "Starting InProcessExecutor for endpoint '%s'",
            self.endpoint_slug,
        )
        self._started = True

    async def stop(self) -> None:
        """
        Stop the executor.

        For in-process execution, this is a no-op.
        """
        if not self._started:
            return

        logger.debug(
            "Stopping InProcessExecutor for endpoint '%s'",
            self.endpoint_slug,
        )
        self._started = False

    async def execute(
        self,
        messages: list[Any],
        context: RequestContext | None,
    ) -> ExecutionResult:
        """
        Execute the handler directly in the current process.

        Args:
            messages: List of messages to pass to the handler.
            context: RequestContext for the execution.

        Returns:
            ExecutionResult with the result or error.
        """
        if not self._started:
            return ExecutionResult.from_error(
                RuntimeError("Executor not started"),
                executor_type="in_process",
            )

        start_time = time.perf_counter()

        try:
            # Execute handler directly
            result = await self.handler_fn(messages=messages, ctx=context)

            execution_time = (time.perf_counter() - start_time) * 1000

            logger.debug(
                "InProcessExecutor '%s' completed in %.2fms",
                self.endpoint_slug,
                execution_time,
            )

            return ExecutionResult.from_success(
                result=result,
                execution_time_ms=execution_time,
                executor_type="in_process",
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000

            logger.error(
                "InProcessExecutor '%s' failed after %.2fms: %s",
                self.endpoint_slug,
                execution_time,
                e,
            )

            return ExecutionResult.from_error(
                error=e,
                execution_time_ms=execution_time,
                executor_type="in_process",
            )

    def supports_hot_reload(self) -> bool:
        """
        In-process executor supports hot-reload.

        The handler function can be directly replaced without
        needing to restart any processes.
        """
        return True

    async def reload_handler(self, new_handler_fn: Any) -> None:
        """
        Reload the handler function.

        Args:
            new_handler_fn: The new handler function.
        """
        logger.info(
            "Hot-reloading handler for endpoint '%s'",
            self.endpoint_slug,
        )
        self.handler_fn = new_handler_fn
