"""Tests for discovery commands (ls)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from syfthub_cli.main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_endpoints() -> list[MagicMock]:
    """Create mock endpoint objects."""
    endpoints = []
    for i, (owner, name, ep_type) in enumerate(
        [
            ("alice", "gpt4-model", "model"),
            ("alice", "my-data", "data_source"),
            ("bob", "llama-model", "model"),
            ("bob", "documents", "data_source"),
            ("bob", "hybrid-endpoint", "model_data_source"),
        ]
    ):
        ep = MagicMock()
        ep.owner_username = owner
        ep.name = name
        ep.type = MagicMock()
        ep.type.value = ep_type
        ep.version = "1.0.0"
        ep.stars_count = i * 10
        ep.description = f"Description for {name}"
        ep.readme = f"# README for {name}"
        ep.created_at = None
        ep.updated_at = None
        endpoints.append(ep)
    return endpoints


class TestLsCommand:
    """Tests for the ls command."""

    def test_ls_all_users(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test listing all users."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls"])

        assert result.exit_code == 0
        # Should show user names in grid format
        assert "alice" in result.stdout
        assert "bob" in result.stdout

    def test_ls_user_endpoints(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test listing endpoints for a specific user."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "bob"])

        assert result.exit_code == 0
        assert "bob" in result.stdout
        # Bob's endpoints should be visible
        assert "llama-model" in result.stdout or "documents" in result.stdout

    def test_ls_user_endpoints_case_insensitive(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test that username matching is case-insensitive."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "BOB"])

        assert result.exit_code == 0

    def test_ls_endpoint_detail(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test showing endpoint details."""
        mock_endpoint = mock_endpoints[0]  # alice/gpt4-model

        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.get.return_value = mock_endpoint
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "alice/gpt4-model"])

        assert result.exit_code == 0
        assert "alice/gpt4-model" in result.stdout
        assert "model" in result.stdout

    def test_ls_trailing_slash_normalized(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test that trailing slash is normalized."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            # Should behave same as "ls alice"
            result = runner.invoke(app, ["ls", "alice/"])

        assert result.exit_code == 0

    def test_ls_long_format(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test listing with long format (-l)."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "-l"])

        assert result.exit_code == 0
        # Long format should show table headers
        assert "Username" in result.stdout or "Active Users" in result.stdout

    def test_ls_json_output(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test listing with JSON output."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"users"' in result.stdout

    def test_ls_endpoint_not_found(self, runner: CliRunner, mock_config: Path) -> None:
        """Test ls with non-existent endpoint."""
        from syfthub_sdk import NotFoundError

        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.get.side_effect = NotFoundError("Endpoint not found")
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "alice/nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output

    def test_ls_limit_option(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test listing with limit option."""
        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter(mock_endpoints)
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "-n", "2"])

        assert result.exit_code == 0

    def test_ls_endpoint_detail_json(
        self, runner: CliRunner, mock_config: Path, mock_endpoints: list[MagicMock]
    ) -> None:
        """Test showing endpoint details with JSON output."""
        mock_endpoint = mock_endpoints[0]

        with patch(
            "syfthub_cli.commands.discovery._get_authenticated_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.get.return_value = mock_endpoint
            mock_get_client.return_value = mock_client

            result = runner.invoke(app, ["ls", "alice/gpt4-model", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"endpoint"' in result.stdout
