"""Tests for authentication commands."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from syfthub_cli.config import SyftConfig, load_config
from syfthub_cli.main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestLoginCommand:
    """Tests for the login command."""

    def test_login_success(self, runner: CliRunner, mock_config: Path) -> None:
        """Test successful login."""
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"

        mock_tokens = MagicMock()
        mock_tokens.access_token = "new_access_token"
        mock_tokens.refresh_token = "new_refresh_token"

        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.login.return_value = mock_user
            mock_client.get_tokens.return_value = mock_tokens

            result = runner.invoke(
                app, ["login", "-u", "testuser", "-p", "password123"]
            )

        assert result.exit_code == 0
        assert "Logged in as testuser" in result.stdout

        # Verify tokens were saved
        config = load_config()
        assert config.access_token == "new_access_token"
        assert config.refresh_token == "new_refresh_token"

    def test_login_failure(self, runner: CliRunner, mock_config: Path) -> None:
        """Test login with invalid credentials."""
        from syfthub_sdk import AuthenticationError

        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.login.side_effect = AuthenticationError("Invalid credentials")

            result = runner.invoke(
                app, ["login", "-u", "testuser", "-p", "wrongpassword"]
            )

        assert result.exit_code == 1
        assert "Authentication failed" in result.output

    def test_login_json_output(self, runner: CliRunner, mock_config: Path) -> None:
        """Test login with JSON output."""
        mock_user = MagicMock()
        mock_user.username = "testuser"
        mock_user.email = "test@example.com"

        mock_tokens = MagicMock()
        mock_tokens.access_token = "token"
        mock_tokens.refresh_token = "refresh"

        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.login.return_value = mock_user
            mock_client.get_tokens.return_value = mock_tokens

            result = runner.invoke(
                app, ["login", "-u", "testuser", "-p", "password", "--json"]
            )

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"username": "testuser"' in result.stdout

    def test_login_json_output_failure(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test login failure with JSON output."""
        from syfthub_sdk import AuthenticationError

        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.login.side_effect = AuthenticationError("Invalid credentials")

            result = runner.invoke(
                app, ["login", "-u", "testuser", "-p", "wrong", "--json"]
            )

        assert result.exit_code == 1
        assert '"status": "error"' in result.stdout


class TestLogoutCommand:
    """Tests for the logout command."""

    def test_logout_success(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test successful logout."""
        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["logout"])

        assert result.exit_code == 0
        assert "Logged out successfully" in result.stdout

        # Verify tokens were cleared
        config = load_config()
        assert config.access_token is None
        assert config.refresh_token is None

    def test_logout_when_not_logged_in(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test logout when already logged out."""
        result = runner.invoke(app, ["logout"])

        assert result.exit_code == 0
        assert "Already logged out" in result.stdout

    def test_logout_json_output(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test logout with JSON output."""
        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

            result = runner.invoke(app, ["logout", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"message": "Logged out"' in result.stdout

    def test_logout_server_error_still_clears_local(
        self, runner: CliRunner, authenticated_config: SyftConfig
    ) -> None:
        """Test that logout clears local tokens even if server logout fails."""
        with patch("syfthub_cli.commands.auth.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__ = MagicMock(
                return_value=mock_client
            )
            mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.logout.side_effect = Exception("Server error")

            result = runner.invoke(app, ["logout"])

        assert result.exit_code == 0
        # Tokens should still be cleared locally
        config = load_config()
        assert config.access_token is None
