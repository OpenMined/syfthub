"""
Virtual environment manager for isolated endpoint execution.

This module provides utilities for creating, managing, and using
virtual environments for endpoint isolation in subprocess mode.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import venv
from pathlib import Path

logger = logging.getLogger(__name__)

# Virtual environment folder name within endpoint directory
VENV_FOLDER = ".venv"
REQUIREMENTS_HASH_FILE = ".requirements.hash"


class VenvManager:
    """
    Manages virtual environments for endpoint isolation.

    Creates and maintains per-endpoint virtual environments,
    handling dependency installation and change detection.

    Example usage:
        manager = VenvManager(endpoint_path)

        if await manager.needs_rebuild("abc123"):
            await manager.create_or_update("abc123")

        python_exe = manager.get_python_executable()
        env = manager.get_subprocess_env()
    """

    def __init__(
        self,
        endpoint_path: Path,
        venv_folder: str = VENV_FOLDER,
    ) -> None:
        """
        Initialize the virtual environment manager.

        Args:
            endpoint_path: Path to the endpoint folder.
            venv_folder: Name of the venv folder (default: ".venv").
        """
        self.endpoint_path = endpoint_path
        self.venv_path = endpoint_path / venv_folder
        self.hash_file = self.venv_path / REQUIREMENTS_HASH_FILE

    @property
    def exists(self) -> bool:
        """Check if the virtual environment exists."""
        python_exe = self._get_python_path()
        return python_exe.exists()

    def _get_python_path(self) -> Path:
        """Get the path to the Python executable in the venv."""
        if sys.platform == "win32":
            return self.venv_path / "Scripts" / "python.exe"
        return self.venv_path / "bin" / "python"

    def _get_pip_path(self) -> Path:
        """Get the path to pip in the venv."""
        if sys.platform == "win32":
            return self.venv_path / "Scripts" / "pip.exe"
        return self.venv_path / "bin" / "pip"

    def get_python_executable(self) -> Path:
        """
        Get the Python executable path for subprocess execution.

        Returns:
            Path to the venv Python executable.

        Raises:
            FileNotFoundError: If venv doesn't exist.
        """
        python_path = self._get_python_path()
        if not python_path.exists():
            raise FileNotFoundError(
                f"Virtual environment not found at {self.venv_path}. "
                "Call create_or_update() first."
            )
        return python_path

    def get_stored_hash(self) -> str | None:
        """
        Get the stored requirements hash from the venv.

        Returns:
            The stored hash, or None if not found.
        """
        if not self.hash_file.exists():
            return None
        try:
            return self.hash_file.read_text().strip()
        except Exception:
            return None

    def needs_rebuild(self, current_hash: str) -> bool:
        """
        Check if the venv needs to be rebuilt.

        Args:
            current_hash: Hash of current pyproject.toml.

        Returns:
            True if venv needs rebuild, False otherwise.
        """
        if not current_hash:
            # No dependencies declared, no venv needed
            return False

        if not self.exists:
            return True

        stored_hash = self.get_stored_hash()
        if stored_hash is None:
            return True

        return stored_hash != current_hash

    async def create_or_update(
        self,
        requirements_hash: str,
        extras: list[str] | None = None,
    ) -> None:
        """
        Create or update the virtual environment.

        If the venv doesn't exist, creates it. If it exists but
        the hash differs, reinstalls dependencies.

        Args:
            requirements_hash: Hash to store after installation.
            extras: Optional list of extras to install.
        """
        if not self.exists:
            logger.info(
                "Creating virtual environment at %s",
                self.venv_path,
            )
            await self._create_venv()

        # Install dependencies
        await self._install_dependencies(extras)

        # Store the hash
        self._store_hash(requirements_hash)

        logger.info(
            "Virtual environment ready at %s (hash: %s)",
            self.venv_path,
            requirements_hash[:8],
        )

    async def _create_venv(self) -> None:
        """Create a new virtual environment."""
        # Use venv module to create the environment
        # Run in thread to not block event loop
        await asyncio.to_thread(
            venv.create,
            self.venv_path,
            with_pip=True,
            clear=True,  # Remove existing if any
        )

    async def _install_dependencies(
        self,
        extras: list[str] | None = None,
    ) -> None:
        """
        Install dependencies from pyproject.toml.

        Args:
            extras: Optional list of extras to install.
        """
        pyproject = self.endpoint_path / "pyproject.toml"
        if not pyproject.exists():
            logger.debug("No pyproject.toml found, skipping dependency installation")
            return

        pip_path = self._get_pip_path()

        # Build the install command
        # Install the endpoint package with its dependencies
        install_target = str(self.endpoint_path)
        if extras:
            install_target += "[" + ",".join(extras) + "]"

        cmd = [
            str(pip_path),
            "install",
            "--upgrade",
            "-e",
            install_target,
        ]

        logger.debug("Installing dependencies: %s", " ".join(cmd))

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.endpoint_path),
            )

            if result.returncode != 0:
                logger.error(
                    "Failed to install dependencies:\nstdout: %s\nstderr: %s",
                    result.stdout,
                    result.stderr,
                )
                raise RuntimeError(
                    f"Dependency installation failed: {result.stderr}"
                )

            logger.debug("Dependencies installed successfully")

        except Exception as e:
            logger.error("Error installing dependencies: %s", e)
            raise

    def _store_hash(self, hash_value: str) -> None:
        """Store the requirements hash in the venv."""
        self.hash_file.parent.mkdir(parents=True, exist_ok=True)
        self.hash_file.write_text(hash_value)

    def get_subprocess_env(
        self,
        endpoint_env: dict[str, str] | None = None,
        inherit_vars: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Build environment variables for subprocess execution.

        Creates an isolated environment with:
        - VIRTUAL_ENV pointing to the venv
        - PATH with venv bin prepended
        - Endpoint-specific environment variables
        - Optionally inherited variables from parent

        Args:
            endpoint_env: Endpoint-specific environment variables.
            inherit_vars: Variables to inherit from parent (default: PATH, HOME).

        Returns:
            Environment dictionary for subprocess.
        """
        if inherit_vars is None:
            # Minimal required variables
            inherit_vars = ["PATH", "HOME", "LANG", "LC_ALL"]

        env: dict[str, str] = {}

        # Copy inherited variables from current environment
        for var in inherit_vars:
            value = os.environ.get(var)
            if value:
                env[var] = value

        # Set VIRTUAL_ENV
        env["VIRTUAL_ENV"] = str(self.venv_path)

        # Prepend venv bin to PATH
        venv_bin = str(self.venv_path / "bin")
        if "PATH" in env:
            env["PATH"] = f"{venv_bin}:{env['PATH']}"
        else:
            env["PATH"] = venv_bin

        # Add PYTHONPATH for local imports
        env["PYTHONPATH"] = str(self.endpoint_path)

        # Prevent inheriting __pycache__ from parent
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        # Add endpoint-specific environment variables (take precedence)
        if endpoint_env:
            env.update(endpoint_env)

        return env

    async def cleanup(self) -> None:
        """Remove the virtual environment."""
        if self.venv_path.exists():
            import shutil

            await asyncio.to_thread(shutil.rmtree, self.venv_path)
            logger.info("Removed virtual environment at %s", self.venv_path)


async def ensure_venv_ready(
    endpoint_path: Path,
    requirements_hash: str,
    extras: list[str] | None = None,
) -> VenvManager:
    """
    Ensure a virtual environment is ready for an endpoint.

    Creates or updates the venv if needed.

    Args:
        endpoint_path: Path to the endpoint folder.
        requirements_hash: Hash of pyproject.toml for change detection.
        extras: Optional list of extras to install.

    Returns:
        Ready VenvManager instance.
    """
    manager = VenvManager(endpoint_path)

    if manager.needs_rebuild(requirements_hash):
        await manager.create_or_update(requirements_hash, extras)

    return manager
