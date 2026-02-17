"""Tests for utility commands (whoami, completion)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from syfthub_cli.config import SyftConfig
from syfthub_cli.main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestWhoamiCommand:
    """Tests for the whoami command."""

    def test_whoami_not_logged_in(self, runner: CliRunner, mock_config: Path) -> None:
        """Test whoami when not logged in."""
        result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 1
        assert "Not logged in" in result.output

    def test_whoami_not_logged_in_json(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test whoami when not logged in with JSON output."""
        result = runner.invoke(app, ["whoami", "--json"])

        assert result.exit_code == 1
        assert '"status": "error"' in result.stdout
        assert "Not logged in" in result.stdout

    def test_whoami_success(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test whoami with valid authentication."""
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"

        with patch("syfthub_cli.commands.utils.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.me.return_value = mock_user

            result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 0
        assert "testuser" in result.stdout
        assert "test@example.com" in result.stdout

    def test_whoami_json_output(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test whoami with JSON output."""
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"

        with patch("syfthub_cli.commands.utils.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.me.return_value = mock_user

            result = runner.invoke(app, ["whoami", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"username": "testuser"' in result.stdout

    def test_whoami_api_error(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test whoami when API call fails."""
        with patch("syfthub_cli.commands.utils.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.me.side_effect = Exception("Token expired")

            result = runner.invoke(app, ["whoami"])

        assert result.exit_code == 1
        assert (
            "Failed to get user info" in result.output
            or "Token expired" in result.output
        )


class TestCompletionCommands:
    """Tests for completion commands."""

    def test_completion_bash(self, runner: CliRunner) -> None:
        """Test generating bash completion script."""
        result = runner.invoke(app, ["completion", "bash"])

        assert result.exit_code == 0
        assert "_syft_completion" in result.stdout
        assert "complete" in result.stdout
        assert "COMP_WORDS" in result.stdout

    def test_completion_zsh(self, runner: CliRunner) -> None:
        """Test generating zsh completion script."""
        result = runner.invoke(app, ["completion", "zsh"])

        assert result.exit_code == 0
        assert "#compdef syft" in result.stdout
        assert "_syft" in result.stdout

    def test_completion_fish(self, runner: CliRunner) -> None:
        """Test generating fish completion script."""
        result = runner.invoke(app, ["completion", "fish"])

        assert result.exit_code == 0
        assert "_syft_completion" in result.stdout
        assert "complete -c syft" in result.stdout

    def test_completion_install_bash(self, runner: CliRunner) -> None:
        """Test completion install instructions for bash."""
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = runner.invoke(app, ["completion", "install", "bash"])

        assert result.exit_code == 0
        assert "Bash" in result.stdout
        assert ".bashrc" in result.stdout

    def test_completion_install_zsh(self, runner: CliRunner) -> None:
        """Test completion install instructions for zsh."""
        result = runner.invoke(app, ["completion", "install", "zsh"])

        assert result.exit_code == 0
        assert "Zsh" in result.stdout
        assert ".zshrc" in result.stdout

    def test_completion_install_fish(self, runner: CliRunner) -> None:
        """Test completion install instructions for fish."""
        result = runner.invoke(app, ["completion", "install", "fish"])

        assert result.exit_code == 0
        assert "Fish" in result.stdout
        assert "completions" in result.stdout

    def test_completion_install_auto_detect_bash(self, runner: CliRunner) -> None:
        """Test auto-detecting bash shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            result = runner.invoke(app, ["completion", "install"])

        assert result.exit_code == 0
        assert "Bash" in result.stdout

    def test_completion_install_auto_detect_zsh(self, runner: CliRunner) -> None:
        """Test auto-detecting zsh shell."""
        with patch.dict("os.environ", {"SHELL": "/usr/bin/zsh"}):
            result = runner.invoke(app, ["completion", "install"])

        assert result.exit_code == 0
        assert "Zsh" in result.stdout

    def test_completion_install_unknown_shell(self, runner: CliRunner) -> None:
        """Test completion install with unknown shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/unknown"}):
            result = runner.invoke(app, ["completion", "install"])

        assert result.exit_code == 1
        assert "Could not detect shell" in result.output

    def test_completion_install_invalid_shell(self, runner: CliRunner) -> None:
        """Test completion install with invalid shell argument."""
        result = runner.invoke(app, ["completion", "install", "powershell"])

        assert result.exit_code == 1
        assert "Unknown shell" in result.output
