"""Authentication commands for SyftHub CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from syfthub_cli.config import clear_tokens, load_config, save_config
from syfthub_cli.output import print_error, print_json, print_success
from syfthub_sdk import AuthenticationError, SyftHubClient


def login(
    username: Annotated[
        str | None,
        typer.Option("--username", "-u", help="Username for authentication."),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            help="Password for authentication.",
            hide_input=True,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Authenticate with SyftHub.

    Prompts for username and password if not provided via options.
    """
    config = load_config()

    # Prompt for credentials if not provided
    if username is None:
        username = typer.prompt("Username")
    if password is None:
        password = typer.prompt("Password", hide_input=True)

    try:
        with SyftHubClient(base_url=config.hub_url, timeout=config.timeout) as client:
            user = client.login(username=username, password=password)

            # Store tokens in config
            tokens = client.get_tokens()
            if tokens:
                config.access_token = tokens.access_token
                config.refresh_token = tokens.refresh_token
                save_config(config)

            if json_output:
                print_json(
                    {
                        "status": "success",
                        "username": user.username,
                        "email": user.email,
                    }
                )
            else:
                print_success(f"Logged in as {user.username}")

    except AuthenticationError as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(f"Authentication failed: {e}")
        raise typer.Exit(1) from None
    except Exception as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(f"Login failed: {e}")
        raise typer.Exit(1) from None


def logout(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Clear authentication credentials.

    Removes stored tokens from the local configuration.
    """
    config = load_config()

    if config.access_token is None and config.refresh_token is None:
        if json_output:
            print_json({"status": "success", "message": "Already logged out"})
        else:
            print_success("Already logged out")
        return

    # Try to logout on server if we have tokens
    if config.access_token:
        try:
            with SyftHubClient(
                base_url=config.hub_url, timeout=config.timeout
            ) as client:
                from syfthub_sdk import AuthTokens

                client.set_tokens(
                    AuthTokens(
                        access_token=config.access_token,
                        refresh_token=config.refresh_token or "",
                    )
                )
                client.logout()
        except Exception:
            # Ignore errors during server logout - we'll clear local tokens anyway
            pass

    # Clear local tokens
    clear_tokens()

    if json_output:
        print_json({"status": "success", "message": "Logged out"})
    else:
        print_success("Logged out successfully")
