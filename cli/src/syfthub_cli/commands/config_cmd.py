"""Configuration commands for SyftHub CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from syfthub_cli.completion import complete_config_key
from syfthub_cli.config import load_config, save_config
from syfthub_cli.output import (
    print_config_table,
    print_error,
    print_json,
    print_success,
)

app = typer.Typer(no_args_is_help=True)

# Allowed configuration keys for 'config set'
ALLOWED_KEYS = {
    "default_aggregator": "Default aggregator alias",
    "default_accounting": "Default accounting service alias",
    "timeout": "Request timeout in seconds",
    "hub_url": "SyftHub API URL",
}


@app.command("set")
def config_set(
    key: Annotated[
        str,
        typer.Argument(
            help=f"Configuration key. Allowed: {', '.join(ALLOWED_KEYS.keys())}",
            autocompletion=complete_config_key,
        ),
    ],
    value: Annotated[str, typer.Argument(help="Value to set.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Set a configuration value."""
    if key not in ALLOWED_KEYS:
        if json_output:
            print_json(
                {
                    "status": "error",
                    "message": f"Unknown key '{key}'",
                    "allowed_keys": list(ALLOWED_KEYS.keys()),
                }
            )
        else:
            print_error(
                f"Unknown key '{key}'. Allowed keys: {', '.join(ALLOWED_KEYS.keys())}"
            )
        raise typer.Exit(1)

    config = load_config()

    # Type conversion for specific keys
    if key == "timeout":
        try:
            typed_value: str | float | None = float(value)
        except ValueError:
            if json_output:
                print_json(
                    {"status": "error", "message": f"Invalid timeout value: {value}"}
                )
            else:
                print_error(f"Invalid timeout value: {value}. Must be a number.")
            raise typer.Exit(1) from None
    elif key in ("default_aggregator", "default_accounting"):
        # Allow clearing by setting to empty string
        typed_value = value if value else None
    else:
        typed_value = value

    setattr(config, key, typed_value)
    save_config(config)

    if json_output:
        print_json({"status": "success", "key": key, "value": typed_value})
    else:
        print_success(f"Set {key} = {typed_value}")


@app.command("show")
def config_show(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Display current configuration."""
    config = load_config()

    if json_output:
        # Include all config values
        data = config.model_dump()
        # Convert nested models to dicts
        data["aggregators"] = {k: {"url": v.url} for k, v in config.aggregators.items()}
        data["accounting_services"] = {
            k: {"url": v.url} for k, v in config.accounting_services.items()
        }
        print_json({"status": "success", "config": data})
    else:
        # Display as table (excluding sensitive data in detail)
        print_config_table(config.model_dump())


@app.command("path")
def config_path(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Show the configuration file path."""
    from syfthub_cli.config import CONFIG_FILE

    if json_output:
        print_json({"status": "success", "path": str(CONFIG_FILE)})
    else:
        typer.echo(str(CONFIG_FILE))
