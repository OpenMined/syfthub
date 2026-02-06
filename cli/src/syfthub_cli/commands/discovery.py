"""Discovery commands for SyftHub CLI."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated

import typer

from syfthub_cli.completion import complete_ls_target
from syfthub_cli.config import load_config
from syfthub_cli.output import (
    print_endpoint_detail,
    print_endpoints_grid,
    print_endpoints_table,
    print_error,
    print_json,
    print_users_grid,
    print_users_table,
)
from syfthub_sdk import AuthTokens, NotFoundError, SyftHubClient


def _get_authenticated_client(config) -> SyftHubClient:  # type: ignore[no-untyped-def]
    """Create an authenticated client from config."""
    client = SyftHubClient(base_url=config.hub_url, timeout=config.timeout)
    if config.access_token:
        client.set_tokens(
            AuthTokens(
                access_token=config.access_token,
                refresh_token=config.refresh_token or "",
            )
        )
    return client


def ls(
    target: Annotated[
        str | None,
        typer.Argument(
            help="Target to list: empty for all users, username for user's endpoints, or user/endpoint for details.",
            autocompletion=complete_ls_target,
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum number of results to show."),
    ] = 50,
    long_format: Annotated[
        bool,
        typer.Option("--long", "-l", help="Use detailed table format."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Browse users and endpoints.

    Usage modes:

    - syft ls           : List all active users with endpoint counts

    - syft ls <user>    : List endpoints for a specific user

    - syft ls user/ep   : Show details/README for a specific endpoint
    """
    config = load_config()

    # Normalize target: strip trailing slash
    if target and target.endswith("/"):
        target = target.rstrip("/")

    try:
        with _get_authenticated_client(config) as client:
            if target is None:
                # Mode 1: List all users
                _list_users(client, limit, long_format, json_output)
            elif "/" in target:
                # Mode 3: Show endpoint details (user/endpoint)
                _show_endpoint(client, target, json_output)
            else:
                # Mode 2: List user's endpoints
                _list_user_endpoints(client, target, limit, long_format, json_output)

    except NotFoundError as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(str(e))
        raise typer.Exit(1) from None
    except Exception as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(f"Failed to list: {e}")
        raise typer.Exit(1) from None


def _list_users(
    client: SyftHubClient, limit: int, long_format: bool, json_output: bool
) -> None:
    """List all users with their endpoint counts."""
    users: dict[str, list] = defaultdict(list)  # type: ignore[type-arg]

    for count, endpoint in enumerate(client.hub.browse(), start=1):
        users[endpoint.owner_username].append(endpoint)
        if count >= limit:
            break

    if json_output:
        result = {
            username: [
                {
                    "name": ep.name,
                    "type": ep.type.value,
                    "version": ep.version,
                    "stars": ep.stars_count,
                }
                for ep in endpoints
            ]
            for username, endpoints in users.items()
        }
        print_json({"status": "success", "users": result})
    elif long_format:
        print_users_table(users)
    else:
        print_users_grid(users)


def _list_user_endpoints(
    client: SyftHubClient,
    username: str,
    limit: int,
    long_format: bool,
    json_output: bool,
) -> None:
    """List endpoints for a specific user."""
    endpoints = []
    count = 0

    for endpoint in client.hub.browse():
        if endpoint.owner_username.lower() == username.lower():
            endpoints.append(endpoint)
            count += 1
            if count >= limit:
                break

    if json_output:
        result = [
            {
                "name": ep.name,
                "type": ep.type.value,
                "version": ep.version,
                "stars": ep.stars_count,
                "description": ep.description,
            }
            for ep in endpoints
        ]
        print_json({"status": "success", "endpoints": result})
    elif long_format:
        print_endpoints_table(endpoints, username)
    else:
        print_endpoints_grid(endpoints, username)


def _show_endpoint(client: SyftHubClient, path: str, json_output: bool) -> None:
    """Show details for a specific endpoint."""
    endpoint = client.hub.get(path)

    if json_output:
        print_json(
            {
                "status": "success",
                "endpoint": {
                    "owner": endpoint.owner_username,
                    "name": endpoint.name,
                    "type": endpoint.type.value,
                    "version": endpoint.version,
                    "stars": endpoint.stars_count,
                    "description": endpoint.description,
                    "readme": endpoint.readme,
                    "created_at": str(endpoint.created_at)
                    if endpoint.created_at
                    else None,
                    "updated_at": str(endpoint.updated_at)
                    if endpoint.updated_at
                    else None,
                },
            }
        )
    else:
        print_endpoint_detail(endpoint)
