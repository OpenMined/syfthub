"""Utility commands for SyftHub CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from syfthub_cli.config import load_config
from syfthub_cli.output import console, print_error, print_json, print_success
from syfthub_sdk import AuthTokens, SyftHubClient

# Shell completion scripts
BASH_COMPLETION = """\
# SyftHub CLI completion for Bash
_syft_completion() {
    local IFS=$'\\n'
    COMPREPLY=( $(env COMP_WORDS="${COMP_WORDS[*]}" \\
                     COMP_CWORD=$COMP_CWORD \\
                     _SYFT_COMPLETE=complete_bash \\
                     syft 2>/dev/null) )
    return 0
}

complete -o default -F _syft_completion syft
"""

ZSH_COMPLETION = """\
#compdef syft

_syft() {
    local -a completions
    local -a completions_with_descriptions
    local -a response
    response=("${(@f)$(env COMP_WORDS="${words[*]}" \\
                          COMP_CWORD=$((CURRENT-1)) \\
                          _SYFT_COMPLETE=complete_zsh \\
                          syft 2>/dev/null)}")

    for key descr in ${(kv)response}; do
        if [[ "$descr" == "_" ]]; then
            completions+=("$key")
        else
            completions_with_descriptions+=("$key":"$descr")
        fi
    done

    if [ -n "$completions_with_descriptions" ]; then
        _describe -V unsorted completions_with_descriptions -U
    fi

    if [ -n "$completions" ]; then
        compadd -U -V unsorted -a completions
    fi
}

compdef _syft syft
"""

FISH_COMPLETION = """\
function _syft_completion
    set -l response (env _SYFT_COMPLETE=complete_fish COMP_WORDS=(commandline -cp) \\
                        COMP_CWORD=(commandline -t) syft 2>/dev/null)
    for completion in $response
        echo $completion
    end
end

complete -c syft -f -a "(_syft_completion)"
"""


def whoami(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON."),
    ] = False,
) -> None:
    """Show current authenticated user.

    Displays the username and email of the currently logged-in user.
    """
    config = load_config()

    if not config.access_token:
        if json_output:
            print_json({"status": "error", "message": "Not logged in"})
        else:
            print_error("Not logged in. Use 'syft login' to authenticate.")
        raise typer.Exit(1)

    try:
        with SyftHubClient(base_url=config.hub_url, timeout=config.timeout) as client:
            client.set_tokens(
                AuthTokens(
                    access_token=config.access_token,
                    refresh_token=config.refresh_token or "",
                )
            )
            user = client.me()

            if json_output:
                print_json(
                    {
                        "status": "success",
                        "user": {
                            "id": str(user.id),
                            "username": user.username,
                            "email": user.email,
                        },
                    }
                )
            else:
                console.print(f"[bold cyan]{user.username}[/bold cyan]")
                console.print(f"[dim]Email:[/dim] {user.email}")
                console.print(f"[dim]ID:[/dim] {user.id}")

    except Exception as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(f"Failed to get user info: {e}")
        raise typer.Exit(1) from None


# Create sub-app for completion commands
completion_app = typer.Typer(no_args_is_help=True)


@completion_app.command("bash")
def completion_bash() -> None:
    """Generate Bash completion script.

    Usage:
        syft completion bash >> ~/.bashrc
        # or
        syft completion bash > /etc/bash_completion.d/syft
    """
    typer.echo(BASH_COMPLETION)


@completion_app.command("zsh")
def completion_zsh() -> None:
    """Generate Zsh completion script.

    Usage:
        syft completion zsh >> ~/.zshrc
        # or
        syft completion zsh > ~/.zsh/completions/_syft
    """
    typer.echo(ZSH_COMPLETION)


@completion_app.command("fish")
def completion_fish() -> None:
    """Generate Fish completion script.

    Usage:
        syft completion fish > ~/.config/fish/completions/syft.fish
    """
    typer.echo(FISH_COMPLETION)


@completion_app.command("install")
def completion_install(
    shell: Annotated[
        str | None,
        typer.Argument(help="Shell to install completion for (bash, zsh, fish)."),
    ] = None,
) -> None:
    """Install shell completion for the current shell.

    Detects the current shell and prints installation instructions.
    """
    import os

    # Detect shell if not provided
    if shell is None:
        shell_path = os.environ.get("SHELL", "")
        if "bash" in shell_path:
            shell = "bash"
        elif "zsh" in shell_path:
            shell = "zsh"
        elif "fish" in shell_path:
            shell = "fish"
        else:
            print_error(
                "Could not detect shell. Please specify: syft completion install bash|zsh|fish"
            )
            raise typer.Exit(1)

    shell = shell.lower()

    if shell == "bash":
        console.print("[bold]Bash completion installation:[/bold]")
        console.print()
        console.print("Add to ~/.bashrc:")
        console.print('[dim]  eval "$(syft completion bash)"[/dim]')
        console.print()
        console.print("Or save to a file:")
        console.print("[dim]  syft completion bash > ~/.bash_completions/syft.sh[/dim]")
        console.print(
            "[dim]  echo 'source ~/.bash_completions/syft.sh' >> ~/.bashrc[/dim]"
        )

    elif shell == "zsh":
        console.print("[bold]Zsh completion installation:[/bold]")
        console.print()
        console.print("Add to ~/.zshrc:")
        console.print('[dim]  eval "$(syft completion zsh)"[/dim]')
        console.print()
        console.print("Or save to completions directory:")
        console.print("[dim]  syft completion zsh > ~/.zsh/completions/_syft[/dim]")

    elif shell == "fish":
        console.print("[bold]Fish completion installation:[/bold]")
        console.print()
        console.print("Save to completions directory:")
        console.print(
            "[dim]  syft completion fish > ~/.config/fish/completions/syft.fish[/dim]"
        )

    else:
        print_error(f"Unknown shell: {shell}. Supported: bash, zsh, fish")
        raise typer.Exit(1)

    console.print()
    print_success(f"Run the command above to enable {shell} completion.")
