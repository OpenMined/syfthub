"""Management commands for SyftHub CLI (add/remove/update/list)."""

from __future__ import annotations

from typing import Annotated

import typer

from syfthub_cli.completion import complete_accounting_alias, complete_aggregator_alias
from syfthub_cli.config import (
    AccountingConfig,
    AggregatorConfig,
    load_config,
    save_config,
)
from syfthub_cli.output import (
    print_aliases_table,
    print_error,
    print_json,
    print_success,
    print_warning,
)

# Sub-apps for command groups
add_app = typer.Typer(no_args_is_help=True)
list_app = typer.Typer(no_args_is_help=True)
update_app = typer.Typer(no_args_is_help=True)
remove_app = typer.Typer(no_args_is_help=True)


# ============================================================================
# ADD commands
# ============================================================================


@add_app.command("aggregator")
def add_aggregator(
    alias: Annotated[str, typer.Argument(help="Alias name for the aggregator.")],
    url: Annotated[str, typer.Argument(help="URL of the aggregator endpoint.")],
    set_default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default aggregator."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Add an aggregator alias."""
    config = load_config()

    if alias in config.aggregators:
        if json_output:
            print_json(
                {"status": "error", "message": f"Aggregator '{alias}' already exists"}
            )
        else:
            print_error(
                f"Aggregator '{alias}' already exists. Use 'syft update aggregator' to modify it."
            )
        raise typer.Exit(1)

    config.aggregators[alias] = AggregatorConfig(url=url)

    if set_default:
        config.default_aggregator = alias

    save_config(config)

    if json_output:
        print_json(
            {
                "status": "success",
                "alias": alias,
                "url": url,
                "is_default": set_default,
            }
        )
    else:
        msg = f"Added aggregator '{alias}' -> {url}"
        if set_default:
            msg += " (default)"
        print_success(msg)


@add_app.command("accounting")
def add_accounting(
    alias: Annotated[
        str, typer.Argument(help="Alias name for the accounting service.")
    ],
    url: Annotated[str, typer.Argument(help="URL of the accounting service.")],
    set_default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default accounting service."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Add an accounting service alias."""
    config = load_config()

    if alias in config.accounting_services:
        if json_output:
            print_json(
                {
                    "status": "error",
                    "message": f"Accounting service '{alias}' already exists",
                }
            )
        else:
            print_error(
                f"Accounting service '{alias}' already exists. Use 'syft update accounting' to modify it."
            )
        raise typer.Exit(1)

    config.accounting_services[alias] = AccountingConfig(url=url)

    if set_default:
        config.default_accounting = alias

    save_config(config)

    if json_output:
        print_json(
            {
                "status": "success",
                "alias": alias,
                "url": url,
                "is_default": set_default,
            }
        )
    else:
        msg = f"Added accounting service '{alias}' -> {url}"
        if set_default:
            msg += " (default)"
        print_success(msg)


# ============================================================================
# LIST commands
# ============================================================================


@list_app.command("aggregator")
def list_aggregators(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """List aggregator aliases."""
    config = load_config()

    if json_output:
        result = {
            alias: {"url": cfg.url, "is_default": alias == config.default_aggregator}
            for alias, cfg in config.aggregators.items()
        }
        print_json({"status": "success", "aggregators": result})
    else:
        print_aliases_table(config.aggregators, "Aggregator", config.default_aggregator)


@list_app.command("accounting")
def list_accounting(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """List accounting service aliases."""
    config = load_config()

    if json_output:
        result = {
            alias: {"url": cfg.url, "is_default": alias == config.default_accounting}
            for alias, cfg in config.accounting_services.items()
        }
        print_json({"status": "success", "accounting_services": result})
    else:
        print_aliases_table(
            config.accounting_services, "Accounting", config.default_accounting
        )


# ============================================================================
# UPDATE commands
# ============================================================================


@update_app.command("aggregator")
def update_aggregator(
    alias: Annotated[
        str,
        typer.Argument(
            help="Alias name to update.", autocompletion=complete_aggregator_alias
        ),
    ],
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="New URL for the aggregator."),
    ] = None,
    set_default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default aggregator."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Update an aggregator alias."""
    config = load_config()

    if alias not in config.aggregators:
        if json_output:
            print_json(
                {"status": "error", "message": f"Aggregator '{alias}' not found"}
            )
        else:
            print_error(f"Aggregator '{alias}' not found.")
        raise typer.Exit(1)

    if url is None and not set_default:
        if json_output:
            print_json({"status": "error", "message": "Nothing to update"})
        else:
            print_warning("Nothing to update. Specify --url or --default.")
        return

    if url:
        config.aggregators[alias] = AggregatorConfig(url=url)

    if set_default:
        config.default_aggregator = alias

    save_config(config)

    if json_output:
        print_json(
            {
                "status": "success",
                "alias": alias,
                "url": config.aggregators[alias].url,
                "is_default": config.default_aggregator == alias,
            }
        )
    else:
        print_success(f"Updated aggregator '{alias}'")


@update_app.command("accounting")
def update_accounting(
    alias: Annotated[
        str,
        typer.Argument(
            help="Alias name to update.", autocompletion=complete_accounting_alias
        ),
    ],
    url: Annotated[
        str | None,
        typer.Option("--url", "-u", help="New URL for the accounting service."),
    ] = None,
    set_default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default accounting service."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Update an accounting service alias."""
    config = load_config()

    if alias not in config.accounting_services:
        if json_output:
            print_json(
                {
                    "status": "error",
                    "message": f"Accounting service '{alias}' not found",
                }
            )
        else:
            print_error(f"Accounting service '{alias}' not found.")
        raise typer.Exit(1)

    if url is None and not set_default:
        if json_output:
            print_json({"status": "error", "message": "Nothing to update"})
        else:
            print_warning("Nothing to update. Specify --url or --default.")
        return

    if url:
        config.accounting_services[alias] = AccountingConfig(url=url)

    if set_default:
        config.default_accounting = alias

    save_config(config)

    if json_output:
        print_json(
            {
                "status": "success",
                "alias": alias,
                "url": config.accounting_services[alias].url,
                "is_default": config.default_accounting == alias,
            }
        )
    else:
        print_success(f"Updated accounting service '{alias}'")


# ============================================================================
# REMOVE commands
# ============================================================================


@remove_app.command("aggregator")
def remove_aggregator(
    alias: Annotated[
        str,
        typer.Argument(
            help="Alias name to remove.", autocompletion=complete_aggregator_alias
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Remove an aggregator alias."""
    config = load_config()

    if alias not in config.aggregators:
        if json_output:
            print_json(
                {"status": "error", "message": f"Aggregator '{alias}' not found"}
            )
        else:
            print_error(f"Aggregator '{alias}' not found.")
        raise typer.Exit(1)

    del config.aggregators[alias]

    # Clear default if it was this alias
    if config.default_aggregator == alias:
        config.default_aggregator = None

    save_config(config)

    if json_output:
        print_json({"status": "success", "alias": alias, "message": "Removed"})
    else:
        print_success(f"Removed aggregator '{alias}'")


@remove_app.command("accounting")
def remove_accounting(
    alias: Annotated[
        str,
        typer.Argument(
            help="Alias name to remove.", autocompletion=complete_accounting_alias
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Remove an accounting service alias."""
    config = load_config()

    if alias not in config.accounting_services:
        if json_output:
            print_json(
                {
                    "status": "error",
                    "message": f"Accounting service '{alias}' not found",
                }
            )
        else:
            print_error(f"Accounting service '{alias}' not found.")
        raise typer.Exit(1)

    del config.accounting_services[alias]

    # Clear default if it was this alias
    if config.default_accounting == alias:
        config.default_accounting = None

    save_config(config)

    if json_output:
        print_json({"status": "success", "alias": alias, "message": "Removed"})
    else:
        print_success(f"Removed accounting service '{alias}'")
