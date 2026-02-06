"""Update command for SyftHub CLI."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from syfthub_cli import __version__
from syfthub_cli.update import (
    check_for_updates,
    is_binary_install,
    perform_self_update,
)

console = Console()
err_console = Console(stderr=True)


def update(
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            "-c",
            help="Only check for updates, don't install.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force update check (bypass cache).",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation prompt.",
        ),
    ] = False,
) -> None:
    """Check for and install updates.

    By default, downloads and installs the latest version.
    Use --check to only check without installing.

    Examples:
        syft update           # Update to latest version
        syft update --check   # Check if update is available
        syft update -y        # Update without confirmation
    """
    console.print(f"Current version: [cyan]v{__version__}[/cyan]")
    console.print("Checking for updates...")

    update_info = check_for_updates(force=force)

    if not update_info:
        console.print("[green]You are running the latest version![/green]")
        return

    # Show update available
    console.print()
    console.print(
        Panel(
            f"[bold]New version available: v{update_info.version}[/bold]\n\n"
            f"Published: {update_info.published_at[:10] if update_info.published_at else 'Unknown'}\n"
            f"Release: {update_info.release_url}",
            title="Update Available",
            border_style="yellow",
        )
    )

    if check:
        console.print("\n[dim]Run 'syft update' to install the update.[/dim]")
        return

    # Check if we can self-update
    if not is_binary_install():
        console.print()
        err_console.print(
            "[yellow]Self-update is only available for standalone binary installations.[/yellow]"
        )
        console.print("\nTo update, use one of these methods:")
        console.print("  [cyan]pip install --upgrade syfthub-cli[/cyan]")
        console.print("  [dim]or reinstall using:[/dim]")
        console.print(
            "  [cyan]curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh[/cyan]"
        )
        raise typer.Exit(1)

    # Confirm update
    if not yes:
        console.print()
        confirm = typer.confirm(
            f"Update from v{__version__} to v{update_info.version}?"
        )
        if not confirm:
            console.print("[dim]Update cancelled.[/dim]")
            raise typer.Abort()

    # Perform update
    console.print()
    console.print("Downloading update...")

    success, message = perform_self_update(update_info)

    if success:
        console.print(f"[green]{message}[/green]")
        console.print("\n[dim]Restart your terminal to use the new version.[/dim]")
    else:
        err_console.print(f"[red]Update failed:[/red] {message}")
        raise typer.Exit(1)
