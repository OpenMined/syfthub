"""
File-based endpoint configuration mode for SyftHub API.

This module provides dynamic, hot-reloadable endpoint configuration
through a folder-based approach where each endpoint is defined by:
- README.md with YAML frontmatter for metadata
- runner.py with the handler function
- .env (optional) with endpoint-specific environment variables
- pyproject.toml (optional) with endpoint-specific dependencies
- policy/ folder with YAML policy configurations

Example folder structure:
    /endpoints/
    ├── my-model/
    │   ├── README.md
    │   ├── runner.py
    │   ├── .env              # Endpoint-specific secrets
    │   ├── pyproject.toml    # Endpoint-specific dependencies
    │   └── policy/
    │       └── rate_limit.yaml
    └── my-datasource/
        ├── README.md
        └── runner.py

Environment variables from .env are loaded into ctx.metadata["env"]
and can be accessed in the handler function without polluting os.environ.

Runtime modes:
- in_process: Direct execution (default, fastest)
- subprocess: Isolated execution with virtual environments
- container: Docker-based isolation (future)
"""

from .env_loader import (
    load_endpoint_env,
    merge_env_with_inheritance,
    validate_required_env,
)
from .executors import (
    EndpointExecutor,
    ExecutionResult,
    ExecutorFactory,
    InProcessExecutor,
    SubprocessExecutor,
)
from .loader import EndpointLoader
from .policy_loader import PolicyFactory
from .provider import FileBasedEndpointProvider
from .requirements_manager import RequirementsManager, validate_endpoint_dependencies
from .schemas import EndpointConfig, EnvConfig, PolicyConfig, RuntimeConfig
from .venv_manager import VenvManager, ensure_venv_ready
from .watcher import FileSystemWatcher

__all__ = [
    # Provider
    "FileBasedEndpointProvider",
    # Loader
    "EndpointLoader",
    # Executors
    "EndpointExecutor",
    "ExecutionResult",
    "ExecutorFactory",
    "InProcessExecutor",
    "SubprocessExecutor",
    # Virtual environment
    "VenvManager",
    "ensure_venv_ready",
    # Requirements
    "RequirementsManager",
    "validate_endpoint_dependencies",
    # Policies
    "PolicyFactory",
    # Watcher
    "FileSystemWatcher",
    # Schemas
    "EndpointConfig",
    "EnvConfig",
    "PolicyConfig",
    "RuntimeConfig",
    # Environment
    "load_endpoint_env",
    "merge_env_with_inheritance",
    "validate_required_env",
]
