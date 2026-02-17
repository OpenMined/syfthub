"""Configuration management for SyftHub CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Default config directory and file
CONFIG_DIR = Path.home() / ".syfthub"
CONFIG_FILE = CONFIG_DIR / "config.json"


class AggregatorConfig(BaseModel):
    """Configuration for an aggregator endpoint."""

    url: str


class AccountingConfig(BaseModel):
    """Configuration for an accounting service."""

    url: str


class SyftConfig(BaseModel):
    """Main configuration model for SyftHub CLI."""

    # Authentication tokens
    access_token: str | None = None
    refresh_token: str | None = None

    # Infrastructure aliases
    aggregators: dict[str, AggregatorConfig] = Field(default_factory=dict)
    accounting_services: dict[str, AccountingConfig] = Field(default_factory=dict)

    # Default selections
    default_aggregator: str | None = None
    default_accounting: str | None = None

    # API settings
    timeout: float = 30.0
    hub_url: str = "https://hub.syftbox.org"

    def get_aggregator_url(self, alias: str | None = None) -> str | None:
        """Get aggregator URL by alias or return default."""
        if alias:
            if alias in self.aggregators:
                return self.aggregators[alias].url
            # Treat as direct URL if not an alias
            return alias
        if self.default_aggregator and self.default_aggregator in self.aggregators:
            return self.aggregators[self.default_aggregator].url
        return None

    def get_accounting_url(self, alias: str | None = None) -> str | None:
        """Get accounting service URL by alias or return default."""
        if alias:
            if alias in self.accounting_services:
                return self.accounting_services[alias].url
            # Treat as direct URL if not an alias
            return alias
        if (
            self.default_accounting
            and self.default_accounting in self.accounting_services
        ):
            return self.accounting_services[self.default_accounting].url
        return None


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config(config_path: Path | None = None) -> SyftConfig:
    """Load configuration from file."""
    path = config_path or CONFIG_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return SyftConfig.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            # Return default config if file is corrupted
            return SyftConfig()
    return SyftConfig()


def save_config(config: SyftConfig, config_path: Path | None = None) -> None:
    """Save configuration to file."""
    path = config_path or CONFIG_FILE
    ensure_config_dir()
    path.write_text(config.model_dump_json(indent=2))


def update_config(updates: dict[str, Any], config_path: Path | None = None) -> None:
    """Update specific configuration values."""
    config = load_config(config_path)
    for key, value in updates.items():
        if hasattr(config, key):
            setattr(config, key, value)
    save_config(config, config_path)


def clear_tokens(config_path: Path | None = None) -> None:
    """Clear authentication tokens from config."""
    config = load_config(config_path)
    config.access_token = None
    config.refresh_token = None
    save_config(config, config_path)
