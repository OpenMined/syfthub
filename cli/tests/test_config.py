"""Tests for configuration management."""

from __future__ import annotations

import json
from pathlib import Path

from syfthub_cli.config import (
    AccountingConfig,
    AggregatorConfig,
    SyftConfig,
    clear_tokens,
    load_config,
    save_config,
    update_config,
)


class TestSyftConfig:
    """Tests for SyftConfig model."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = SyftConfig()
        assert config.access_token is None
        assert config.refresh_token is None
        assert config.aggregators == {}
        assert config.accounting_services == {}
        assert config.default_aggregator is None
        assert config.default_accounting is None
        assert config.timeout == 30.0
        assert config.hub_url == "https://hub.syftbox.org"

    def test_custom_values(self) -> None:
        """Test configuration with custom values."""
        config = SyftConfig(
            access_token="token123",
            refresh_token="refresh456",
            timeout=60.0,
            hub_url="https://custom.example.com",
        )
        assert config.access_token == "token123"
        assert config.refresh_token == "refresh456"
        assert config.timeout == 60.0
        assert config.hub_url == "https://custom.example.com"

    def test_aggregator_config(self) -> None:
        """Test aggregator configuration."""
        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
                "prod": AggregatorConfig(url="https://agg.example.com"),
            },
            default_aggregator="local",
        )
        assert len(config.aggregators) == 2
        assert config.aggregators["local"].url == "http://localhost:8001"
        assert config.default_aggregator == "local"

    def test_accounting_config(self) -> None:
        """Test accounting service configuration."""
        config = SyftConfig(
            accounting_services={
                "main": AccountingConfig(url="http://localhost:8002"),
            },
            default_accounting="main",
        )
        assert len(config.accounting_services) == 1
        assert config.accounting_services["main"].url == "http://localhost:8002"
        assert config.default_accounting == "main"


class TestGetAggregatorUrl:
    """Tests for get_aggregator_url method."""

    def test_get_by_alias(self) -> None:
        """Test getting aggregator URL by alias."""
        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
            }
        )
        assert config.get_aggregator_url("local") == "http://localhost:8001"

    def test_get_default(self) -> None:
        """Test getting default aggregator URL."""
        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
            },
            default_aggregator="local",
        )
        assert config.get_aggregator_url() == "http://localhost:8001"

    def test_direct_url_passthrough(self) -> None:
        """Test that unknown aliases are treated as direct URLs."""
        config = SyftConfig()
        assert config.get_aggregator_url("http://direct.url") == "http://direct.url"

    def test_no_default_returns_none(self) -> None:
        """Test that None is returned when no default is set."""
        config = SyftConfig()
        assert config.get_aggregator_url() is None

    def test_missing_default_alias_returns_none(self) -> None:
        """Test that None is returned when default alias doesn't exist."""
        config = SyftConfig(default_aggregator="nonexistent")
        assert config.get_aggregator_url() is None


class TestGetAccountingUrl:
    """Tests for get_accounting_url method."""

    def test_get_by_alias(self) -> None:
        """Test getting accounting URL by alias."""
        config = SyftConfig(
            accounting_services={
                "main": AccountingConfig(url="http://localhost:8002"),
            }
        )
        assert config.get_accounting_url("main") == "http://localhost:8002"

    def test_get_default(self) -> None:
        """Test getting default accounting URL."""
        config = SyftConfig(
            accounting_services={
                "main": AccountingConfig(url="http://localhost:8002"),
            },
            default_accounting="main",
        )
        assert config.get_accounting_url() == "http://localhost:8002"

    def test_direct_url_passthrough(self) -> None:
        """Test that unknown aliases are treated as direct URLs."""
        config = SyftConfig()
        assert config.get_accounting_url("http://direct.url") == "http://direct.url"


class TestLoadSaveConfig:
    """Tests for load_config and save_config functions."""

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading config when file doesn't exist."""
        config_file = tmp_path / "config.json"
        config = load_config(config_file)
        assert isinstance(config, SyftConfig)
        assert config.access_token is None

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading configuration."""
        config_file = tmp_path / ".syfthub" / "config.json"
        config_file.parent.mkdir(parents=True)

        original = SyftConfig(
            access_token="test_token",
            timeout=45.0,
            aggregators={"test": AggregatorConfig(url="http://test.com")},
        )
        save_config(original, config_file)

        loaded = load_config(config_file)
        assert loaded.access_token == "test_token"
        assert loaded.timeout == 45.0
        assert loaded.aggregators["test"].url == "http://test.com"

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        """Test loading config when file is corrupted."""
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {{{")

        config = load_config(config_file)
        assert isinstance(config, SyftConfig)
        # Should return default config
        assert config.access_token is None

    def test_load_invalid_schema(self, tmp_path: Path) -> None:
        """Test loading config with invalid schema."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"timeout": "not_a_number"}')

        config = load_config(config_file)
        assert isinstance(config, SyftConfig)
        # Should return default config on validation error
        assert config.timeout == 30.0


class TestUpdateConfig:
    """Tests for update_config function."""

    def test_update_single_value(self, mock_config: Path) -> None:
        """Test updating a single configuration value."""
        update_config({"timeout": 60.0})
        config = load_config()
        assert config.timeout == 60.0

    def test_update_multiple_values(self, mock_config: Path) -> None:
        """Test updating multiple configuration values."""
        update_config({"timeout": 90.0, "hub_url": "https://new.url"})
        config = load_config()
        assert config.timeout == 90.0
        assert config.hub_url == "https://new.url"

    def test_update_ignores_unknown_keys(self, mock_config: Path) -> None:
        """Test that unknown keys are ignored."""
        update_config({"unknown_key": "value", "timeout": 45.0})
        config = load_config()
        assert config.timeout == 45.0
        assert not hasattr(config, "unknown_key")


class TestClearTokens:
    """Tests for clear_tokens function."""

    def test_clear_tokens(self, mock_config: Path) -> None:
        """Test clearing authentication tokens."""
        # First set some tokens
        config = SyftConfig(
            access_token="test_access",
            refresh_token="test_refresh",
        )
        save_config(config)

        # Clear tokens
        clear_tokens()

        # Verify tokens are cleared
        loaded = load_config()
        assert loaded.access_token is None
        assert loaded.refresh_token is None

    def test_clear_tokens_preserves_other_settings(self, mock_config: Path) -> None:
        """Test that clearing tokens preserves other settings."""
        config = SyftConfig(
            access_token="test_access",
            timeout=60.0,
            default_aggregator="test",
        )
        save_config(config)

        clear_tokens()

        loaded = load_config()
        assert loaded.access_token is None
        assert loaded.timeout == 60.0
        assert loaded.default_aggregator == "test"


class TestConfigSerialization:
    """Tests for config serialization."""

    def test_json_serialization(self) -> None:
        """Test that config can be serialized to JSON."""
        config = SyftConfig(
            access_token="token",
            aggregators={"test": AggregatorConfig(url="http://test.com")},
        )
        json_str = config.model_dump_json()
        data = json.loads(json_str)

        assert data["access_token"] == "token"
        assert data["aggregators"]["test"]["url"] == "http://test.com"

    def test_json_deserialization(self) -> None:
        """Test that config can be deserialized from JSON."""
        data = {
            "access_token": "token",
            "aggregators": {"test": {"url": "http://test.com"}},
            "timeout": 45.0,
        }
        config = SyftConfig.model_validate(data)

        assert config.access_token == "token"
        assert config.aggregators["test"].url == "http://test.com"
        assert config.timeout == 45.0
