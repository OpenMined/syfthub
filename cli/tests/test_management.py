"""Tests for management commands (add, list, update, remove)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from syfthub_cli.config import (
    AccountingConfig,
    AggregatorConfig,
    SyftConfig,
    load_config,
    save_config,
)
from syfthub_cli.main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestAddAggregator:
    """Tests for add aggregator command."""

    def test_add_aggregator(self, runner: CliRunner, mock_config: Path) -> None:
        """Test adding a new aggregator."""
        result = runner.invoke(
            app, ["add", "aggregator", "local", "http://localhost:8001"]
        )

        assert result.exit_code == 0
        assert "Added aggregator 'local'" in result.stdout

        config = load_config()
        assert "local" in config.aggregators
        assert config.aggregators["local"].url == "http://localhost:8001"

    def test_add_aggregator_as_default(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test adding aggregator as default."""
        result = runner.invoke(
            app, ["add", "aggregator", "local", "http://localhost:8001", "--default"]
        )

        assert result.exit_code == 0
        assert "default" in result.stdout

        config = load_config()
        assert config.default_aggregator == "local"

    def test_add_aggregator_already_exists(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test adding an aggregator that already exists."""
        # Add first time
        runner.invoke(app, ["add", "aggregator", "local", "http://localhost:8001"])

        # Try to add again
        result = runner.invoke(
            app, ["add", "aggregator", "local", "http://different:8001"]
        )

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_aggregator_json_output(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test adding aggregator with JSON output."""
        result = runner.invoke(
            app, ["add", "aggregator", "local", "http://localhost:8001", "--json"]
        )

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"alias": "local"' in result.stdout


class TestAddAccounting:
    """Tests for add accounting command."""

    def test_add_accounting(self, runner: CliRunner, mock_config: Path) -> None:
        """Test adding a new accounting service."""
        result = runner.invoke(
            app, ["add", "accounting", "main", "http://localhost:8002"]
        )

        assert result.exit_code == 0
        assert "Added accounting service 'main'" in result.stdout

        config = load_config()
        assert "main" in config.accounting_services
        assert config.accounting_services["main"].url == "http://localhost:8002"

    def test_add_accounting_as_default(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test adding accounting service as default."""
        result = runner.invoke(
            app, ["add", "accounting", "main", "http://localhost:8002", "--default"]
        )

        assert result.exit_code == 0
        config = load_config()
        assert config.default_accounting == "main"


class TestListAggregator:
    """Tests for list aggregator command."""

    def test_list_aggregators_empty(self, runner: CliRunner, mock_config: Path) -> None:
        """Test listing aggregators when none configured."""
        result = runner.invoke(app, ["list", "aggregator"])

        assert result.exit_code == 0
        assert "No aggregator" in result.stdout.lower() or "Alias" not in result.stdout

    def test_list_aggregators(self, runner: CliRunner, mock_config: Path) -> None:
        """Test listing configured aggregators."""
        # Add some aggregators
        config = SyftConfig(
            aggregators={
                "local": AggregatorConfig(url="http://localhost:8001"),
                "prod": AggregatorConfig(url="https://agg.example.com"),
            },
            default_aggregator="local",
        )
        save_config(config)

        result = runner.invoke(app, ["list", "aggregator"])

        assert result.exit_code == 0
        assert "local" in result.stdout
        assert "prod" in result.stdout
        assert "http://localhost:8001" in result.stdout

    def test_list_aggregators_json(self, runner: CliRunner, mock_config: Path) -> None:
        """Test listing aggregators with JSON output."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")},
            default_aggregator="local",
        )
        save_config(config)

        result = runner.invoke(app, ["list", "aggregator", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout
        assert '"aggregators"' in result.stdout
        assert '"is_default": true' in result.stdout


class TestListAccounting:
    """Tests for list accounting command."""

    def test_list_accounting_services(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test listing configured accounting services."""
        config = SyftConfig(
            accounting_services={
                "main": AccountingConfig(url="http://localhost:8002"),
            }
        )
        save_config(config)

        result = runner.invoke(app, ["list", "accounting"])

        assert result.exit_code == 0
        assert "main" in result.stdout


class TestUpdateAggregator:
    """Tests for update aggregator command."""

    def test_update_aggregator_url(self, runner: CliRunner, mock_config: Path) -> None:
        """Test updating aggregator URL."""
        # Add aggregator first
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        result = runner.invoke(
            app, ["update", "aggregator", "local", "--url", "http://newhost:8001"]
        )

        assert result.exit_code == 0
        assert "Updated aggregator 'local'" in result.stdout

        config = load_config()
        assert config.aggregators["local"].url == "http://newhost:8001"

    def test_update_aggregator_set_default(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test setting aggregator as default."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        result = runner.invoke(app, ["update", "aggregator", "local", "--default"])

        assert result.exit_code == 0
        config = load_config()
        assert config.default_aggregator == "local"

    def test_update_aggregator_not_found(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test updating non-existent aggregator."""
        result = runner.invoke(
            app, ["update", "aggregator", "nonexistent", "--url", "http://test.com"]
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_update_aggregator_nothing_to_update(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test update with no changes specified."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        result = runner.invoke(app, ["update", "aggregator", "local"])

        assert result.exit_code == 0
        assert "Nothing to update" in result.stdout


class TestUpdateAccounting:
    """Tests for update accounting command."""

    def test_update_accounting_url(self, runner: CliRunner, mock_config: Path) -> None:
        """Test updating accounting service URL."""
        config = SyftConfig(
            accounting_services={"main": AccountingConfig(url="http://localhost:8002")}
        )
        save_config(config)

        result = runner.invoke(
            app, ["update", "accounting", "main", "--url", "http://newhost:8002"]
        )

        assert result.exit_code == 0
        config = load_config()
        assert config.accounting_services["main"].url == "http://newhost:8002"


class TestRemoveAggregator:
    """Tests for remove aggregator command."""

    def test_remove_aggregator(self, runner: CliRunner, mock_config: Path) -> None:
        """Test removing an aggregator."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        result = runner.invoke(app, ["remove", "aggregator", "local"])

        assert result.exit_code == 0
        assert "Removed aggregator 'local'" in result.stdout

        config = load_config()
        assert "local" not in config.aggregators

    def test_remove_default_aggregator(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test removing the default aggregator clears default."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")},
            default_aggregator="local",
        )
        save_config(config)

        runner.invoke(app, ["remove", "aggregator", "local"])

        config = load_config()
        assert config.default_aggregator is None

    def test_remove_aggregator_not_found(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test removing non-existent aggregator."""
        result = runner.invoke(app, ["remove", "aggregator", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_remove_aggregator_json_output(
        self, runner: CliRunner, mock_config: Path
    ) -> None:
        """Test removing aggregator with JSON output."""
        config = SyftConfig(
            aggregators={"local": AggregatorConfig(url="http://localhost:8001")}
        )
        save_config(config)

        result = runner.invoke(app, ["remove", "aggregator", "local", "--json"])

        assert result.exit_code == 0
        assert '"status": "success"' in result.stdout


class TestRemoveAccounting:
    """Tests for remove accounting command."""

    def test_remove_accounting(self, runner: CliRunner, mock_config: Path) -> None:
        """Test removing an accounting service."""
        config = SyftConfig(
            accounting_services={"main": AccountingConfig(url="http://localhost:8002")}
        )
        save_config(config)

        result = runner.invoke(app, ["remove", "accounting", "main"])

        assert result.exit_code == 0
        assert "Removed accounting service 'main'" in result.stdout

        config = load_config()
        assert "main" not in config.accounting_services
