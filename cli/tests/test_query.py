"""Tests for query command."""

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
def mock_complete_response() -> MagicMock:
    """Create a mock complete response."""
    response = MagicMock()
    response.response = "This is the AI response to your query."
    response.sources = {}
    response.retrieval_info = []
    response.usage = MagicMock()
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    response.usage.total_tokens = 150
    return response


@pytest.fixture
def mock_stream_events() -> list[MagicMock]:
    """Create mock streaming events."""
    from syfthub_sdk import (
        DoneEvent,
        GenerationStartEvent,
        RetrievalCompleteEvent,
        RetrievalStartEvent,
        TokenEvent,
    )

    return [
        RetrievalStartEvent(),
        RetrievalCompleteEvent(total_documents=5),
        GenerationStartEvent(),
        TokenEvent(content="Hello "),
        TokenEvent(content="world!"),
        DoneEvent(),
    ]


class TestQueryCommand:
    """Tests for the query command."""

    def test_query_complete_json(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_complete_response: MagicMock,
    ) -> None:
        """Test query with JSON output (non-streaming)."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.complete.return_value = mock_complete_response

            result = runner.invoke(
                app, ["query", "alice/gpt4", "What is machine learning?", "--json"]
            )

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"response"' in result.stdout
        assert "This is the AI response" in result.stdout

    def test_query_streaming(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query with streaming output."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(
                app, ["query", "alice/gpt4", "What is machine learning?"]
            )

        assert result.exit_code == 0
        # Should contain the streamed tokens
        assert "Hello " in result.stdout or "world!" in result.stdout

    def test_query_with_sources(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query with data sources."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(
                app,
                [
                    "query",
                    "alice/gpt4",
                    "--source",
                    "bob/docs",
                    "--source",
                    "carol/data",
                    "What is ML?",
                ],
            )

        assert result.exit_code == 0
        # Verify stream was called with sources
        mock_client.chat.stream.assert_called_once()
        call_kwargs = mock_client.chat.stream.call_args[1]
        assert call_kwargs["data_sources"] == ["bob/docs", "carol/data"]

    def test_query_with_aggregator_alias(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query with aggregator alias."""
        # Set up config with aggregator
        from syfthub_cli.config import AggregatorConfig, SyftConfig, save_config

        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(app, ["query", "alice/gpt4", "-a", "local", "Hello"])

        assert result.exit_code == 0
        # Verify client was created with aggregator URL
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs["aggregator_url"] == "http://localhost:8001"

    def test_query_with_options(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query with various options."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(
                app,
                [
                    "query",
                    "alice/gpt4",
                    "--top-k",
                    "10",
                    "--max-tokens",
                    "2048",
                    "--temperature",
                    "0.5",
                    "Hello",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = mock_client.chat.stream.call_args[1]
        assert call_kwargs["top_k"] == 10
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["temperature"] == 0.5

    def test_query_verbose_mode(
        self,
        runner: CliRunner,
        mock_config: Path,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query with verbose mode showing retrieval progress."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(app, ["query", "alice/gpt4", "--verbose", "Hello"])

        assert result.exit_code == 0
        # Verbose mode should show retrieval info
        assert "Retriev" in result.stdout or "document" in result.stdout

    def test_query_error_handling(self, runner: CliRunner, mock_config: Path) -> None:
        """Test query error handling."""
        from syfthub_sdk import ChatError

        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.side_effect = ChatError("Model not found")

            result = runner.invoke(app, ["query", "alice/gpt4", "Hello"])

        assert result.exit_code == 1
        assert "Model not found" in result.output or "Error" in result.output

    def test_query_error_json_output(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test query error with JSON output."""
        from syfthub_sdk import ChatError

        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.complete.side_effect = ChatError("Error message")

            result = runner.invoke(app, ["query", "alice/gpt4", "Hello", "--json"])

        assert result.exit_code == 1
        assert '"status": "error"' in result.stdout

    def test_query_with_authenticated_config(
        self,
        runner: CliRunner,
        authenticated_config: MagicMock,
        mock_stream_events: list[MagicMock],
    ) -> None:
        """Test query uses authentication tokens from config."""
        with patch("syfthub_cli.commands.query.SyftHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.chat.stream.return_value = iter(mock_stream_events)

            result = runner.invoke(app, ["query", "alice/gpt4", "Hello"])

        assert result.exit_code == 0
        # Verify set_tokens was called
        mock_client.set_tokens.assert_called_once()
