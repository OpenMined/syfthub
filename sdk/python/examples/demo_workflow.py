#!/usr/bin/env python3
"""Demo script: Login, RAG Query, and Accounting Balance Check.

This script demonstrates a complete SyftHub SDK workflow:
1. Login with username/password
2. Query a model using data sources (RAG)
3. Check accounting balance

Usage:
    # Using environment variables
    export SYFTHUB_URL="https://hub.syft.com"
    export SYFTHUB_ACCOUNTING_URL="https://accounting.syft.com"
    export SYFTHUB_ACCOUNTING_EMAIL="your@email.com"
    export SYFTHUB_ACCOUNTING_PASSWORD="your-accounting-password"

    python demo_workflow.py --username alice --password secret123 \
        --model "owner/model-slug" \
        --data-sources "owner1/docs,owner2/knowledge-base" \
        --prompt "What is machine learning?"

    # Or with explicit URLs
    python demo_workflow.py --base-url https://hub.syft.com \
        --username alice --password secret123 \
        --model "owner/model-slug" \
        --prompt "Explain neural networks"
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import NoReturn

from syfthub_sdk import (
    AuthenticationError,
    ChatResponse,
    ConfigurationError,
    EndpointResolutionError,
    SyftHubClient,
    SyftHubError,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SyftHub SDK Demo: Login, RAG Query, and Accounting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage with model and data sources
    python demo_workflow.py -u alice -p secret123 \\
        --model "bob/gpt-model" \\
        --data-sources "carol/docs,dave/tutorials" \\
        --prompt "What is Python?"

    # Streaming mode
    python demo_workflow.py -u alice -p secret123 \\
        --model "bob/gpt-model" \\
        --prompt "Explain AI" \\
        --stream

    # Skip accounting check
    python demo_workflow.py -u alice -p secret123 \\
        --model "bob/gpt-model" \\
        --prompt "Hello" \\
        --skip-accounting
        """,
    )

    # Connection settings
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SYFTHUB_URL"),
        help="SyftHub API URL (or set SYFTHUB_URL env var)",
    )

    # Authentication
    parser.add_argument(
        "-u", "--username",
        required=True,
        help="Username or email for login",
    )
    parser.add_argument(
        "-p", "--password",
        required=True,
        help="Password for login",
    )

    # Chat parameters
    parser.add_argument(
        "--model",
        required=True,
        help="Model endpoint path (e.g., 'owner/model-slug')",
    )
    parser.add_argument(
        "--data-sources",
        default="",
        help="Comma-separated data source paths (e.g., 'owner1/docs,owner2/kb')",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="The prompt/question to send to the model",
    )

    # Chat options
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of documents to retrieve per source (default: 5)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Maximum tokens to generate (default: 1024)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Generation temperature (default: 0.7)",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming mode for response",
    )

    # Accounting
    parser.add_argument(
        "--skip-accounting",
        action="store_true",
        help="Skip the accounting balance check",
    )

    return parser.parse_args()


