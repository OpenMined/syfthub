#!/usr/bin/env python3
"""
Tunneled SyftHub Space — one data source + one model endpoint.

Reads configuration from .env file and connects to SyftHub via NATS tunnel.

Usage:
    python server.py
"""

import asyncio
from pathlib import Path

# Load .env before anything else
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from syfthub_api import SyftAPI, AuthenticatedUser, Document, Message

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
@app.authenticated
async def search_documents(query: str, user: AuthenticatedUser) -> list[Document]:
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
@app.authenticated
async def echo_model(messages: list[Message], user: AuthenticatedUser) -> str:
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
