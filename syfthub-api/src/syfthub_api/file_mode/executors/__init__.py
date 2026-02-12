"""
Endpoint executors for different isolation modes.

This package provides the Strategy pattern implementation for
endpoint execution, supporting:
- in_process: Direct execution (default, fastest)
- subprocess: Isolated execution with virtual environments
- container: Docker-based isolation (future)
"""

from .base import EndpointExecutor, ExecutionResult
from .factory import ExecutorFactory, create_executor, get_executor_factory
from .in_process import InProcessExecutor
from .subprocess import SubprocessExecutor

__all__ = [
    "EndpointExecutor",
    "ExecutionResult",
    "ExecutorFactory",
    "InProcessExecutor",
    "SubprocessExecutor",
    "create_executor",
    "get_executor_factory",
]
