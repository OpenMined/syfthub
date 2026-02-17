"""Output formatting helpers using Rich."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from syfthub_sdk import EndpointPublic

# Shared console instances
console = Console()
err_console = Console(stderr=True)


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    err_console.print(f"[bold red]Error:[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]{message}[/bold green]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[bold blue]Info:[/bold blue] {message}")


def print_json(data: Any, *, indent: int = 2) -> None:
    """Print data as JSON."""
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    print(json.dumps(data, indent=indent, default=str))


def print_markdown(content: str, *, title: str | None = None) -> None:
    """Render markdown content."""
    md = Markdown(content)
    if title:
        console.print(Panel(md, title=title, border_style="blue"))
    else:
        console.print(md)


def print_users_table(users: dict[str, list[EndpointPublic]]) -> None:
    """Print a table of users with endpoint counts."""
    table = Table(title="Active Users")
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("Endpoints", justify="right", style="green")
    table.add_column("Types", style="magenta")

    for username, endpoints in sorted(users.items()):
        types = {ep.type.value for ep in endpoints}
        table.add_row(username, str(len(endpoints)), ", ".join(sorted(types)))

    console.print(table)


def print_endpoints_table(
    endpoints: list[EndpointPublic], username: str | None = None
) -> None:
    """Print a table of endpoints."""
    title = f"Endpoints for {username}" if username else "Endpoints"
    table = Table(title=title)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Version", style="yellow")
    table.add_column("Stars", justify="right", style="green")
    table.add_column("Description", max_width=40)

    for ep in endpoints:
        description = ep.description or ""
        if len(description) > 40:
            description = description[:37] + "..."
        table.add_row(
            ep.name,
            ep.type.value,
            ep.version,
            str(ep.stars_count),
            description,
        )

    console.print(table)


def print_endpoint_detail(endpoint: EndpointPublic) -> None:
    """Print detailed information about a single endpoint."""
    console.print()
    console.print(f"[bold cyan]{endpoint.owner_username}/{endpoint.name}[/bold cyan]")
    console.print(f"[dim]Type:[/dim] {endpoint.type.value}")
    console.print(f"[dim]Version:[/dim] {endpoint.version}")
    console.print(f"[dim]Stars:[/dim] {endpoint.stars_count}")

    if endpoint.description:
        console.print()
        console.print("[dim]Description:[/dim]")
        console.print(endpoint.description)

    if endpoint.readme:
        console.print()
        print_markdown(endpoint.readme, title="README")


def print_aliases_table(
    aliases: dict[str, Any], alias_type: str, default: str | None = None
) -> None:
    """Print a table of aliases (aggregators or accounting services)."""
    table = Table(title=f"{alias_type} Aliases")
    table.add_column("Alias", style="cyan", no_wrap=True)
    table.add_column("URL", style="green")
    table.add_column("Default", style="yellow")

    for name, config in sorted(aliases.items()):
        url = config.url if hasattr(config, "url") else str(config)
        is_default = "Yes" if name == default else ""
        table.add_row(name, url, is_default)

    if not aliases:
        console.print(f"[dim]No {alias_type.lower()} aliases configured.[/dim]")
    else:
        console.print(table)


def print_config_table(config: dict[str, Any]) -> None:
    """Print configuration as a table."""
    table = Table(title="Configuration")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    for key, value in sorted(config.items()):
        if key in ("access_token", "refresh_token") and value:
            # Mask tokens
            value = value[:8] + "..." if len(value) > 8 else "***"
        elif isinstance(value, dict):
            value = f"<{len(value)} items>"
        table.add_row(key, str(value) if value is not None else "[dim]not set[/dim]")

    console.print(table)


def print_streaming_token(token: str) -> None:
    """Print a streaming token without newline."""
    sys.stdout.write(token)
    sys.stdout.flush()


def print_streaming_done() -> None:
    """Print newline after streaming is complete."""
    print()


# =============================================================================
# File System Style Output
# =============================================================================

# Type icons for endpoints
TYPE_ICONS = {
    "model": "[magenta]󰧑[/magenta]",  # nerd font model icon
    "data_source": "[blue]󰆼[/blue]",  # nerd font database icon
    "model_data_source": "[yellow]󰯂[/yellow]",  # nerd font hybrid icon
}

# Fallback icons (using standard unicode)
TYPE_ICONS_FALLBACK = {
    "model": "[magenta]⚡[/magenta]",
    "data_source": "[blue]📦[/blue]",
    "model_data_source": "[yellow]🔀[/yellow]",
}


def _get_type_icon(endpoint_type: str) -> str:
    """Get icon for endpoint type."""
    return TYPE_ICONS_FALLBACK.get(endpoint_type, "📄")


# =============================================================================
# Grid Style Output (ls-like columns)
# =============================================================================


def _get_type_color(endpoint_type: str) -> str:
    """Get color for endpoint type."""
    colors = {
        "model": "magenta",
        "data_source": "blue",
        "model_data_source": "yellow",
    }
    return colors.get(endpoint_type, "white")


def print_users_grid(users: dict[str, list[EndpointPublic]]) -> None:
    """Print users in a grid layout like 'ls' command."""
    if not users:
        console.print("[dim]No users found.[/dim]")
        return

    from rich.columns import Columns
    from rich.text import Text

    # Build list of formatted user entries
    max_name_width = 20
    cells = []
    for username, endpoints in sorted(users.items()):
        # Count by type for badge
        type_counts: dict[str, int] = {}
        for ep in endpoints:
            type_counts[ep.type.value] = type_counts.get(ep.type.value, 0) + 1

        # Create compact badge like "2m 3d" for 2 models, 3 data sources
        badges = []
        if "model" in type_counts:
            badges.append(f"[magenta]{type_counts['model']}m[/magenta]")
        if "data_source" in type_counts:
            badges.append(f"[blue]{type_counts['data_source']}d[/blue]")
        if "model_data_source" in type_counts:
            badges.append(f"[yellow]{type_counts['model_data_source']}h[/yellow]")

        badge_str = " ".join(badges)
        name = (
            username
            if len(username) <= max_name_width
            else username[: max_name_width - 2] + ".."
        )
        cell = Text.from_markup(
            f"[bold cyan]{name}/[/bold cyan] [dim]{badge_str}[/dim]"
        )
        cells.append(cell)

    # Use Rich Columns with fixed width for grid
    console.print(Columns(cells, column_first=False, expand=False, width=32))


def print_endpoints_grid(
    endpoints: list[EndpointPublic], username: str | None = None
) -> None:
    """Print endpoints in a grid layout like 'ls' command."""
    if not endpoints:
        if username:
            console.print(f"[dim]No endpoints found for '{username}'[/dim]")
        else:
            console.print("[dim]No endpoints found.[/dim]")
        return

    if username:
        console.print(f"[bold cyan]{username}/[/bold cyan]")
        console.print()

    from rich.columns import Columns
    from rich.text import Text

    # Build cells with icons, truncating long names
    max_name_width = 28
    cells = []
    for ep in sorted(endpoints, key=lambda e: (e.type.value, e.name)):
        icon = _get_type_icon(ep.type.value)
        color = _get_type_color(ep.type.value)
        name = (
            ep.name
            if len(ep.name) <= max_name_width
            else ep.name[: max_name_width - 2] + ".."
        )
        cell = Text.from_markup(f"{icon} [{color}]{name}[/{color}]")
        cells.append(cell)

    # Use Rich Columns with fixed width for grid
    console.print(Columns(cells, column_first=False, expand=False, width=32))
