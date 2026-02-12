"""
Policy loader for file-based endpoint configuration.

This module provides a PolicyFactory that creates Policy instances
from YAML configuration files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from policy_manager.policies import (
    AccessGroupPolicy,
    AllOf,
    AnyOf,
    AttributionPolicy,
    CustomPolicy,
    ManualReviewPolicy,
    Not,
    Policy,
    PromptFilterPolicy,
    RateLimitPolicy,
    TokenLimitPolicy,
    TransactionPolicy,
)

from .schemas import PolicyConfig

logger = logging.getLogger(__name__)


class PolicyLoadError(Exception):
    """Raised when a policy fails to load from configuration."""

    def __init__(self, message: str, file_path: Path | None = None, cause: Exception | None = None):
        self.file_path = file_path
        self.cause = cause
        super().__init__(message)


class PolicyFactory:
    """
    Factory for creating Policy instances from YAML configurations.

    The factory maintains a registry of known policy types that can be
    extended with custom policy classes.

    Example usage:
        factory = PolicyFactory()
        factory.register("MyCustomPolicy", MyCustomPolicy)

        config = PolicyConfig(type="RateLimitPolicy", config={"max_requests": 100})
        policy = factory.create(config)
    """

    # Default registry of built-in policy types
    _default_registry: dict[str, type[Policy]] = {
        "RateLimitPolicy": RateLimitPolicy,
        "TokenLimitPolicy": TokenLimitPolicy,
        "AccessGroupPolicy": AccessGroupPolicy,
        "PromptFilterPolicy": PromptFilterPolicy,
        "ManualReviewPolicy": ManualReviewPolicy,
        "TransactionPolicy": TransactionPolicy,
        "AttributionPolicy": AttributionPolicy,
        "CustomPolicy": CustomPolicy,
        "AllOf": AllOf,
        "AnyOf": AnyOf,
        "Not": Not,
    }

    def __init__(self) -> None:
        """Initialize factory with a copy of the default registry."""
        self._registry: dict[str, type[Policy]] = dict(self._default_registry)

    def register(self, name: str, policy_class: type[Policy]) -> None:
        """
        Register a custom policy class.

        Args:
            name: The name to use in YAML configurations.
            policy_class: The Policy subclass to register.

        Example:
            factory.register("BusinessHoursPolicy", BusinessHoursPolicy)
        """
        if not isinstance(policy_class, type) or not issubclass(policy_class, Policy):
            raise TypeError(f"{policy_class} must be a Policy subclass")
        self._registry[name] = policy_class
        logger.debug("Registered policy type: %s", name)

    def unregister(self, name: str) -> bool:
        """
        Unregister a policy class.

        Args:
            name: The policy type name to remove.

        Returns:
            True if the policy was removed, False if it wasn't registered.
        """
        if name in self._registry:
            del self._registry[name]
            return True
        return False

    def get_registered_types(self) -> list[str]:
        """Return list of registered policy type names."""
        return list(self._registry.keys())

    def create(self, config: PolicyConfig) -> Policy:
        """
        Create a Policy instance from configuration.

        Handles both simple policies and composite policies (AllOf, AnyOf, Not)
        that contain nested child policies.

        Args:
            config: The PolicyConfig parsed from YAML.

        Returns:
            Configured Policy instance.

        Raises:
            PolicyLoadError: If the policy type is unknown or configuration is invalid.
        """
        policy_class = self._registry.get(config.type)
        if policy_class is None:
            raise PolicyLoadError(
                f"Unknown policy type: '{config.type}'. "
                f"Available types: {', '.join(self._registry.keys())}"
            )

        policy_name = config.name or config.type

        try:
            # Handle composite policies (AllOf, AnyOf, Not)
            if config.policies is not None:
                if config.type == "Not":
                    # Not takes a single policy
                    if len(config.policies) != 1:
                        raise PolicyLoadError(
                            f"'Not' policy requires exactly one child policy, got {len(config.policies)}"
                        )
                    child_policy = self.create(config.policies[0])
                    return policy_class(child_policy, name=policy_name)  # type: ignore
                else:
                    # AllOf/AnyOf take multiple policies
                    child_policies = [self.create(p) for p in config.policies]
                    return policy_class(*child_policies, name=policy_name)  # type: ignore

            # Handle CustomPolicy specially (needs callable)
            if config.type == "CustomPolicy":
                # CustomPolicy from YAML is limited - can only do simple checks
                # Full custom policies should be defined in code
                logger.warning(
                    "CustomPolicy from YAML has limited functionality. "
                    "Consider defining custom policies in code."
                )
                return policy_class(
                    name=policy_name,
                    phase=config.config.get("phase", "pre"),
                    check=lambda ctx: True,  # Placeholder - always passes
                    deny_reason=config.config.get("deny_reason", "Custom policy denied"),
                )

            # Standard policy instantiation
            return policy_class(name=policy_name, **config.config)

        except TypeError as e:
            raise PolicyLoadError(
                f"Invalid configuration for {config.type}: {e}"
            ) from e
        except Exception as e:
            raise PolicyLoadError(
                f"Failed to create {config.type} policy: {e}"
            ) from e

    def load_from_yaml(self, yaml_content: str, file_path: Path | None = None) -> Policy:
        """
        Load a policy from YAML content.

        Args:
            yaml_content: Raw YAML string.
            file_path: Optional path for error reporting.

        Returns:
            Configured Policy instance.

        Raises:
            PolicyLoadError: If parsing or creation fails.
        """
        try:
            data = yaml.safe_load(yaml_content)
            if not isinstance(data, dict):
                raise PolicyLoadError(
                    "Policy YAML must be a mapping (dictionary)",
                    file_path=file_path,
                )
            config = PolicyConfig.model_validate(data)
            return self.create(config)
        except yaml.YAMLError as e:
            raise PolicyLoadError(
                f"Invalid YAML syntax: {e}",
                file_path=file_path,
                cause=e,
            ) from e
        except ValidationError as e:
            raise PolicyLoadError(
                f"Invalid policy configuration: {e}",
                file_path=file_path,
                cause=e,
            ) from e

    def load_from_file(self, file_path: Path) -> Policy:
        """
        Load a policy from a YAML file.

        Args:
            file_path: Path to the .yaml or .yml file.

        Returns:
            Configured Policy instance.

        Raises:
            PolicyLoadError: If the file cannot be read or parsed.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            return self.load_from_yaml(content, file_path=file_path)
        except FileNotFoundError as e:
            raise PolicyLoadError(
                f"Policy file not found: {file_path}",
                file_path=file_path,
                cause=e,
            ) from e
        except PermissionError as e:
            raise PolicyLoadError(
                f"Permission denied reading policy file: {file_path}",
                file_path=file_path,
                cause=e,
            ) from e

    async def load_policies_from_folder(self, folder: Path) -> list[Policy]:
        """
        Load all policies from a folder.

        Reads all .yaml and .yml files in the folder and creates
        Policy instances for each.

        Args:
            folder: Path to the policy folder.

        Returns:
            List of loaded Policy instances.

        Note:
            Invalid policy files are logged and skipped, not raised.
            This allows partial loading when some policies are malformed.
        """
        policies: list[Policy] = []

        if not folder.exists():
            logger.debug("Policy folder does not exist: %s", folder)
            return policies

        if not folder.is_dir():
            logger.warning("Policy path is not a directory: %s", folder)
            return policies

        yaml_files = list(folder.glob("*.yaml")) + list(folder.glob("*.yml"))
        logger.debug("Found %d policy files in %s", len(yaml_files), folder)

        for file_path in sorted(yaml_files):
            try:
                policy = self.load_from_file(file_path)
                policies.append(policy)
                logger.info("Loaded policy '%s' from %s", policy.name, file_path.name)
            except PolicyLoadError as e:
                logger.error("Failed to load policy from %s: %s", file_path, e)
                # Continue loading other policies

        return policies


# Module-level factory instance for convenience
_default_factory: PolicyFactory | None = None


def get_default_factory() -> PolicyFactory:
    """Get the default PolicyFactory instance."""
    global _default_factory
    if _default_factory is None:
        _default_factory = PolicyFactory()
    return _default_factory
