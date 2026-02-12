#!/usr/bin/env python3
"""
NATS-tunneled SyftHub Space — serves endpoints via a NATS pub/sub tunnel.

This example shows how to run a SyftAI Space behind a NATS tunnel.
Instead of receiving HTTP requests directly, the space connects to
the SyftHub NATS server and listens for requests on a pub/sub channel.
This is useful when the space cannot be reached directly over HTTP
(e.g. running behind NAT, a firewall, or on a local machine).

Configuration is loaded from a .env file alongside this script.

Required .env variables:
    SYFTHUB_URL      — URL of the SyftHub instance
    SYFTHUB_USERNAME — Your SyftHub username
    SYFTHUB_PASSWORD — Your SyftHub password
    SPACE_URL        — Must be "tunneling:<username>" to enable tunnel mode

Usage:
    python examples/nats_server.py
"""

import asyncio
from pathlib import Path

# Load .env before anything else
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from syfthub_api import SyftAPI, UserContext, Document, Message

app = SyftAPI()


@app.on_startup
async def startup():
    print("Space is online — listening for requests via tunnel.")


@app.on_shutdown
async def shutdown():
    print("Space is shutting down.")


# ── Data Source Endpoint ─────────────────────────────────────────────
@app.datasource(
    slug="sample-docs",
    name="Sample Documents",
    description="Returns mock documents matching a query.",
)
async def search_documents(query: str, user: UserContext) -> list[Document]:
    print(f"[datasource] query={query!r} from {user.username} ({user.email})")
    return [
        Document(
            document_id=f"doc-{i}",
            content=f"Document {i} about: {query}",
            metadata={"source": "sample", "index": i},
            similarity_score=round(0.95 - i * 0.1, 2),
        )
        for i in range(3)
    ]


# ── Model Endpoint ───────────────────────────────────────────────────
@app.model(
    slug="echo-model",
    name="Echo Model",
    description="Echoes the last user message back.",
)
async def echo_model(messages: list[Message], user: UserContext) -> str:
    print(f"[model] received {len(messages)} message(s) from {user.username} ({user.email})")
    last = next(
        (m.content for m in reversed(messages) if m.role == "user"),
        "(no user message)",
    )
    return f"Echo: {last}"


async def main():
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
