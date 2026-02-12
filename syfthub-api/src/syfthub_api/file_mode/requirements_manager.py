"""
Requirements manager for file-based endpoints.

This module provides utilities for parsing pyproject.toml files,
validating dependencies, and managing virtual environments for
isolated endpoint execution.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from importlib.metadata import PackageNotFoundError, version as get_version
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# pyproject.toml file name
PYPROJECT_FILE = "pyproject.toml"


def _parse_toml(path: Path) -> dict[str, Any]:
    """
    Parse a TOML file.

    Uses tomllib (Python 3.11+) or tomli as fallback.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed TOML as a dictionary.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found]

    with open(path, "rb") as f:
        return tomllib.load(f)


class RequirementsManager:
    """
    Manages endpoint dependencies from pyproject.toml.

    Parses pyproject.toml to extract dependencies and validates
    that they are installed in the current environment.

    Example pyproject.toml:
        [project]
        dependencies = [
            "numpy>=1.24",
            "pandas>=2.0",
        ]

        [project.optional-dependencies]
        ml = ["torch>=2.0"]
    """

    def __init__(self, endpoint_path: Path) -> None:
        """
        Initialize the requirements manager.

        Args:
            endpoint_path: Path to the endpoint folder.
        """
        self.endpoint_path = endpoint_path
        self.pyproject_file = endpoint_path / PYPROJECT_FILE
        self._parsed: dict[str, Any] | None = None

    def has_pyproject(self) -> bool:
        """Check if the endpoint has a pyproject.toml file."""
        return self.pyproject_file.exists()

    def _ensure_parsed(self) -> dict[str, Any]:
        """Ensure pyproject.toml is parsed and cached."""
        if self._parsed is None:
            if not self.has_pyproject():
                self._parsed = {}
            else:
                try:
                    self._parsed = _parse_toml(self.pyproject_file)
                except Exception as e:
                    logger.warning(
                        "Failed to parse %s: %s",
                        self.pyproject_file,
                        e,
                    )
                    self._parsed = {}
        return self._parsed

    def get_dependencies(self) -> list[str]:
        """
        Get the list of dependencies from pyproject.toml.

        Returns:
            List of dependency specifiers (e.g., ["numpy>=1.24", "pandas"]).
        """
        data = self._ensure_parsed()
        project = data.get("project", {})
        return list(project.get("dependencies", []))

    def get_optional_dependencies(self, extra: str | None = None) -> list[str]:
        """
        Get optional dependencies from pyproject.toml.

        Args:
            extra: Specific extra to get (e.g., "ml"). If None, returns all.

        Returns:
            List of optional dependency specifiers.
        """
        data = self._ensure_parsed()
        project = data.get("project", {})
        optional = project.get("optional-dependencies", {})

        if extra is not None:
            return list(optional.get(extra, []))

        # Return all optional dependencies
        all_deps: list[str] = []
        for deps in optional.values():
            all_deps.extend(deps)
        return all_deps

    def get_all_dependencies(self, extras: list[str] | None = None) -> list[str]:
        """
        Get all dependencies including specified extras.

        Args:
            extras: List of extras to include (e.g., ["ml", "dev"]).

        Returns:
            Combined list of all dependencies.
        """
        deps = self.get_dependencies()

        if extras:
            for extra in extras:
                deps.extend(self.get_optional_dependencies(extra))

        return deps

    def get_python_requires(self) -> str | None:
        """
        Get the required Python version from pyproject.toml.

        Returns:
            Python version specifier (e.g., ">=3.11") or None.
        """
        data = self._ensure_parsed()
        project = data.get("project", {})
        return project.get("requires-python")

    def get_requirements_hash(self) -> str:
        """
        Generate a hash of the pyproject.toml content.

        Used for detecting changes that require venv rebuild.

        Returns:
            SHA256 hash of the file content (12 chars), or empty string.
        """
        if not self.has_pyproject():
            return ""

        try:
            content = self.pyproject_file.read_bytes()
            return hashlib.sha256(content).hexdigest()[:12]
        except Exception:
            return ""

    def parse_requirement(self, req: str) -> tuple[str, str | None]:
        """
        Parse a requirement string into package name and version spec.

        Args:
            req: Requirement string (e.g., "numpy>=1.24,<2.0").

        Returns:
            Tuple of (package_name, version_spec or None).

        Examples:
            >>> parse_requirement("numpy>=1.24")
            ('numpy', '>=1.24')
            >>> parse_requirement("requests")
            ('requests', None)
            >>> parse_requirement("package[extra]>=1.0")
            ('package', '>=1.0')
        """
        # Remove extras like [ml] from package name
        req = re.sub(r"\[.*?\]", "", req)

        # Split on version operators
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*(.*)$", req.strip())
        if not match:
            return req.strip(), None

        name = match.group(1)
        version_spec = match.group(2).strip() or None

        return name, version_spec

    def validate_installed(
        self,
        extras: list[str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        Validate that all dependencies are installed.

        Args:
            extras: Optional list of extras to validate.

        Returns:
            Tuple of (missing_packages, version_mismatches).
            - missing_packages: Packages not installed at all.
            - version_mismatches: Packages installed but wrong version.
        """
        deps = self.get_all_dependencies(extras)
        missing: list[str] = []
        mismatches: list[str] = []

        for dep in deps:
            pkg_name, version_spec = self.parse_requirement(dep)

            try:
                installed_version = get_version(pkg_name)

                # If there's a version spec, check it (basic check)
                if version_spec:
                    if not self._check_version(installed_version, version_spec):
                        mismatches.append(
                            f"{pkg_name} (installed: {installed_version}, required: {version_spec})"
                        )

            except PackageNotFoundError:
                missing.append(pkg_name)

        return missing, mismatches

    def _check_version(self, installed: str, spec: str) -> bool:
        """
        Check if installed version satisfies the version spec.

        This is a basic implementation. For full PEP 440 compliance,
        use packaging.version.

        Args:
            installed: Installed version string.
            spec: Version specifier (e.g., ">=1.24,<2.0").

        Returns:
            True if version satisfies spec, False otherwise.
        """
        try:
            from packaging.specifiers import SpecifierSet
            from packaging.version import Version

            specifier = SpecifierSet(spec)
            return Version(installed) in specifier
        except ImportError:
            # packaging not available, skip version check
            logger.debug(
                "packaging module not available, skipping version validation"
            )
            return True
        except Exception as e:
            logger.debug("Version check failed: %s", e)
            return True  # Assume OK if we can't check

    def check_python_version(self) -> bool:
        """
        Check if current Python version satisfies requires-python.

        Returns:
            True if compatible, False otherwise.
        """
        required = self.get_python_requires()
        if not required:
            return True

        try:
            from packaging.specifiers import SpecifierSet
            from packaging.version import Version

            current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            specifier = SpecifierSet(required)
            return Version(current) in specifier
        except ImportError:
            return True
        except Exception as e:
            logger.debug("Python version check failed: %s", e)
            return True

    def get_install_command(
        self,
        extras: list[str] | None = None,
        use_pip: bool = True,
    ) -> str:
        """
        Generate the command to install dependencies.

        Args:
            extras: Optional list of extras to install.
            use_pip: If True, use pip. If False, use uv.

        Returns:
            Install command string.
        """
        base_cmd = "pip install" if use_pip else "uv pip install"

        if self.has_pyproject():
            # Install from pyproject.toml
            extra_str = ""
            if extras:
                extra_str = "[" + ",".join(extras) + "]"
            return f"{base_cmd} -e .{extra_str}"

        return f"{base_cmd} -r requirements.txt"


def validate_endpoint_dependencies(
    endpoint_path: Path,
    endpoint_name: str,
    extras: list[str] | None = None,
) -> bool:
    """
    Validate dependencies for an endpoint and log warnings.

    Args:
        endpoint_path: Path to the endpoint folder.
        endpoint_name: Name for logging.
        extras: Optional list of extras to validate.

    Returns:
        True if all dependencies are satisfied, False otherwise.
    """
    manager = RequirementsManager(endpoint_path)

    if not manager.has_pyproject():
        return True  # No dependencies declared

    # Check Python version
    if not manager.check_python_version():
        required = manager.get_python_requires()
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        logger.warning(
            "Endpoint '%s' requires Python %s but current is %s",
            endpoint_name,
            required,
            current,
        )

    # Check dependencies
    missing, mismatches = manager.validate_installed(extras)

    if missing:
        logger.warning(
            "Endpoint '%s' has missing dependencies: %s. "
            "Install with: cd %s && %s",
            endpoint_name,
            missing,
            endpoint_path,
            manager.get_install_command(extras),
        )

    if mismatches:
        logger.warning(
            "Endpoint '%s' has version mismatches: %s",
            endpoint_name,
            mismatches,
        )

    return not missing and not mismatches
