"""
Endpoint loader for file-based configuration.

This module provides the EndpointLoader class that loads endpoints
from folder structures containing README.md and runner.py files.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import logging
import sys
import typing
from collections.abc import Callable, Coroutine
from functools import wraps
from pathlib import Path
from typing import Any

import frontmatter
from pydantic import ValidationError

from policy_manager.context import RequestContext
from policy_manager.policies.base import Policy

from ..schemas import Document, EndpointType, Message
from .env_loader import (
    load_endpoint_env,
    merge_env_with_inheritance,
    validate_required_env,
)
from .policy_loader import PolicyFactory, PolicyLoadError, get_default_factory
from .requirements_manager import RequirementsManager, validate_endpoint_dependencies
from .schemas import EndpointConfig, FileEndpointDefinition

logger = logging.getLogger(__name__)


class EndpointLoadError(Exception):
    """Raised when an endpoint fails to load from a folder."""

    def __init__(
        self,
        message: str,
        folder_path: Path | None = None,
        cause: Exception | None = None,
    ):
        self.folder_path = folder_path
        self.cause = cause
        super().__init__(message)


class EndpointLoader:
    """
    Loads endpoints from folder-based configuration.

    Each endpoint folder should contain:
    - README.md: YAML frontmatter with endpoint metadata
    - runner.py: Python module with handler function
    - policy/ (optional): Folder with YAML policy configurations

    Example folder structure:
        my-endpoint/
        ├── README.md
        ├── runner.py
        └── policy/
            └── rate_limit.yaml
    """

    # Required files
    README_FILE = "README.md"
    RUNNER_FILE = "runner.py"
    POLICY_FOLDER = "policy"
    ENV_FILE = ".env"
    PYPROJECT_FILE = "pyproject.toml"

    # Handler function name in runner.py
    HANDLER_NAME = "handler"

    def __init__(self, policy_factory: PolicyFactory | None = None) -> None:
        """
        Initialize the endpoint loader.

        Args:
            policy_factory: Optional custom PolicyFactory. Uses default if not provided.
        """
        self._policy_factory = policy_factory or get_default_factory()
        self._loaded_modules: dict[str, Any] = {}

    @staticmethod
    def _get_module_name(folder: Path) -> str:
        """
        Generate a unique, stable module name for an endpoint folder.

        Uses path hash instead of id() to ensure the same folder always
        gets the same module name, even across process restarts.

        Args:
            folder: Path to the endpoint folder.

        Returns:
            Unique module name string.
        """
        path_hash = hashlib.md5(str(folder.absolute()).encode()).hexdigest()[:12]
        return f"_syfthub_endpoint_{folder.name}_{path_hash}"

    async def load(self, folder: Path) -> dict[str, Any]:
        """
        Load an endpoint from a folder.

        Args:
            folder: Path to the endpoint folder.

        Returns:
            Endpoint dict compatible with SyftAPI.endpoints format.

        Raises:
            EndpointLoadError: If loading fails.
        """
        if not folder.is_dir():
            raise EndpointLoadError(f"Not a directory: {folder}", folder_path=folder)

        # 1. Parse README.md for metadata
        readme_path = folder / self.README_FILE
        config, readme_content = self._parse_readme(readme_path)

        if not config.enabled:
            logger.info("Endpoint '%s' is disabled, skipping", config.slug)
            raise EndpointLoadError(
                f"Endpoint '{config.slug}' is disabled",
                folder_path=folder,
            )

        # 2. Load runner.py handler
        runner_path = folder / self.RUNNER_FILE
        handler = self._load_handler(runner_path, folder)

        # 3. Validate handler signature
        self._validate_handler_signature(handler, config.type, runner_path)

        # 4. Create wrapper to adapt unified signature
        wrapped_fn = self._create_wrapper(handler, config.type)

        # 5. Load policies from policy/ folder
        policy_folder = folder / self.POLICY_FOLDER
        policies = await self._policy_factory.load_policies_from_folder(policy_folder)

        # 6. Load environment variables from .env file
        endpoint_env = load_endpoint_env(folder, self.ENV_FILE)

        # Merge with inherited variables if configured
        env_config = config.env
        if env_config.inherit:
            endpoint_env = merge_env_with_inheritance(
                endpoint_env=endpoint_env,
                inherit_vars=env_config.inherit,
            )

        # Validate required env vars (warn but don't fail)
        if env_config.required:
            validate_required_env(
                env_vars=endpoint_env,
                required=env_config.required,
                endpoint_name=config.slug,
            )

        # 7. Validate dependencies from pyproject.toml (warn but don't fail)
        runtime_config = config.runtime
        req_manager = RequirementsManager(folder)
        requirements_hash = ""

        if req_manager.has_pyproject():
            # Validate dependencies are installed (for in_process mode)
            if runtime_config.mode == "in_process":
                validate_endpoint_dependencies(
                    endpoint_path=folder,
                    endpoint_name=config.slug,
                    extras=runtime_config.extras or None,
                )
            requirements_hash = req_manager.get_requirements_hash()

        env_count = len(endpoint_env)
        deps_count = len(req_manager.get_dependencies()) if req_manager.has_pyproject() else 0
        logger.info(
            "Loaded endpoint '%s' (%s) from %s with %d policies, %d env vars, %d deps, mode=%s",
            config.slug,
            config.type,
            folder.name,
            len(policies),
            env_count,
            deps_count,
            runtime_config.mode,
        )

        return {
            "type": EndpointType(config.type),
            "slug": config.slug,
            "name": config.name,
            "description": config.description or f"File-based endpoint: {config.name}",
            "version": config.version,
            "fn": wrapped_fn,
            "policies": policies,
            "_source_path": str(folder.absolute()),
            "_file_mode": True,  # Marker for file-based endpoints
            "_config": config.model_dump(),
            "_env": endpoint_env,  # Endpoint-specific environment variables
            "_runtime": runtime_config.model_dump(),  # Runtime execution config
            "_requirements_hash": requirements_hash,  # For detecting dep changes
            "_readme_body": readme_content,  # README body after frontmatter
        }

    def _parse_readme(self, readme_path: Path) -> tuple[EndpointConfig, str]:
        """
        Parse README.md file for endpoint configuration.

        Args:
            readme_path: Path to README.md file.

        Returns:
            Tuple of (EndpointConfig, readme_content_after_frontmatter).

        Raises:
            EndpointLoadError: If file cannot be parsed.
        """
        if not readme_path.exists():
            raise EndpointLoadError(
                f"README.md not found: {readme_path}",
                folder_path=readme_path.parent,
            )

        try:
            post = frontmatter.load(readme_path)
            metadata = dict(post.metadata)
            content = post.content

            if not metadata:
                raise EndpointLoadError(
                    "README.md must have YAML frontmatter with endpoint configuration",
                    folder_path=readme_path.parent,
                )

            config = EndpointConfig.model_validate(metadata)
            return config, content

        except ValidationError as e:
            raise EndpointLoadError(
                f"Invalid endpoint configuration in README.md: {e}",
                folder_path=readme_path.parent,
                cause=e,
            ) from e
        except Exception as e:
            raise EndpointLoadError(
                f"Failed to parse README.md: {e}",
                folder_path=readme_path.parent,
                cause=e,
            ) from e

    def _load_handler(
        self, runner_path: Path, folder: Path
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        """
        Load handler function from runner.py.

        Args:
            runner_path: Path to runner.py file.
            folder: Parent folder for module path setup.

        Returns:
            The handler function.

        Raises:
            EndpointLoadError: If handler cannot be loaded.
        """
        if not runner_path.exists():
            raise EndpointLoadError(
                f"runner.py not found: {runner_path}",
                folder_path=folder,
            )

        try:
            # Create unique, stable module name based on folder path
            module_name = self._get_module_name(folder)

            # Remove old module if reloading
            if module_name in sys.modules:
                del sys.modules[module_name]
            if module_name in self._loaded_modules:
                del self._loaded_modules[module_name]

            # Load module from file
            spec = importlib.util.spec_from_file_location(
                module_name,
                runner_path,
                submodule_search_locations=[str(folder)],
            )
            if spec is None or spec.loader is None:
                raise EndpointLoadError(
                    f"Failed to create module spec for {runner_path}",
                    folder_path=folder,
                )

            module = importlib.util.module_from_spec(spec)

            # Add folder to module's path for relative imports
            module.__path__ = [str(folder)]  # type: ignore

            # Add to sys.modules before exec to allow self-imports
            sys.modules[module_name] = module

            # Execute module
            spec.loader.exec_module(module)

            # Track loaded module
            self._loaded_modules[module_name] = module

            # Get handler function
            handler = getattr(module, self.HANDLER_NAME, None)
            if handler is None:
                raise EndpointLoadError(
                    f"runner.py must define a '{self.HANDLER_NAME}' function",
                    folder_path=folder,
                )

            if not callable(handler):
                raise EndpointLoadError(
                    f"'{self.HANDLER_NAME}' must be a callable function",
                    folder_path=folder,
                )

            return handler

        except EndpointLoadError:
            raise
        except SyntaxError as e:
            raise EndpointLoadError(
                f"Syntax error in runner.py: {e}",
                folder_path=folder,
                cause=e,
            ) from e
        except Exception as e:
            raise EndpointLoadError(
                f"Failed to load runner.py: {e}",
                folder_path=folder,
                cause=e,
            ) from e

    def _validate_handler_signature(
        self,
        handler: Callable[..., Any],
        endpoint_type: str,
        runner_path: Path,
    ) -> None:
        """
        Validate handler function signature.

        Expected signature:
            async def handler(messages: list[Message], ctx: RequestContext) -> str | list[Document]

        Args:
            handler: The handler function to validate.
            endpoint_type: 'model' or 'data_source'.
            runner_path: Path for error reporting.

        Raises:
            EndpointLoadError: If signature is invalid.
        """
        # Check if async
        if not inspect.iscoroutinefunction(handler):
            raise EndpointLoadError(
                f"Handler must be an async function, got {type(handler).__name__}",
                folder_path=runner_path.parent,
            )

        # Check parameters
        sig = inspect.signature(handler)
        params = list(sig.parameters.keys())

        if "messages" not in params:
            raise EndpointLoadError(
                "Handler must accept 'messages' parameter (list[Message])",
                folder_path=runner_path.parent,
            )

        if "ctx" not in params:
            raise EndpointLoadError(
                "Handler must accept 'ctx' parameter (RequestContext)",
                folder_path=runner_path.parent,
            )

        # Optionally validate type hints if present
        try:
            hints = typing.get_type_hints(handler)
            return_hint = hints.get("return")

            if return_hint is not None:
                # Check return type matches endpoint type
                # This is informational, not enforced
                logger.debug(
                    "Handler return type hint: %s (endpoint type: %s)",
                    return_hint,
                    endpoint_type,
                )
        except Exception:
            # Type hints are optional
            pass

    def _create_wrapper(
        self,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        endpoint_type: str,
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        """
        Create wrapper to adapt unified handler signature to SyftAPI expectations.

        For datasource endpoints:
            SyftAPI calls with (query: str, ctx: RequestContext)
            We convert to (messages: list[Message], ctx: RequestContext)

        For model endpoints:
            SyftAPI calls with (messages: list[Message], ctx: RequestContext)
            Direct pass-through

        Args:
            handler: The original handler function.
            endpoint_type: 'model' or 'data_source'.

        Returns:
            Wrapped function with appropriate signature.
        """
        if endpoint_type == "data_source":

            @wraps(handler)
            async def datasource_wrapper(
                query: str, ctx: RequestContext | None = None
            ) -> list[Document]:
                """Wrapper that converts query to messages format."""
                messages = [Message(role="user", content=query)]
                result = await handler(messages=messages, ctx=ctx)

                # Ensure result is list of Documents
                if not isinstance(result, list):
                    raise TypeError(
                        f"Datasource handler must return list[Document], got {type(result).__name__}"
                    )
                return result

            return datasource_wrapper

        else:  # model

            @wraps(handler)
            async def model_wrapper(
                messages: list[Message], ctx: RequestContext | None = None
            ) -> str:
                """Wrapper for model endpoints."""
                result = await handler(messages=messages, ctx=ctx)

                # Ensure result is string
                if not isinstance(result, str):
                    raise TypeError(
                        f"Model handler must return str, got {type(result).__name__}"
                    )
                return result

            return model_wrapper

    def unload(self, folder: Path) -> bool:
        """
        Unload a previously loaded endpoint module.

        Args:
            folder: Path to the endpoint folder.

        Returns:
            True if module was unloaded, False if it wasn't loaded.
        """
        module_name = self._get_module_name(folder)

        unloaded = False
        if module_name in sys.modules:
            del sys.modules[module_name]
            unloaded = True
        if module_name in self._loaded_modules:
            del self._loaded_modules[module_name]
            unloaded = True

        if unloaded:
            logger.debug("Unloaded endpoint module: %s", module_name)

        return unloaded

    def cleanup(self) -> None:
        """Unload all loaded modules."""
        for module_name in list(self._loaded_modules.keys()):
            if module_name in sys.modules:
                del sys.modules[module_name]
            del self._loaded_modules[module_name]

        logger.debug("Cleaned up %d loaded modules", len(self._loaded_modules))
