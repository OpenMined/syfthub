# SyftHub Aggregator

RAG (Retrieval-Augmented Generation) orchestration service for SyftHub.

## Overview

The aggregator service coordinates the chat workflow by:

1. Receiving user prompts with model and data source selections
2. Querying data sources for relevant context (in parallel)
3. Building an augmented prompt with retrieved context
4. Calling the model endpoint
5. Streaming/returning the response

## Architecture

```
Frontend Request
      │
      ▼
┌─────────────────────────────────────────┐
│            AGGREGATOR                    │
│                                          │
│  1. Resolve paths → URLs via SyftHub    │
│  2. Query data sources (parallel)        │
│  3. Build RAG prompt                     │
│  4. Call model endpoint                  │
│  5. Stream response back                 │
└─────────────────────────────────────────┘
```

## API

### POST /api/v1/chat

Non-streaming chat completion with RAG context.

**Request:**
```json
{
  "prompt": "What are the key features?",
  "model": "owner/model-slug",
  "data_sources": ["owner/datasource-1", "owner/datasource-2"],
  "top_k": 5
}
```

**Response:**
```json
{
  "response": "Based on the context...",
  "sources": [
    {"path": "owner/datasource-1", "documents_retrieved": 5, "status": "success"}
  ],
  "metadata": {
    "retrieval_time_ms": 150,
    "generation_time_ms": 2000,
    "total_time_ms": 2150
  }
}
```

### POST /api/v1/chat/stream

Streaming chat with Server-Sent Events.

**Events:**
- `retrieval_start` - Starting data source queries
- `source_complete` - One data source finished
- `retrieval_complete` - All sources done
- `generation_start` - Starting model generation
- `token` - Response chunk
- `done` - Complete with metadata
- `error` - Error occurred

## Configuration

Environment variables (prefix: `AGGREGATOR_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SYFTHUB_URL` | `http://localhost:8000` | SyftHub backend URL |
| `DEBUG` | `false` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8001` | Server port |
| `RETRIEVAL_TIMEOUT` | `30.0` | Timeout for data source queries (seconds) |
| `GENERATION_TIMEOUT` | `120.0` | Timeout for model generation (seconds) |
| `DEFAULT_TOP_K` | `5` | Default documents per source |
| `MAX_TOP_K` | `20` | Maximum documents per source |
| `MAX_DATA_SOURCES` | `10` | Maximum data sources per request |

## Development

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
cd aggregator

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run the server
uvicorn aggregator.main:app --reload --port 8001
```

### Docker

```bash
# Build and run standalone
docker compose up --build

# Or with the main SyftHub stack
cd .. && docker compose -f docker-compose.dev.yml up --build
```

### Testing

```bash
uv run pytest tests/ -v
```

## Endpoint Interfaces

### Data Source Interface

Data sources must implement:

```
POST /query
Request: {"query": "...", "top_k": 5}
Response: {"documents": [{"content": "...", "score": 0.9, "metadata": {...}}]}
```

### Model Interface

Models must implement:

```
POST /chat
Request: {"messages": [{"role": "user", "content": "..."}], "stream": false}
Response: {"message": {"role": "assistant", "content": "..."}}
```

For streaming:
```
POST /chat
Request: {"messages": [...], "stream": true}
Response: SSE stream with data: {"content": "..."} chunks
```
