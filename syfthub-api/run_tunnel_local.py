#!/usr/bin/env python3
"""
Run a tunneled SyftAI Space against the local dev stack.

This connects to the locally deployed SyftHub (docker-compose.dev.yml)
and registers one model endpoint and one data source endpoint, then
listens for requests via NATS pub/sub.

The NATS WebSocket URL is derived from SYFTHUB_URL (http://localhost:8080
-> ws://localhost:8080/nats) and the auth token is fetched from the hub
after login. No separate NATS env vars are needed.
"""

import asyncio
import os

from syfthub_api import SyftAPI, Document, Message

# Local dev stack configuration
SYFTHUB_URL = "http://localhost:8080"
USERNAME = "tunnel_test"
PASSWORD = "TunnelPass123!"

os.environ["SYFTHUB_URL"] = SYFTHUB_URL
os.environ["SYFTHUB_USERNAME"] = USERNAME
os.environ["SYFTHUB_PASSWORD"] = PASSWORD
os.environ["SPACE_URL"] = f"tunneling:{USERNAME}"

app = SyftAPI(log_level="DEBUG")


@app.on_startup
async def startup():
    print("=" * 60)
    print("TUNNELED SPACE IS READY")
    print(f"User: {USERNAME}")
    print(f"NATS subject: syfthub.spaces.{USERNAME}")
    print("Endpoints:")
    print("  - data_source: knowledge-base")
    print("  - model: echo-assistant")
    print("=" * 60)


@app.on_shutdown
async def shutdown():
    print("Tunneled space shutting down.")


# ---------------------------------------------------------------------------
# Data source endpoint
# ---------------------------------------------------------------------------
@app.datasource(
    slug="knowledge-base",
    name="Knowledge Base",
    description="A sample knowledge base with facts about Python and AI",
)
async def search_knowledge(query: str) -> list[Document]:
    """Return documents matching the query from a small in-memory corpus."""
    print(f"[knowledge-base] query='{query}'")

    corpus = [
        {
            "id": "py-1",
            "text": "Python is a high-level, interpreted programming language created by Guido van Rossum in 1991. It emphasises readability and simplicity.",
            "tags": ["python", "programming", "language"],
        },
        {
            "id": "py-2",
            "text": "Python supports multiple paradigms including procedural, object-oriented, and functional programming. Its standard library is extensive.",
            "tags": ["python", "paradigms", "stdlib"],
        },
        {
            "id": "ai-1",
            "text": "Machine learning is a subset of artificial intelligence that enables systems to learn patterns from data without being explicitly programmed.",
            "tags": ["ai", "machine learning"],
        },
        {
            "id": "ai-2",
            "text": "Neural networks are computing systems inspired by biological neural networks. Deep learning uses neural networks with many layers.",
            "tags": ["ai", "neural networks", "deep learning"],
        },
        {
            "id": "ai-3",
            "text": "Large language models (LLMs) like GPT are trained on vast text corpora and can generate human-like text, translate languages, and answer questions.",
            "tags": ["ai", "llm", "gpt"],
        },
    ]

    query_lower = query.lower()
    results = []
    for doc in corpus:
        # Simple keyword matching for scoring
        text_lower = doc["text"].lower()
        tag_match = any(tag in query_lower for tag in doc["tags"])
        word_overlap = sum(1 for w in query_lower.split() if w in text_lower)
        score = min(1.0, (word_overlap * 0.2) + (0.3 if tag_match else 0.0))

        if score > 0.0:
            results.append(
                Document(
                    document_id=doc["id"],
                    content=doc["text"],
                    metadata={"tags": doc["tags"]},
                    similarity_score=round(score, 2),
                )
            )

    # Sort by score descending, return top 3
    results.sort(key=lambda d: d.similarity_score, reverse=True)
    results = results[:3]

    print(f"[knowledge-base] returning {len(results)} documents")
    return results


# ---------------------------------------------------------------------------
# Model endpoint
# ---------------------------------------------------------------------------
@app.model(
    slug="echo-assistant",
    name="Echo Assistant",
    description="A simple model that summarises the conversation and echoes it back",
)
async def echo_assistant(messages: list[Message]) -> str:
    """Process messages and return a response summarising the input."""
    print(f"[echo-assistant] received {len(messages)} messages")

    # Build a simple response from the conversation
    parts = []
    for msg in messages:
        role = msg.role.upper()
        content = msg.content
        if len(content) > 200:
            content = content[:200] + "..."
        parts.append(f"[{role}] {content}")

    summary = "\n".join(parts)
    response = (
        f"[Echo Assistant via NATS Tunnel]\n"
        f"Received {len(messages)} message(s).\n\n"
        f"--- Conversation ---\n{summary}\n--- End ---"
    )

    print(f"[echo-assistant] responding ({len(response)} chars)")
    return response


async def main():
    print()
    print("=" * 60)
    print("LOCAL TUNNELED SYFTHUB SPACE")
    print("=" * 60)
    print(f"SyftHub: {SYFTHUB_URL}")
    print(f"User:    {USERNAME}")
    print(f"Mode:    TUNNELING + NATS")
    print("=" * 60)
    print()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
