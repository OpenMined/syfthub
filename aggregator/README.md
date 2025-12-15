# SyftHub Aggregator

RAG (Retrieval-Augmented Generation) orchestration service for SyftHub, designed to work with SyftAI-Space endpoints.

## Overview

The aggregator service coordinates the chat workflow by:

1. Receiving user prompts with model and data source endpoint references
2. Querying SyftAI-Space data source endpoints for relevant context (in parallel)
3. Building an augmented prompt with retrieved context
4. Calling the SyftAI-Space model endpoint
5. Streaming/returning the response

**Key Feature:** The aggregator is **stateless** - all required connection information (URLs, slugs, tenant names, user email) is provided in each request.

## Architecture

```
External Service (e.g., Frontend)
      │
      │ ChatRequest with:
      │ - user_email
      │ - model: {url, slug, tenant_name}
      │ - data_sources: [{url, slug, tenant_name}, ...]
      ▼
┌─────────────────────────────────────────┐
│            AGGREGATOR                    │
│                                          │
│  1. Query SyftAI-Space data sources     │
│     POST {url}/api/v1/endpoints/{slug}/query
│  2. Build RAG prompt with context        │
│  3. Call SyftAI-Space model endpoint    │
│     POST {url}/api/v1/endpoints/{slug}/query
│  4. Stream response back                 │
└─────────────────────────────────────────┘
      │
      ▼
  SyftAI-Space Instances
```

## API

### POST /api/v1/chat

Non-streaming chat completion with RAG context.

**Request:**
```json
{
  "prompt": "What are the key features?",
  "user_email": "user@example.com",
  "model": {
    "url": "http://syftai-space-1:8080",
    "slug": "gpt-model",
    "name": "GPT Model",
    "tenant_name": "acme-corp"
  },
  "data_sources": [
    {
      "url": "http://syftai-space-1:8080",
      "slug": "docs-dataset",
      "name": "Documentation",
      "tenant_name": "acme-corp"
    },
    {
      "url": "http://syftai-space-2:8080",
      "slug": "wiki-dataset",
      "name": "Wiki",
      "tenant_name": null
    }
  ],
  "top_k": 5,
  "max_tokens": 1024,
  "temperature": 0.7,
  "similarity_threshold": 0.5
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | Yes | The user's question or prompt |
| `user_email` | string | Yes | User email for SyftAI-Space visibility/policy checks |
| `model` | EndpointRef | Yes | Model endpoint reference |
| `data_sources` | EndpointRef[] | No | Data source endpoint references |
| `top_k` | int | No | Documents per source (1-20, default: 5) |
| `max_tokens` | int | No | Max tokens for LLM (default: 1024) |
| `temperature` | float | No | LLM temperature (0.0-2.0, default: 0.7) |
| `similarity_threshold` | float | No | Min similarity score (0.0-1.0, default: 0.5) |

**EndpointRef Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | Yes | Base URL of the SyftAI-Space instance |
| `slug` | string | Yes | Endpoint slug for the API path |
| `name` | string | No | Display name for logging/attribution |
| `tenant_name` | string | No | Tenant name for X-Tenant-Name header |

**Response:**
```json
{
  "response": "Based on the context...",
  "sources": [
    {
      "path": "Documentation",
      "documents_retrieved": 5,
      "status": "success",
      "error_message": null
    }
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

**Request:** Same as `/api/v1/chat`

**Events:**
- `retrieval_start` - Starting data source queries: `{"sources": N}`
- `source_complete` - One data source finished: `{"path": "...", "status": "success", "documents": N}`
- `retrieval_complete` - All sources done: `{"total_documents": N, "time_ms": N}`
- `generation_start` - Starting model generation: `{}`
- `token` - Response chunk: `{"content": "..."}`
- `done` - Complete with metadata: `{"sources": [...], "metadata": {...}}`
- `error` - Error occurred: `{"message": "..."}`

## Configuration

Environment variables (prefix: `AGGREGATOR_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8001` | Server port |
| `RETRIEVAL_TIMEOUT` | `30.0` | Timeout for data source queries (seconds) |
| `GENERATION_TIMEOUT` | `120.0` | Timeout for model generation (seconds) |

## SyftAI-Space Compatibility

The aggregator is designed to work with SyftAI-Space's unified endpoint API:

```
POST /api/v1/endpoints/{slug}/query
```

### Requirements for SyftAI-Space Endpoints

**For Data Sources:**
- Endpoint must have a dataset configured
- Endpoint's `response_type` should include references (`"raw"` or `"both"`)
- Endpoint must be `published: true`
- User email must be in the endpoint's `visibility` list (or visibility = `["*"]`)

**For Models:**
- Endpoint must have a model configured
- Endpoint's `response_type` should include summary (`"summary"` or `"both"`)
- Endpoint must be `published: true`
- User email must be in the endpoint's `visibility` list (or visibility = `["*"]`)

### Multi-tenancy Support

When connecting to SyftAI-Space instances with multi-tenancy enabled:
- Set `tenant_name` in the EndpointRef
- The aggregator will include `X-Tenant-Name` header in requests

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

## Example Usage

```python
import httpx

response = httpx.post(
    "http://localhost:8001/api/v1/chat",
    json={
        "prompt": "What is machine learning?",
        "user_email": "user@example.com",
        "model": {
            "url": "http://localhost:8080",
            "slug": "gpt-endpoint",
        },
        "data_sources": [
            {
                "url": "http://localhost:8080",
                "slug": "ml-docs",
                "name": "ML Documentation",
            }
        ],
        "top_k": 5,
        "max_tokens": 512,
    }
)

print(response.json())
```
