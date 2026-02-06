"""Main entry point for SyftHub CLI."""

from __future__ import annotations

import atexit
from typing import Annotated

import typer
from rich.console import Console

from syfthub_cli import __version__
from syfthub_cli.commands import (
    auth,
    config_cmd,
    discovery,
    management,
    query,
    update_cmd,
    utils,
)

# Console for update notifications
_console = Console(stderr=True)

# Create the main Typer app
app = typer.Typer(
    name="syft",
    help="SyftHub CLI - Interact with the SyftHub platform.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register command groups
app.add_typer(management.add_app, name="add", help="Add infrastructure aliases.")
app.add_typer(management.list_app, name="list", help="List infrastructure aliases.")
app.add_typer(
    management.update_app, name="update", help="Update infrastructure aliases."
)
app.add_typer(
    management.remove_app, name="remove", help="Remove infrastructure aliases."
)
app.add_typer(config_cmd.app, name="config", help="Manage CLI configuration.")
app.add_typer(
    utils.completion_app, name="completion", help="Generate shell completion scripts."
)

# Register top-level commands
app.command(name="login", help="Authenticate with SyftHub.")(auth.login)
app.command(name="logout", help="Clear authentication credentials.")(auth.logout)
app.command(name="whoami", help="Show current authenticated user.")(utils.whoami)
app.command(name="ls", help="Browse users and endpoints.")(discovery.ls)
app.command(name="query", help="Query endpoints using RAG.")(query.query)
app.command(name="upgrade", help="Check for and install CLI updates.")(
    update_cmd.update
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        typer.echo(f"syft version {__version__}")
        raise typer.Exit()


def _show_update_notification() -> None:
    """Show update notification at exit if available."""
    try:
        from syfthub_cli.update import get_update_notification

        notification = get_update_notification()
        if notification:
            _console.print(notification)
    except Exception:
        # Never interrupt the user due to update check failures
        pass


# Flag to track if update check is registered
_update_check_registered = False


@app.callback()
def main(
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
    no_update_check: Annotated[
        bool,
        typer.Option(
            "--no-update-check",
            help="Disable update check notification.",
            hidden=True,
        ),
    ] = False,
) -> None:
    """SyftHub CLI - A Unix-style interface for the SyftHub platform."""
    global _update_check_registered

    # Register update notification at exit (once per invocation)
    if not no_update_check and not _update_check_registered:
        _update_check_registered = True
        atexit.register(_show_update_notification)


if __name__ == "__main__":
    app()