def print_header(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_error(message: str) -> NoReturn:
    """Print error message and exit."""
    print(f"\nError: {message}", file=sys.stderr)
    sys.exit(1)


def login(client: SyftHubClient, username: str, password: str) -> None:
    """Perform login and display user info."""
    print_header("Step 1: Authentication")

    print(f"Logging in as: {username}")

    try:
        user = client.auth.login(username=username, password=password)
        print(f"Login successful!")
        print(f"  User ID: {user.id}")
        print(f"  Username: {user.username}")
        print(f"  Email: {user.email}")
        print(f"  Full Name: {user.full_name}")
        print(f"  Role: {user.role.value}")
        print(f"  Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    except AuthenticationError as e:
        print_error(f"Login failed: {e.message}")


def query_model_complete(
    client: SyftHubClient,
    model: str,
    data_sources: list[str],
    prompt: str,
    top_k: int,
    max_tokens: int,
    temperature: float,
) -> None:
    """Query model using complete (non-streaming) mode."""
    print("Sending request to aggregator...")
    print(f"  Model: {model}")
    if data_sources:
        print(f"  Data Sources: {', '.join(data_sources)}")
    print(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print()

    try:
        response: ChatResponse = client.chat.complete(
            prompt=prompt,
            model=model,
            data_sources=data_sources if data_sources else None,
            top_k=top_k,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        print("Response:")
        print("-" * 40)
        print(response.response)
        print("-" * 40)

        # Display sources used
        if response.sources:
            print("\nSources Used:")
            for source in response.sources:
                status_icon = "+" if source.status.value == "success" else "!"
                print(f"  [{status_icon}] {source.path}: {source.documents_retrieved} docs")
                if source.error_message:
                    print(f"      Error: {source.error_message}")

        # Display metadata
        print("\nPerformance Metrics:")
        print(f"  Retrieval Time: {response.metadata.retrieval_time_ms}ms")
        print(f"  Generation Time: {response.metadata.generation_time_ms}ms")
        print(f"  Total Time: {response.metadata.total_time_ms}ms")

        # Display token usage if available
        if response.usage:
            print("\nToken Usage:")
            print(f"  Prompt Tokens: {response.usage.prompt_tokens}")
            print(f"  Completion Tokens: {response.usage.completion_tokens}")
            print(f"  Total Tokens: {response.usage.total_tokens}")

    except EndpointResolutionError as e:
        print_error(f"Failed to resolve endpoint '{e.endpoint_path}': {e.message}")
    except SyftHubError as e:
        print_error(f"Chat request failed: {e.message}")


def query_model_stream(
    client: SyftHubClient,
    model: str,
    data_sources: list[str],
    prompt: str,
    top_k: int,
    max_tokens: int,
    temperature: float,
) -> None:
    """Query model using streaming mode."""
    print("Streaming request to aggregator...")
    print(f"  Model: {model}")
    if data_sources:
        print(f"  Data Sources: {', '.join(data_sources)}")
    print(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print()

    try:
        print("Response:")
        print("-" * 40)

        sources_info = []
        metadata = None

        for event in client.chat.stream(
            prompt=prompt,
            model=model,
            data_sources=data_sources if data_sources else None,
            top_k=top_k,
            max_tokens=max_tokens,
            temperature=temperature,
        ):
            if event.type == "retrieval_start":
                print(f"[Retrieving from {event.source_count} sources...]", end="\r")

            elif event.type == "source_complete":
                # Clear the retrieval message
                print(" " * 50, end="\r")

            elif event.type == "retrieval_complete":
                print(f"[Retrieved {event.total_documents} docs in {event.time_ms}ms]")
                print()

            elif event.type == "generation_start":
                pass  # Model starting, output will follow

            elif event.type == "token":
                print(event.content, end="", flush=True)

            elif event.type == "done":
                sources_info = event.sources
                metadata = event.metadata
                print()  # Newline after streaming content

            elif event.type == "error":
                print(f"\n[ERROR: {event.message}]")

        print("-" * 40)

        # Display sources used
        if sources_info:
            print("\nSources Used:")
            for source in sources_info:
                status_icon = "+" if source.status.value == "success" else "!"
                print(f"  [{status_icon}] {source.path}: {source.documents_retrieved} docs")
                if source.error_message:
                    print(f"      Error: {source.error_message}")

        # Display metadata
        if metadata:
            print("\nPerformance Metrics:")
            print(f"  Retrieval Time: {metadata.retrieval_time_ms}ms")
            print(f"  Generation Time: {metadata.generation_time_ms}ms")
            print(f"  Total Time: {metadata.total_time_ms}ms")

    except EndpointResolutionError as e:
        print_error(f"Failed to resolve endpoint '{e.endpoint_path}': {e.message}")
    except SyftHubError as e:
        print_error(f"Chat request failed: {e.message}")


def chat_query(
    client: SyftHubClient,
    model: str,
    data_sources: list[str],
    prompt: str,
    top_k: int,
    max_tokens: int,
    temperature: float,
    stream: bool,
) -> None:
    """Perform RAG chat query."""
    print_header("Step 2: RAG Chat Query")

    if stream:
        query_model_stream(
            client, model, data_sources, prompt,
            top_k, max_tokens, temperature,
        )
    else:
        query_model_complete(
            client, model, data_sources, prompt,
            top_k, max_tokens, temperature,
        )


def check_accounting(client: SyftHubClient) -> None:
    """Check accounting balance."""
    print_header("Step 3: Accounting Balance")

    if not client.accounting.is_configured:
        print("Accounting service not configured.")
        print("Set SYFTHUB_ACCOUNTING_URL, SYFTHUB_ACCOUNTING_EMAIL,")
        print("and SYFTHUB_ACCOUNTING_PASSWORD environment variables.")
        return

    try:
        user = client.accounting.get_user()
        print(f"Account ID: {user.id}")
        print(f"Email: {user.email}")
        print(f"Balance: {user.balance:.2f} credits")
        if user.organization:
            print(f"Organization: {user.organization}")

        # Show recent transactions
        print("\nRecent Transactions:")
        transactions = client.accounting.get_transactions().take(5)
        if transactions:
            for tx in transactions:
                direction = "+" if tx.recipient_email == user.email else "-"
                status_icon = {"pending": "?", "completed": "+", "cancelled": "x"}.get(
                    tx.status.value, "?"
                )
                print(
                    f"  [{status_icon}] {direction}{tx.amount:.2f} "
                    f"({tx.sender_email} -> {tx.recipient_email}) "
                    f"@ {tx.created_at.strftime('%Y-%m-%d %H:%M')}"
                )
        else:
            print("  No transactions found.")

    except ConfigurationError as e:
        print(f"Configuration error: {e.message}")
    except SyftHubError as e:
        print(f"Failed to fetch accounting info: {e.message}")


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Validate base URL
    if not args.base_url:
        print_error(
            "SyftHub URL not configured. "
            "Either pass --base-url or set SYFTHUB_URL environment variable."
        )

    # Parse data sources
    data_sources = [
        ds.strip() for ds in args.data_sources.split(",") if ds.strip()
    ]

    print(f"Connecting to: {args.base_url}")

    # Use context manager for proper cleanup
    with SyftHubClient(base_url=args.base_url) as client:
        # Step 1: Login
        login(client, args.username, args.password)

        # Step 2: RAG Chat Query
        chat_query(
            client=client,
            model=args.model,
            data_sources=data_sources,
            prompt=args.prompt,
            top_k=args.top_k,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            stream=args.stream,
        )

        # Step 3: Accounting Balance (optional)
        if not args.skip_accounting:
            check_accounting(client)

    print_header("Complete")
    print("Demo workflow finished successfully!")


if __name__ == "__main__":
    main()
