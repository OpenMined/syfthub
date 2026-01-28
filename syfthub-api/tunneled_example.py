#!/usr/bin/env python3
"""
Tunneled Example - Demonstrates the tunneling mode of SyftAPI.

This script runs a Space in tunneling mode, where requests are received
via the message queue instead of HTTP. This enables operation behind
firewalls/NAT without a public IP address.

Usage:
    python tunneled_example.py

Environment variables (or set below):
    SYFTHUB_URL: URL of the SyftHub backend
    SYFTHUB_USERNAME: Username for authentication
    SYFTHUB_PASSWORD: Password for authentication
    SPACE_URL: Must be "tunneling:<username>" for tunnel mode
"""

import asyncio
import os

from syfthub_api import SyftAPI, Document, Message

# Configuration - User1 (the tunneled server)
SYFTHUB_URL = "https://syfthub-dev.openmined.org"
USERNAME = "tunnel_server_77xukh"
PASSWORD = "TestPass123!"

# Set environment variables
os.environ["SYFTHUB_URL"] = SYFTHUB_URL
os.environ["SYFTHUB_USERNAME"] = USERNAME
os.environ["SYFTHUB_PASSWORD"] = PASSWORD
os.environ["SPACE_URL"] = f"tunneling:{USERNAME}"  # Tunneling mode!

# Create the SyftAPI app
app = SyftAPI()


@app.on_startup
async def startup():
    """Called when the tunnel consumer starts."""
    print("=" * 60)
    print("Tunneled Space is starting up!")
    print(f"Listening for requests on queue for user: {USERNAME}")
    print("=" * 60)


@app.on_shutdown
async def shutdown():
    """Called when the tunnel consumer shuts down."""
    print("=" * 60)
    print("Tunneled Space is shutting down!")
    print("=" * 60)


@app.datasource(
    slug="sample-docs",
    name="Sample Documents",
    description="A sample data source that returns mock documents based on query"
)
async def search_documents(query: str) -> list[Document]:
    """Search for documents matching the query.

    This is a mock implementation that returns sample documents.
    In a real application, this would search a database or index.
    """
    print(f"\n>>> Received DATA_SOURCE request: query='{query}'")

    # Mock document results based on query
    documents = [
        Document(
            document_id=f"doc-{i}",
            content=f"This is document {i} matching query: '{query}'",
            metadata={"source": "tunneled_example", "query": query, "index": i},
            similarity_score=0.9 - (i * 0.1)
        )
        for i in range(1, 4)  # Return 3 documents
    ]

    print(f">>> Returning {len(documents)} documents")
    return documents


@app.model(
    slug="echo-model",
    name="Echo Model",
    description="A simple model that echoes the last message with a prefix"
)
async def echo_model(messages: list[Message]) -> str:
    """Process messages and return a response.

    This is a simple echo model that returns the last message
    with a prefix. In a real application, this would call an LLM.
    """
    print(f"\n>>> Received MODEL request: {len(messages)} messages")
    for i, msg in enumerate(messages):
        print(f"    [{i}] {msg.role}: {msg.content[:50]}...")

    # Get the last user message
    last_message = messages[-1].content if messages else "No message provided"

    response = f"[ECHO via TUNNEL] You said: {last_message}"
    print(f">>> Returning response: {response[:50]}...")

    return response


async def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("TUNNELED SYFTHUB SPACE EXAMPLE")
    print("=" * 60)
    print(f"SyftHub URL: {SYFTHUB_URL}")
    print(f"Username: {USERNAME}")
    print(f"Mode: TUNNELING (no HTTP server)")
    print("=" * 60 + "\n")

    # Run the app - in tunneling mode, this starts the MQ consumer
    # instead of an HTTP server
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
