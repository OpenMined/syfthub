"""Tests for shell completion functions."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from syfthub_cli.completion import (
    CACHE_TTL,
    _fetch_and_cache_endpoints,
    _get_cached_endpoints,
    complete_accounting_alias,
    complete_aggregator_alias,
    complete_config_key,
    complete_data_source,
    complete_ls_target,
    complete_model_endpoint,
)

if TYPE_CHECKING:
    from typing import Any


@pytest.fixture
def mock_endpoints_data() -> list[dict[str, Any]]:
    """Create mock endpoint data."""
    return [
        {
            "owner": "alice",
            "name": "gpt4-model",
            "type": "model",
            "description": "GPT-4",
        },
        {
            "owner": "alice",
            "name": "my-data",
            "type": "data_source",
            "description": "Data",
        },
        {
            "owner": "bob",
            "name": "llama",
            "type": "model",
            "description": "LLaMA model",
        },
        {
            "owner": "bob",
            "name": "docs",
            "type": "data_source",
            "description": "Documents",
        },
        {
            "owner": "carol",
            "name": "hybrid",
            "type": "model_data_source",
            "description": "Hybrid",
        },
    ]


@pytest.fixture
def mock_cache_file(tmp_path: Path, mock_endpoints_data: list[dict]) -> Path:
    """Create a mock cache file."""
    cache_dir = tmp_path / ".syfthub"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / ".completion_cache.json"
    cache_file.write_text(
        json.dumps({"endpoints": mock_endpoints_data, "timestamp": time.time()})
    )
    return cache_file


class TestCacheOperations:
    """Tests for cache read/write operations."""

    def test_get_cached_endpoints_no_file(self, tmp_path: Path) -> None:
        """Test getting cached endpoints when no cache file exists."""
        with patch("syfthub_cli.completion.CACHE_FILE", tmp_path / "nonexistent.json"):
            result = _get_cached_endpoints()
        assert result is None

    def test_get_cached_endpoints_valid(
        self, mock_cache_file: Path, mock_endpoints_data: list[dict]
    ) -> None:
        """Test getting cached endpoints with valid cache."""
        with patch("syfthub_cli.completion.CACHE_FILE", mock_cache_file):
            result = _get_cached_endpoints()
        assert result is not None
        assert len(result) == len(mock_endpoints_data)

    def test_get_cached_endpoints_expired(self, tmp_path: Path) -> None:
        """Test getting cached endpoints when cache is expired."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(
            json.dumps(
                {
                    "endpoints": [
                        {
                            "owner": "old",
                            "name": "data",
                            "type": "model",
                            "description": "",
                        }
                    ],
                    "timestamp": time.time() - CACHE_TTL - 100,  # Expired
                }
            )
        )
        with patch("syfthub_cli.completion.CACHE_FILE", cache_file):
            result = _get_cached_endpoints()
        assert result is None

    def test_get_cached_endpoints_corrupted(self, tmp_path: Path) -> None:
        """Test getting cached endpoints when file is corrupted."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not valid json {{{")
        with patch("syfthub_cli.completion.CACHE_FILE", cache_file):
            result = _get_cached_endpoints()
        assert result is None

    def test_fetch_and_cache_endpoints(self, tmp_path: Path) -> None:
        """Test fetching and caching endpoints from API."""
        cache_file = tmp_path / ".syfthub" / ".completion_cache.json"

        mock_endpoint = MagicMock()
        mock_endpoint.owner_username = "alice"
        mock_endpoint.name = "model"
        mock_endpoint.type = MagicMock()
        mock_endpoint.type.value = "model"
        mock_endpoint.description = "Test"

        with (
            patch("syfthub_cli.completion.CACHE_FILE", cache_file),
            patch("syfthub_cli.completion.CONFIG_DIR", tmp_path / ".syfthub"),
            patch("syfthub_sdk.SyftHubClient") as mock_client_class,
        ):
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.hub.browse.return_value = iter([mock_endpoint])

            result = _fetch_and_cache_endpoints()

        assert len(result) == 1
        assert result[0]["owner"] == "alice"
        assert cache_file.exists()


class TestCompleteLsTarget:
    """Tests for ls target completion."""

    def test_complete_usernames(self, mock_endpoints_data: list[dict]) -> None:
        """Test completing usernames."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_ls_target(None, "a")

        # Should match "alice"
        assert len(result) >= 1
        user_names = [r[0] for r in result]
        assert any("alice" in name for name in user_names)

    def test_complete_usernames_empty_prefix(
        self, mock_endpoints_data: list[dict]
    ) -> None:
        """Test completing usernames with empty prefix."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_ls_target(None, "")

        # Should return all unique users
        user_names = [r[0] for r in result]
        assert len(user_names) == 3  # alice, bob, carol

    def test_complete_endpoints(self, mock_endpoints_data: list[dict]) -> None:
        """Test completing endpoints for a user."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_ls_target(None, "alice/")

        # Should return alice's endpoints
        assert len(result) == 2
        paths = [r[0] for r in result]
        assert "alice/gpt4-model" in paths
        assert "alice/my-data" in paths

    def test_complete_endpoints_partial(self, mock_endpoints_data: list[dict]) -> None:
        """Test completing endpoints with partial name."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_ls_target(None, "alice/gpt")

        # Should return only matching endpoint
        assert len(result) == 1
        assert result[0][0] == "alice/gpt4-model"


class TestCompleteModelEndpoint:
    """Tests for model endpoint completion."""

    def test_complete_model_endpoints(self, mock_endpoints_data: list[dict]) -> None:
        """Test completing only model endpoints."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_model_endpoint(None, "")

        # Should only return model type endpoints
        assert len(result) == 2  # alice/gpt4-model, bob/llama
        paths = [r[0] for r in result]
        assert "alice/gpt4-model" in paths
        assert "bob/llama" in paths
        assert "alice/my-data" not in paths

    def test_complete_model_endpoints_filtered(
        self, mock_endpoints_data: list[dict]
    ) -> None:
        """Test completing model endpoints with filter."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_model_endpoint(None, "alice")

        # Should only return alice's model
        assert len(result) == 1
        assert result[0][0] == "alice/gpt4-model"


class TestCompleteDataSource:
    """Tests for data source completion."""

    def test_complete_data_sources(self, mock_endpoints_data: list[dict]) -> None:
        """Test completing data source endpoints."""
        with patch(
            "syfthub_cli.completion._get_endpoints", return_value=mock_endpoints_data
        ):
            result = complete_data_source(None, "")

        # Should return data_source and model_data_source types
        paths = [r[0] for r in result]
        assert "alice/my-data" in paths
        assert "bob/docs" in paths
        assert "carol/hybrid" in paths
        assert "alice/gpt4-model" not in paths


class TestCompleteAggregatorAlias:
    """Tests for aggregator alias completion."""

    def test_complete_aggregator_aliases(self, mock_config: Path) -> None:
        """Test completing aggregator aliases."""
        from syfthub_cli.config import AggregatorConfig, SyftConfig, save_config

        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
                "production": AggregatorConfig(url="https://prod.example.com"),
            }
        )
        save_config(config)

        result = complete_aggregator_alias(None, "")

        assert len(result) == 2
        aliases = [r[0] for r in result]
        assert "local" in aliases
        assert "production" in aliases

    def test_complete_aggregator_aliases_filtered(self, mock_config: Path) -> None:
        """Test completing aggregator aliases with filter."""
        from syfthub_cli.config import AggregatorConfig, SyftConfig, save_config

        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
                "production": AggregatorConfig(url="https://prod.example.com"),
            }
        )
        save_config(config)

        result = complete_aggregator_alias(None, "lo")

        assert len(result) == 1
        assert result[0][0] == "local"


class TestCompleteAccountingAlias:
    """Tests for accounting alias completion."""

    def test_complete_accounting_aliases(self, mock_config: Path) -> None:
        """Test completing accounting aliases."""
        from syfthub_cli.config import AccountingConfig, SyftConfig, save_config

        config = SyftConfig(
            accounting_services={
                "main": AccountingConfig(url="http://localhost:8002"),
                "backup": AccountingConfig(url="http://backup:8002"),
            }
        )
        save_config(config)

        result = complete_accounting_alias(None, "")

        assert len(result) == 2


class TestCompleteConfigKey:
    """Tests for config key completion."""

    def test_complete_config_keys(self) -> None:
        """Test completing configuration keys."""
        result = complete_config_key(None, "")

        # Should return all allowed keys
        keys = [r[0] for r in result]
        assert "default_aggregator" in keys
        assert "default_accounting" in keys
        assert "timeout" in keys
        assert "hub_url" in keys

    def test_complete_config_keys_filtered(self) -> None:
        """Test completing configuration keys with filter."""
        result = complete_config_key(None, "default")

        # Should return only default_* keys
        keys = [r[0] for r in result]
        assert len(keys) == 2
        assert all("default" in k for k in keys)

    def test_complete_config_keys_single_match(self) -> None:
        """Test completing configuration keys with single match."""
        result = complete_config_key(None, "time")

        assert len(result) == 1
        assert result[0][0] == "timeout"
