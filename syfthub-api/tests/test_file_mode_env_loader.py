"""Tests for the file_mode env_loader module."""

import pytest
from pathlib import Path
import tempfile
import os

from syfthub_api.file_mode.env_loader import (
    load_endpoint_env,
    validate_required_env,
    merge_env_with_inheritance,
)


class TestLoadEndpointEnv:
    """Tests for load_endpoint_env function."""

    def test_load_existing_env_file(self, tmp_path: Path) -> None:
        """Test loading variables from an existing .env file."""
        env_content = """
API_KEY=test-key-123
MODEL_NAME=gpt-4
DEBUG=true
"""
        (tmp_path / ".env").write_text(env_content)

        env = load_endpoint_env(tmp_path)

        assert env["API_KEY"] == "test-key-123"
        assert env["MODEL_NAME"] == "gpt-4"
        assert env["DEBUG"] == "true"
        assert len(env) == 3

    def test_load_missing_env_file(self, tmp_path: Path) -> None:
        """Test loading returns empty dict when no .env file exists."""
        env = load_endpoint_env(tmp_path)

        assert env == {}

    def test_load_empty_env_file(self, tmp_path: Path) -> None:
        """Test loading an empty .env file."""
        (tmp_path / ".env").write_text("")

        env = load_endpoint_env(tmp_path)

        assert env == {}

    def test_load_env_with_comments(self, tmp_path: Path) -> None:
        """Test that comments are ignored in .env file."""
        env_content = """
# This is a comment
API_KEY=secret
# Another comment
DEBUG=true
"""
        (tmp_path / ".env").write_text(env_content)

        env = load_endpoint_env(tmp_path)

        assert env == {"API_KEY": "secret", "DEBUG": "true"}

    def test_load_env_with_quotes(self, tmp_path: Path) -> None:
        """Test loading values with quotes."""
        env_content = '''
QUOTED="value with spaces"
SINGLE='another value'
UNQUOTED=no_spaces
'''
        (tmp_path / ".env").write_text(env_content)

        env = load_endpoint_env(tmp_path)

        assert env["QUOTED"] == "value with spaces"
        assert env["SINGLE"] == "another value"
        assert env["UNQUOTED"] == "no_spaces"

    def test_custom_env_file_name(self, tmp_path: Path) -> None:
        """Test loading from a custom-named env file."""
        (tmp_path / ".env.local").write_text("LOCAL_VAR=value")

        env = load_endpoint_env(tmp_path, env_file_name=".env.local")

        assert env == {"LOCAL_VAR": "value"}


class TestValidateRequiredEnv:
    """Tests for validate_required_env function."""

    def test_all_required_present(self) -> None:
        """Test validation passes when all required vars are present."""
        env = {"API_KEY": "xxx", "SECRET": "yyy"}
        missing = validate_required_env(env, ["API_KEY", "SECRET"], "test-endpoint")

        assert missing == []

    def test_missing_required_vars(self) -> None:
        """Test validation returns missing var names."""
        env = {"API_KEY": "xxx"}
        missing = validate_required_env(
            env, ["API_KEY", "SECRET", "TOKEN"], "test-endpoint"
        )

        assert missing == ["SECRET", "TOKEN"]

    def test_empty_required_list(self) -> None:
        """Test validation with no required vars."""
        env = {"SOME_VAR": "value"}
        missing = validate_required_env(env, [], "test-endpoint")

        assert missing == []

    def test_empty_env_with_requirements(self) -> None:
        """Test validation with empty env but requirements."""
        missing = validate_required_env({}, ["REQUIRED"], "test-endpoint")

        assert missing == ["REQUIRED"]


class TestMergeEnvWithInheritance:
    """Tests for merge_env_with_inheritance function."""

    def test_merge_with_parent_env(self) -> None:
        """Test merging endpoint env with parent vars."""
        endpoint_env = {"MY_VAR": "endpoint_value"}
        parent_env = {"PATH": "/usr/bin", "HOME": "/root", "OTHER": "x"}

        merged = merge_env_with_inheritance(
            endpoint_env=endpoint_env,
            inherit_vars=["PATH", "HOME"],
            parent_env=parent_env,
        )

        assert merged["MY_VAR"] == "endpoint_value"
        assert merged["PATH"] == "/usr/bin"
        assert merged["HOME"] == "/root"
        assert "OTHER" not in merged  # Not in inherit list

    def test_endpoint_env_overrides_inherited(self) -> None:
        """Test that endpoint vars take precedence over inherited."""
        endpoint_env = {"PATH": "/custom/path"}
        parent_env = {"PATH": "/usr/bin"}

        merged = merge_env_with_inheritance(
            endpoint_env=endpoint_env,
            inherit_vars=["PATH"],
            parent_env=parent_env,
        )

        assert merged["PATH"] == "/custom/path"

    def test_inherit_missing_var(self) -> None:
        """Test inheriting a var that doesn't exist in parent."""
        endpoint_env = {}
        parent_env = {"PATH": "/usr/bin"}

        merged = merge_env_with_inheritance(
            endpoint_env=endpoint_env,
            inherit_vars=["PATH", "NONEXISTENT"],
            parent_env=parent_env,
        )

        assert merged["PATH"] == "/usr/bin"
        assert "NONEXISTENT" not in merged

    def test_inherit_from_os_environ_by_default(self) -> None:
        """Test inheriting from os.environ when parent_env is None."""
        # Set a test variable in os.environ
        test_var = "_TEST_INHERIT_VAR_12345"
        os.environ[test_var] = "test_value"

        try:
            merged = merge_env_with_inheritance(
                endpoint_env={},
                inherit_vars=[test_var],
                parent_env=None,  # Should use os.environ
            )

            assert merged[test_var] == "test_value"
        finally:
            del os.environ[test_var]

    def test_empty_inherit_list(self) -> None:
        """Test with empty inherit list."""
        endpoint_env = {"MY_VAR": "value"}
        parent_env = {"PATH": "/usr/bin"}

        merged = merge_env_with_inheritance(
            endpoint_env=endpoint_env,
            inherit_vars=[],
            parent_env=parent_env,
        )

        assert merged == {"MY_VAR": "value"}
        assert "PATH" not in merged
