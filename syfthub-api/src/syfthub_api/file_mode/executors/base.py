"""
Base classes for endpoint executors.

This module defines the abstract interface (Port) for endpoint execution,
following the Ports & Adapters / Strategy pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionResult:
    """
    Result of an endpoint execution.

    Encapsulates the result or error from handler execution,
    along with timing and metadata.
    """

    success: bool
    """Whether the execution completed successfully."""

    result: Any = None
    """The handler return value (if successful)."""

    error: str | None = None
    """Error message (if failed)."""

    error_type: str | None = None
    """Error type name (if failed)."""

    execution_time_ms: float = 0.0
    """Time taken to execute the handler in milliseconds."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional execution metadata."""

    @classmethod
    def from_success(
        cls,
        result: Any,
        execution_time_ms: float = 0.0,
        **metadata: Any,
    ) -> ExecutionResult:
        """Create a successful execution result."""
        return cls(
            success=True,
            result=result,
            execution_time_ms=execution_time_ms,
            metadata=metadata,
        )

    @classmethod
    def from_error(
        cls,
        error: Exception,
        execution_time_ms: float = 0.0,
        **metadata: Any,
    ) -> ExecutionResult:
        """Create a failed execution result from an exception."""
        return cls(
            success=False,
            error=str(error),
            error_type=type(error).__name__,
            execution_time_ms=execution_time_ms,
            metadata=metadata,
        )


class EndpointExecutor(ABC):
    """
    Abstract base class for endpoint executors.

    Defines the interface (Port) for executing endpoint handlers
    with different isolation strategies.

    Implementations:
    - InProcessExecutor: Direct execution in main process
    - SubprocessExecutor: Isolated execution with venv
    - ContainerExecutor: Docker-based isolation (future)
    """

    def __init__(
        self,
        endpoint_path: Path,
        endpoint_slug: str,
        handler_fn: Any,
        env_vars: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize the executor.

        Args:
            endpoint_path: Path to the endpoint folder.
            endpoint_slug: Endpoint slug for logging/identification.
            handler_fn: The handler function to execute.
            env_vars: Endpoint-specific environment variables.
        """
        self.endpoint_path = endpoint_path
        self.endpoint_slug = endpoint_slug
        self.handler_fn = handler_fn
        self.env_vars = env_vars or {}
        self._started = False

    @property
    def is_started(self) -> bool:
        """Check if the executor has been started."""
        return self._started

    @abstractmethod
    async def start(self) -> None:
        """
        Initialize the executor.

        Called once when the endpoint is loaded. For subprocess mode,
        this creates the venv and starts worker processes.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the executor and cleanup resources.

        Called when the endpoint is unloaded or the server shuts down.
        """
        pass

    @abstractmethod
    async def execute(
        self,
        messages: list[Any],
        context: Any,
    ) -> ExecutionResult:
        """
        Execute the endpoint handler.

        Args:
            messages: List of messages to pass to the handler.
            context: RequestContext for the execution.

        Returns:
            ExecutionResult with the result or error.
        """
        pass

    @abstractmethod
    def supports_hot_reload(self) -> bool:
        """
        Check if this executor supports hot-reload without restart.

        Returns:
            True if handler can be reloaded in-place.
        """
        pass

    async def reload_handler(self, new_handler_fn: Any) -> None:
        """
        Reload the handler function.

        Called when runner.py changes and hot-reload is supported.

        Args:
            new_handler_fn: The new handler function.
        """
        if not self.supports_hot_reload():
            raise NotImplementedError(
                f"{self.__class__.__name__} does not support hot-reload. "
                "Full restart required."
            )
        self.handler_fn = new_handler_fn

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"endpoint={self.endpoint_slug!r}, "
            f"started={self._started})"
        )
