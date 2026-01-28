# SyftHub API Framework

The `syfthub-api` is a Python framework that provides a simple, FastAPI-like interface for creating and deploying custom SyftAI Spaces. It allows you to define data source and model endpoints, and the framework handles the underlying web server, request/response formats, and synchronization with the SyftHub backend.

## Features

- **Declarative Endpoints**: Use simple decorators (`@app.datasource` and `@app.model`) to define your endpoints.
- **FastAPI-like**: Enjoy a familiar developer experience if you've used FastAPI.
- **Automatic Sync**: Endpoints are automatically registered with your SyftHub account on startup.
- **Type Hinting**: Fully type-hinted for better editor support and code quality.
- **Async Support**: Built for modern asynchronous Python.

## Installation

The framework is designed to be used within the SyftHub monorepo. The dependencies can be installed using `uv`.

```bash
# From within the syfthub-api directory
uv venv
source .venv/bin/activate
uv pip install -e .
uv pip install -e ../sdk/python
```

## Quick Start

Here is a simple example of a SyftAI Space with one data source and one model.

### 1. Set up your Environment

Before running your space, you need to configure your environment variables:

```bash
# The URL of your SyftHub backend instance
export SYFTHUB_URL="http://localhost:8080"

# Your SyftHub username and password
export SYFTHUB_USERNAME="your-syfthub-username"
export SYFTHUB_PASSWORD="your-syfthub-password"

# The publicly accessible URL of your SyftAI Space.
# This must match the host and port you run the space on.
export SPACE_URL="http://localhost:8001"
```

### 2. Create your Space file

Create a Python file (e.g., `main.py`):

```python
import asyncio
from syfthub_api.app import SyftAPI
from syfthub_api.schemas import Document, Message

# Initialize the SyftAI Space application
app = SyftAPI()

# In-memory data store for the example
DUMMY_PAPERS = {
    "paper-1": "Attention is All You Need...",
    "paper-2": "BERT: Pre-training of Deep Bidirectional Transformers...",
}

@app.datasource(
    slug="scientific-papers",
    name="Scientific Papers",
    description="A collection of important scientific papers.",
)
async def search_papers(query: str) -> list[Document]:
    """
    A simple data source that performs a keyword search.
    """
    print(f"Received query for papers: {query}")
    results = []
    for doc_id, content in DUMMY_PAPERS.items():
        if query.lower() in content.lower():
            results.append(
                Document(
                    document_id=doc_id,
                    content=content,
                    metadata={"source": "dummy_db"},
                    similarity_score=0.9,
                )
            )
    return results

@app.model(
    slug="echo-model",
    name="Echo Model",
    description="A simple model that echoes the last user message.",
)
async def echo_model(messages: list[Message]) -> str:
    """
    A simple model that returns the content of the last user message.
    """
    last_user_message = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_message = msg.content
            break
    return f"Echo: {last_user_message}"

async def main() -> None:
    # The SDK will automatically use environment variables for configuration.
    # Uvicorn will be started on 0.0.0.0:8001
    await app.run(host="0.0.0.0", port=8001)

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. Run your Space

From your terminal, run the application:

```bash
uv run python main.py
```

When the server starts, it will first connect to SyftHub to sync your endpoints. You will see a confirmation message in the console. Your SyftAI Space is now running and ready to be used in SyftHub chat.

## How It Works

The `SyftAPI` object acts as a registry for your endpoints.

- When you decorate a function with `@app.datasource` or `@app.model`, it's added to a list of endpoints to be created.
- When you call `app.run()`, two main things happen:
    1.  **Sync with SyftHub**: The SDK uses the `syfthub-sdk` to send a list of all your defined endpoints to the SyftHub backend. The backend then updates your user's endpoint registry. The `connect` URL for each endpoint is set to the `SPACE_URL` you provided.
    2.  **Start the Server**: The SDK builds a FastAPI application in the background. It creates the appropriate API routes (`/api/v1/endpoints/{slug}/query`) for each of your registered functions. It then starts a `uvicorn` server to listen for requests from the SyftHub Aggregator.

The framework handles the complexity of parsing incoming requests from the aggregator and formatting the responses from your functions into the structure that the aggregator expects. You only need to focus on the core logic of your data source or model.
