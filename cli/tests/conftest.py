"""Test fixtures for SyftHub CLI."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from syfthub_cli.config import SyftConfig


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / ".syfthub"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_config_file(temp_config_dir: Path) -> Path:
    """Create a temporary config file path."""
    return temp_config_dir / "config.json"


@pytest.fixture
def sample_config() -> dict:
    """Return a sample configuration dict."""
    return {
        "access_token": None,
        "refresh_token": None,
        "aggregators": {
            "local": {"url": "http://localhost:8001"},
            "prod": {"url": "https://aggregator.syftbox.org"},
        },
        "accounting_services": {
            "local": {"url": "http://localhost:8002"},
        },
        "default_aggregator": "local",
        "default_accounting": None,
        "timeout": 30.0,
        "hub_url": "https://hub.syftbox.org",
    }


@pytest.fixture
def config_file_with_data(
    temp_config_file: Path, sample_config: dict
) -> Generator[Path, None, None]:
    """Create a config file with sample data."""
    temp_config_file.write_text(json.dumps(sample_config, indent=2))
    yield temp_config_file


@pytest.fixture
def mock_config(
    monkeypatch: pytest.MonkeyPatch, temp_config_dir: Path, temp_config_file: Path
) -> Generator[Path, None, None]:
    """Mock the config paths to use temp directory."""
    import syfthub_cli.config as config_module

    monkeypatch.setattr(config_module, "CONFIG_DIR", temp_config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", temp_config_file)
    yield temp_config_file


@pytest.fixture
def authenticated_config(mock_config: Path) -> SyftConfig:
    """Create an authenticated config."""
    from syfthub_cli.config import SyftConfig, save_config

    config = SyftConfig(
        access_token="test_access_token_12345",
        refresh_token="test_refresh_token_12345",
        hub_url="https://hub.syftbox.org",
    )
    save_config(config)
    return config
