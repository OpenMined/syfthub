"""
Factory for creating endpoint executors.

Provides a single entry point for creating the appropriate executor
based on endpoint runtime configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from .base import EndpointExecutor
from .in_process import InProcessExecutor
from .subprocess import SubprocessExecutor

logger = logging.getLogger(__name__)

# Type alias for runtime modes
RuntimeMode = Literal["in_process", "subprocess", "container"]


class ExecutorFactory:
    """
    Factory for creating endpoint executors.

    Creates the appropriate executor based on the runtime configuration
    specified in the endpoint's README.md frontmatter.

    Example:
        factory = ExecutorFactory()

        # Create from endpoint data
        executor = factory.create_from_endpoint(endpoint_data)

        # Or create directly
        executor = factory.create(
            mode="subprocess",
            endpoint_path=Path("/path/to/endpoint"),
            endpoint_slug="my-endpoint",
            handler_fn=handler,
        )
    """

    def create(
        self,
        mode: RuntimeMode,
        endpoint_path: Path,
        endpoint_slug: str,
        handler_fn: Any,
        env_vars: dict[str, str] | None = None,
        workers: int = 2,
        timeout: int = 30,
        idle_timeout: int = 300,
        requirements_hash: str = "",
        extras: list[str] | None = None,
    ) -> EndpointExecutor:
        """
        Create an executor for the specified mode.

        Args:
            mode: Execution mode ('in_process', 'subprocess', 'container').
            endpoint_path: Path to the endpoint folder.
            endpoint_slug: Endpoint identifier.
            handler_fn: The handler function.
            env_vars: Endpoint-specific environment variables.
            workers: Number of worker processes (subprocess mode).
            timeout: Execution timeout in seconds.
            idle_timeout: Worker idle timeout (subprocess mode).
            requirements_hash: Hash of dependencies for change detection.
            extras: Optional extras to install.

        Returns:
            Appropriate EndpointExecutor instance.

        Raises:
            ValueError: If mode is not supported.
        """
        if mode == "in_process":
            logger.debug(
                "Creating InProcessExecutor for endpoint '%s'",
                endpoint_slug,
            )
            return InProcessExecutor(
                endpoint_path=endpoint_path,
                endpoint_slug=endpoint_slug,
                handler_fn=handler_fn,
                env_vars=env_vars,
            )

        elif mode == "subprocess":
            logger.debug(
                "Creating SubprocessExecutor for endpoint '%s' "
                "(workers=%d, timeout=%ds)",
                endpoint_slug,
                workers,
                timeout,
            )
            return SubprocessExecutor(
                endpoint_path=endpoint_path,
                endpoint_slug=endpoint_slug,
                handler_fn=handler_fn,
                env_vars=env_vars,
                workers=workers,
                timeout=timeout,
                idle_timeout=idle_timeout,
                requirements_hash=requirements_hash,
                extras=extras,
            )

        elif mode == "container":
            # Container mode is planned for future implementation
            raise NotImplementedError(
                "Container execution mode is not yet implemented. "
                "Use 'subprocess' mode for isolation, or 'in_process' for speed."
            )

        else:
            raise ValueError(
                f"Unknown runtime mode: {mode}. "
                f"Supported modes: in_process, subprocess, container"
            )

    def create_from_endpoint(
        self,
        endpoint_data: dict[str, Any],
    ) -> EndpointExecutor:
        """
        Create an executor from endpoint data dictionary.

        This is the primary method used by the provider to create
        executors from loaded endpoint configurations.

        Args:
            endpoint_data: Endpoint data from EndpointLoader.load().

        Returns:
            Configured EndpointExecutor instance.

        Raises:
            ValueError: If required data is missing.
        """
        # Extract required fields
        source_path = endpoint_data.get("_source_path")
        if not source_path:
            raise ValueError("Endpoint data missing '_source_path'")

        endpoint_path = Path(source_path)
        endpoint_slug = endpoint_data.get("slug", endpoint_path.name)
        handler_fn = endpoint_data.get("fn")

        if handler_fn is None:
            raise ValueError("Endpoint data missing 'fn' (handler function)")

        # Extract optional configuration
        env_vars = endpoint_data.get("_env", {})
        runtime_config = endpoint_data.get("_runtime", {})
        requirements_hash = endpoint_data.get("_requirements_hash", "")

        # Get runtime settings
        mode = runtime_config.get("mode", "in_process")
        workers = runtime_config.get("workers", 2)
        timeout = runtime_config.get("timeout", 30)
        idle_timeout = runtime_config.get("idle_timeout", 300)
        extras = runtime_config.get("extras", [])

        return self.create(
            mode=mode,
            endpoint_path=endpoint_path,
            endpoint_slug=endpoint_slug,
            handler_fn=handler_fn,
            env_vars=env_vars,
            workers=workers,
            timeout=timeout,
            idle_timeout=idle_timeout,
            requirements_hash=requirements_hash,
            extras=extras if extras else None,
        )


# Singleton factory instance
_factory: ExecutorFactory | None = None


def get_executor_factory() -> ExecutorFactory:
    """
    Get the global executor factory instance.

    Returns:
        ExecutorFactory singleton.
    """
    global _factory
    if _factory is None:
        _factory = ExecutorFactory()
    return _factory


def create_executor(
    mode: RuntimeMode,
    endpoint_path: Path,
    endpoint_slug: str,
    handler_fn: Any,
    **kwargs: Any,
) -> EndpointExecutor:
    """
    Convenience function to create an executor.

    Args:
        mode: Execution mode.
        endpoint_path: Path to the endpoint folder.
        endpoint_slug: Endpoint identifier.
        handler_fn: The handler function.
        **kwargs: Additional executor arguments.

    Returns:
        EndpointExecutor instance.
    """
    return get_executor_factory().create(
        mode=mode,
        endpoint_path=endpoint_path,
        endpoint_slug=endpoint_slug,
        handler_fn=handler_fn,
        **kwargs,
    )
