"""Query command for SyftHub CLI."""

from __future__ import annotations

from typing import Annotated

import typer

from syfthub_cli.completion import (
    complete_aggregator_alias,
    complete_data_source,
    complete_model_endpoint,
)
from syfthub_cli.config import load_config
from syfthub_cli.output import (
    console,
    print_error,
    print_json,
    print_streaming_done,
    print_streaming_token,
)
from syfthub_sdk import (
    AuthTokens,
    ChatError,
    DoneEvent,
    ErrorEvent,
    GenerationStartEvent,
    RetrievalCompleteEvent,
    RetrievalStartEvent,
    SourceCompleteEvent,
    SyftHubClient,
    TokenEvent,
)


def query(
    target: Annotated[
        str,
        typer.Argument(
            help="Target model endpoint (e.g., 'username/model-name').",
            autocompletion=complete_model_endpoint,
        ),
    ],
    prompt: Annotated[
        str,
        typer.Argument(help="Query prompt."),
    ],
    source: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-s",
            help="Data source endpoints to query. Can be specified multiple times.",
            autocompletion=complete_data_source,
        ),
    ] = None,
    aggregator: Annotated[
        str | None,
        typer.Option(
            "--aggregator",
            "-a",
            help="Aggregator alias or URL to use.",
            autocompletion=complete_aggregator_alias,
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option("--top-k", "-k", help="Number of documents to retrieve."),
    ] = 5,
    max_tokens: Annotated[
        int,
        typer.Option("--max-tokens", "-m", help="Maximum tokens in response."),
    ] = 1024,
    temperature: Annotated[
        float,
        typer.Option("--temperature", "-t", help="Sampling temperature (0.0-2.0)."),
    ] = 0.7,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Show retrieval progress."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output result as JSON (non-streaming)."),
    ] = False,
) -> None:
    """Query endpoints using RAG.

    Sends a query to a model endpoint, optionally retrieving context from
    data source endpoints.

    Examples:

        syft query alice/gpt4 "What is machine learning?"

        syft query alice/gpt4 --source bob/docs "Explain the API"

        syft query alice/gpt4 -s bob/docs -s carol/data "Compare approaches"
    """
    config = load_config()

    # Resolve aggregator URL
    aggregator_url = config.get_aggregator_url(aggregator)

    try:
        client = SyftHubClient(
            base_url=config.hub_url,
            timeout=config.timeout,
            aggregator_url=aggregator_url,
        )

        # Set tokens if available
        if config.access_token:
            client.set_tokens(
                AuthTokens(
                    access_token=config.access_token,
                    refresh_token=config.refresh_token or "",
                )
            )

        with client:
            if json_output:
                _query_complete(
                    client,
                    target,
                    prompt,
                    source or [],
                    top_k,
                    max_tokens,
                    temperature,
                    aggregator_url,
                )
            else:
                _query_stream(
                    client,
                    target,
                    prompt,
                    source or [],
                    top_k,
                    max_tokens,
                    temperature,
                    aggregator_url,
                    verbose,
                )

    except ChatError as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(str(e))
        raise typer.Exit(1) from None
    except Exception as e:
        if json_output:
            print_json({"status": "error", "message": str(e)})
        else:
            print_error(f"Query failed: {e}")
        raise typer.Exit(1) from None


def _query_complete(
    client: SyftHubClient,
    target: str,
    prompt: str,
    sources: list[str],
    top_k: int,
    max_tokens: int,
    temperature: float,
    aggregator_url: str | None,
) -> None:
    """Execute query and return complete JSON response."""
    response = client.chat.complete(
        prompt=prompt,
        model=target,
        data_sources=sources if sources else None,  # type: ignore[arg-type]
        top_k=top_k,
        max_tokens=max_tokens,
        temperature=temperature,
        aggregator_url=aggregator_url,
    )

    print_json(
        {
            "status": "success",
            "response": response.response,
            "sources": [
                {
                    "title": title,
                    "slug": doc.slug,
                }
                for title, doc in response.sources.items()
            ]
            if response.sources
            else [],
            "retrieval_info": [
                {
                    "path": info.path,
                    "documents_retrieved": info.documents_retrieved,
                    "status": info.status.value,
                }
                for info in response.retrieval_info
            ]
            if response.retrieval_info
            else [],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens
                if response.usage
                else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        }
    )


def _query_stream(
    client: SyftHubClient,
    target: str,
    prompt: str,
    sources: list[str],
    top_k: int,
    max_tokens: int,
    temperature: float,
    aggregator_url: str | None,
    verbose: bool,
) -> None:
    """Execute query with streaming output."""
    stream = client.chat.stream(
        prompt=prompt,
        model=target,
        data_sources=sources if sources else None,  # type: ignore[arg-type]
        top_k=top_k,
        max_tokens=max_tokens,
        temperature=temperature,
        aggregator_url=aggregator_url,
    )

    for event in stream:
        if isinstance(event, RetrievalStartEvent):
            if verbose:
                console.print("[dim]Retrieving from sources...[/dim]")

        elif isinstance(event, SourceCompleteEvent):
            if verbose:
                console.print(
                    f"[dim]  Retrieved {event.documents_retrieved} docs from {event.path}[/dim]"
                )

        elif isinstance(event, RetrievalCompleteEvent):
            if verbose:
                console.print(
                    f"[dim]Retrieved {event.total_documents} documents total[/dim]"
                )
                console.print()

        elif isinstance(event, GenerationStartEvent):
            if verbose:
                console.print("[dim]Generating response...[/dim]")

        elif isinstance(event, TokenEvent):
            print_streaming_token(event.content)

        elif isinstance(event, DoneEvent):
            print_streaming_done()

        elif isinstance(event, ErrorEvent):
            print_streaming_done()
            print_error(event.message)
            raise typer.Exit(1)
