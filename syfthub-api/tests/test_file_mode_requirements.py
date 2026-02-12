"""
Tests for file mode requirements manager and venv manager.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from syfthub_api.file_mode.requirements_manager import (
    RequirementsManager,
    validate_endpoint_dependencies,
)
from syfthub_api.file_mode.venv_manager import VenvManager


class TestRequirementsManager:
    """Tests for RequirementsManager."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> RequirementsManager:
        """Create a RequirementsManager for testing."""
        return RequirementsManager(tmp_path)

    def test_has_pyproject_false(self, manager: RequirementsManager) -> None:
        """Test has_pyproject returns False when no file exists."""
        assert manager.has_pyproject() is False

    def test_has_pyproject_true(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test has_pyproject returns True when file exists."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        assert manager.has_pyproject() is True

    def test_get_dependencies_no_file(self, manager: RequirementsManager) -> None:
        """Test get_dependencies returns empty list when no file."""
        assert manager.get_dependencies() == []

    def test_get_dependencies_empty_deps(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test get_dependencies with no dependencies declared."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
""")
        assert manager.get_dependencies() == []

    def test_get_dependencies_with_deps(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test get_dependencies with dependencies."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = [
    "numpy>=1.20.0",
    "pandas",
]
""")
        deps = manager.get_dependencies()
        assert "numpy>=1.20.0" in deps
        assert "pandas" in deps

    def test_get_dependencies_with_extras(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test get_all_dependencies with extras."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = ["requests"]

[project.optional-dependencies]
dev = ["pytest"]
ml = ["numpy", "pandas"]
""")
        # Without extras
        deps = manager.get_dependencies()
        assert "requests" in deps
        assert "pytest" not in deps

        # With extras using get_all_dependencies
        deps_with_extras = manager.get_all_dependencies(extras=["ml"])
        assert "requests" in deps_with_extras
        assert "numpy" in deps_with_extras
        assert "pandas" in deps_with_extras
        assert "pytest" not in deps_with_extras

    def test_get_requirements_hash(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test get_requirements_hash returns consistent hash."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        hash1 = manager.get_requirements_hash()
        hash2 = manager.get_requirements_hash()
        assert hash1 == hash2
        assert len(hash1) > 0

    def test_get_requirements_hash_no_file(
        self,
        manager: RequirementsManager,
    ) -> None:
        """Test get_requirements_hash returns empty string when no file."""
        assert manager.get_requirements_hash() == ""

    def test_get_requirements_hash_changes(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test get_requirements_hash changes when file changes."""
        (tmp_path / "pyproject.toml").write_text("[project]")
        hash1 = manager.get_requirements_hash()

        (tmp_path / "pyproject.toml").write_text("[project]\nversion = '1.0'")
        hash2 = manager.get_requirements_hash()

        assert hash1 != hash2

    def test_validate_installed_no_deps(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test validate_installed with no dependencies."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
""")
        missing, mismatches = manager.validate_installed()
        assert missing == []
        assert mismatches == []

    def test_validate_installed_with_installed_dep(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test validate_installed with installed dependency."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = ["pydantic"]
""")
        missing, mismatches = manager.validate_installed()
        # pydantic is installed (it's a dependency of this project)
        assert "pydantic" not in missing

    def test_validate_installed_with_missing_dep(
        self,
        tmp_path: Path,
        manager: RequirementsManager,
    ) -> None:
        """Test validate_installed with missing dependency."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = ["nonexistent-package-xyz-123"]
""")
        missing, mismatches = manager.validate_installed()
        assert "nonexistent-package-xyz-123" in missing


class TestValidateEndpointDependencies:
    """Tests for validate_endpoint_dependencies function."""

    def test_no_pyproject(self, tmp_path: Path) -> None:
        """Test with no pyproject.toml file."""
        # Should not raise
        validate_endpoint_dependencies(
            endpoint_path=tmp_path,
            endpoint_name="test",
        )

    def test_with_missing_deps_warns(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that missing deps logs warning."""
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test"
version = "0.1.0"
dependencies = ["nonexistent-package-xyz-123"]
""")

        validate_endpoint_dependencies(
            endpoint_path=tmp_path,
            endpoint_name="test-endpoint",
        )

        assert "test-endpoint" in caplog.text
        assert "nonexistent-package-xyz-123" in caplog.text


class TestVenvManager:
    """Tests for VenvManager."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> VenvManager:
        """Create a VenvManager for testing."""
        return VenvManager(tmp_path)

    def test_init(self, tmp_path: Path, manager: VenvManager) -> None:
        """Test manager initialization."""
        assert manager.endpoint_path == tmp_path
        assert manager.venv_path == tmp_path / ".venv"

    def test_exists_false(self, manager: VenvManager) -> None:
        """Test exists returns False when no venv."""
        assert manager.exists is False

    def test_get_stored_hash_none(self, manager: VenvManager) -> None:
        """Test get_stored_hash returns None when no hash file."""
        assert manager.get_stored_hash() is None

    def test_needs_rebuild_no_hash(self, manager: VenvManager) -> None:
        """Test needs_rebuild returns False when no current hash."""
        assert manager.needs_rebuild("") is False

    def test_needs_rebuild_no_venv(self, manager: VenvManager) -> None:
        """Test needs_rebuild returns True when no venv exists."""
        assert manager.needs_rebuild("abc123") is True

    def test_get_python_executable_not_found(self, manager: VenvManager) -> None:
        """Test get_python_executable raises when no venv."""
        with pytest.raises(FileNotFoundError):
            manager.get_python_executable()

    def test_get_subprocess_env(
        self,
        tmp_path: Path,
        manager: VenvManager,
    ) -> None:
        """Test get_subprocess_env builds correct environment."""
        env = manager.get_subprocess_env(
            endpoint_env={"CUSTOM_VAR": "custom_value"},
        )

        # Should have VIRTUAL_ENV set
        assert "VIRTUAL_ENV" in env
        assert env["VIRTUAL_ENV"] == str(tmp_path / ".venv")

        # Should have venv bin in PATH
        assert "PATH" in env
        assert ".venv/bin" in env["PATH"]

        # Should have PYTHONPATH
        assert "PYTHONPATH" in env
        assert str(tmp_path) in env["PYTHONPATH"]

        # Should have custom env var
        assert env.get("CUSTOM_VAR") == "custom_value"

    def test_get_subprocess_env_custom_override(
        self,
        manager: VenvManager,
    ) -> None:
        """Test that endpoint env overrides inherited vars."""
        env = manager.get_subprocess_env(
            endpoint_env={"PATH": "/custom/path"},
        )
        # Custom PATH should override
        assert env["PATH"] == "/custom/path"


class TestVenvManagerIntegration:
    """Integration tests for VenvManager (creates actual venvs)."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> VenvManager:
        """Create a VenvManager for testing."""
        return VenvManager(tmp_path)

    @pytest.mark.asyncio
    async def test_create_venv(self, manager: VenvManager) -> None:
        """Test creating a virtual environment.

        Note: This test is skipped in CI/container environments where
        ensurepip may not work properly. The venv creation functionality
        is tested manually in development environments.
        """
        import os
        import subprocess

        # Skip in CI or if ensurepip is known to not work
        # (uv-managed Python installations often lack ensurepip)
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            pytest.skip("Skipping venv creation test in CI")

        # Try to create a minimal venv to check if it works
        import tempfile
        import venv

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                venv.create(tmpdir, with_pip=True)
            except subprocess.CalledProcessError:
                pytest.skip("venv creation with pip not supported in this environment")
            except Exception as e:
                pytest.skip(f"venv creation failed: {e}")

        # Create a simple pyproject.toml (no deps to make it fast)
        manager.endpoint_path.mkdir(parents=True, exist_ok=True)
        (manager.endpoint_path / "pyproject.toml").write_text("""
[project]
name = "test-endpoint"
version = "0.1.0"
""")

        await manager.create_or_update(requirements_hash="abc123")

        # Verify venv exists
        assert manager.exists is True
        assert manager.get_python_executable().exists()
        assert manager.get_stored_hash() == "abc123"

    @pytest.mark.asyncio
    async def test_cleanup_venv(self, tmp_path: Path) -> None:
        """Test cleaning up a virtual environment."""
        manager = VenvManager(tmp_path)

        # Create minimal venv structure for cleanup test
        venv_path = tmp_path / ".venv"
        venv_path.mkdir()
        (venv_path / "test.txt").write_text("test")

        await manager.cleanup()

        assert not venv_path.exists()
