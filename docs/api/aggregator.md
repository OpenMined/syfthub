# API Reference: Aggregator

> **Base URL (dev):** `http://localhost:8080/aggregator/api/v1`
> **Base URL (prod):** `https://{domain}/aggregator/api/v1`
> **Authentication:** Optional Bearer token in `Authorization` header
> **Content-Type:** `application/json`
> **Last updated:** 2026-03-27
> **Total endpoints:** 4

---

## Authentication

The aggregator accepts **optional** authentication via satellite tokens. Unlike the backend (which requires a hub token for most endpoints), the aggregator's chat endpoints work without authentication for public endpoints. Authentication is only required when querying private or internal endpoints.

### Satellite Token

```http
Authorization: Bearer <satellite-token>
```

Satellite tokens are RS256 JWTs with a 60-second expiry, obtained from the backend via `GET /api/v1/token?aud={username}`. The aggregator validates them against the backend's JWKS endpoint.

### Endpoint Tokens Pattern

For multi-owner queries (e.g., a model owned by user A and data sources owned by user B), the aggregator uses an **endpoint_tokens** dictionary in the request body rather than a single `Authorization` header:

```json
{
  "endpoint_tokens": {
    "owner_a": "<satellite-token-for-owner-a>",
    "owner_b": "<satellite-token-for-owner-b>"
  }
}
```

Each key is the endpoint owner's username; each value is a satellite token with that owner as the audience. The aggregator forwards the appropriate token when calling each endpoint.

### Transaction Tokens

For paid endpoints with accounting enabled, include transaction tokens alongside endpoint tokens:

```json
{
  "transaction_tokens": {
    "owner_a": "<transaction-token-for-owner-a>"
  }
}
```

---

## Error Format

All errors return consistent JSON:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "details": {}
}
```

The `details` field is optional and provides additional context when available.

### Common HTTP Status Codes

| Status | Meaning |
|---|---|
| 200 | Success |
| 400 | Bad request / validation error |
| 401 | Missing or invalid satellite token |
| 408 | Request timeout (retrieval or generation exceeded limits) |
| 422 | Unprocessable entity (Pydantic validation) |
| 500 | Internal server error |
| 503 | Service unavailable (model or data source unreachable) |

---

## Health Endpoints

### `GET /health`

Health check. Returns immediately to indicate the service is running.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "service": "syfthub-aggregator"
}
```

---

### `GET /ready`

Readiness check. Verifies the service is ready to accept requests.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "status": "ready",
  "checks": {}
}
```

---

## Chat Endpoints

### `POST /api/v1/chat`

Send a RAG chat request. The aggregator retrieves relevant documents from data sources, optionally reranks them, and generates a response using the specified model.

**Auth:** Optional. Bearer satellite token in `Authorization` header, or per-owner tokens in the request body via `endpoint_tokens`.

**Request Body:**

```json
{
  "prompt": "What is federated learning?",
  "model": {
    "url": "https://model-host.example.com",
    "slug": "owner/model-name",
    "name": "My Model",
    "tenant_name": "default",
    "owner_username": "owner"
  },
  "data_sources": [
    {
      "url": "https://datasource-host.example.com",
      "slug": "owner/datasource-name",
      "name": "My Data Source",
      "tenant_name": "default",
      "owner_username": "owner"
    }
  ],
  "endpoint_tokens": {
    "owner": "eyJhbGciOiJSUzI1NiIs..."
  },
  "transaction_tokens": {
    "owner": "txn_token_here"
  },
  "top_k": 5,
  "stream": false,
  "max_tokens": 1024,
  "temperature": 0.7,
  "similarity_threshold": 0.5,
  "custom_system_prompt": "You are a helpful assistant.",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is federated learning?"},
    {"role": "assistant", "content": "Federated learning is..."}
  ],
  "peer_token": "nats-peer-token",
  "peer_channel": "nats-channel-id"
}
```

**Request Fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | Yes | -- | The user query. Must be non-empty (`min_length=1`). |
| `model` | object | Yes | -- | Model endpoint to use for generation. Must include `url` and `slug`. Optional: `name`, `tenant_name`, `owner_username`. |
| `data_sources` | array | No | `[]` | Data source endpoints to retrieve documents from. Each must include `url` and `slug`. Optional: `name`, `tenant_name`, `owner_username`. |
| `endpoint_tokens` | dict | No | `{}` | Map of `owner_username` to satellite token for authenticating with each endpoint. |
| `transaction_tokens` | dict | No | `{}` | Map of `owner_username` to transaction token for paid endpoints. |
| `top_k` | int | No | `5` | Number of documents to retrieve per data source. Min: 1, Max: 20. |
| `stream` | bool | No | `false` | Whether to stream the response (ignored here; use the `/chat/stream` endpoint instead). |
| `max_tokens` | int | No | `1024` | Maximum tokens in the generated response. Min: 1. |
| `temperature` | float | No | `0.7` | Sampling temperature. Min: 0.0, Max: 2.0. |
| `similarity_threshold` | float | No | `0.5` | Minimum similarity score for retrieved documents. Min: 0.0, Max: 1.0. |
| `custom_system_prompt` | string | No | -- | Override the default system prompt used for generation. |
| `messages` | array | No | `[]` | Conversation history. Each message has `role` (`"system"`, `"user"`, or `"assistant"`) and `content` (string). |
| `peer_token` | string | No | -- | NATS authentication token for tunneled endpoint communication. |
| `peer_channel` | string | No | -- | NATS channel identifier for tunneled endpoint communication. |

**Response `200 OK`:**

```json
{
  "response": "Federated learning is a machine learning approach where...",
  "sources": {
    "Introduction to FL": {
      "slug": "owner/datasource-name",
      "content": "Federated learning allows multiple parties to..."
    }
  },
  "retrieval_info": [
    {
      "path": "owner/datasource-name",
      "documents_retrieved": 3,
      "status": "success"
    }
  ],
  "metadata": {
    "retrieval_time_ms": 245,
    "generation_time_ms": 1830,
    "total_time_ms": 2075
  },
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 256,
    "total_tokens": 768
  },
  "profit_share": {
    "owner/model-name": 0.85,
    "owner/datasource-name": 0.15
  }
}
```

**Response Fields:**

| Field | Type | Description |
|---|---|---|
| `response` | string | The generated response text. |
| `sources` | dict | Retrieved documents keyed by document title. Each value contains `slug` and `content`. |
| `retrieval_info` | array | Per-data-source retrieval results. Each entry contains `path`, `documents_retrieved`, `status`, and optional `error_message`. |
| `metadata` | object | Timing information: `retrieval_time_ms`, `generation_time_ms`, `total_time_ms`. |
| `usage` | object or null | Token usage from the model: `prompt_tokens`, `completion_tokens`, `total_tokens`. Null if the model does not report usage. |
| `profit_share` | object or null | Revenue split across endpoints, keyed by `owner/slug`. Null if no accounting is configured. |

**Errors:**

| Status | Cause |
|---|---|
| 400 | Invalid request (empty prompt, invalid parameter ranges) |
| 401 | Invalid or expired satellite token |
| 408 | Retrieval or generation timeout exceeded |
| 422 | Request body validation failed |
| 500 | Internal processing error |
| 503 | Model or data source endpoint unreachable |

---

### `POST /api/v1/chat/stream`

Send a RAG chat request with Server-Sent Events (SSE) streaming. Accepts the same request body as `POST /api/v1/chat`. The response is a stream of SSE events that provide real-time progress through retrieval, reranking, and generation phases.

**Auth:** Optional. Same authentication pattern as `POST /api/v1/chat`.

**Request Body:** Identical to `POST /api/v1/chat` (see above).

**Response:** `200 OK` with `Content-Type: text/event-stream`.

Each SSE event has the format:

```
event: <event_type>
data: <json_payload>
```

#### SSE Event Types

Events are emitted in the following order during a successful request:

| # | Event | Payload | Description |
|---|---|---|---|
| 1 | `retrieval_start` | `{"sources": <int>}` | Retrieval phase begins. `sources` is the number of data sources being queried. |
| 2 | `source_complete` | `{"path": "<owner/slug>", "status": "<status>", "documents": <int>}` | One data source finished retrieval. Emitted once per data source. |
| 3 | `reranking_start` | `{"documents": <int>}` | Reranking phase begins. `documents` is the total number of retrieved documents. |
| 4 | `reranking_complete` | `{"documents": <int>, "time_ms": <int>}` | Reranking finished. `documents` is the count after reranking; `time_ms` is elapsed time. |
| 5 | `retrieval_complete` | `{"total_documents": <int>, "time_ms": <int>}` | All retrieval (including reranking) is complete. |
| 6 | `generation_start` | `{}` | Generation phase begins. |
| 7 | `token` | `{"content": "<string>"}` | A generated token. Emitted repeatedly as the model produces output. |
| 8 | `generation_heartbeat` | `{"elapsed_ms": <int>}` | Sent every 3 seconds during non-streaming model generation to keep the connection alive. |
| 9 | `done` | `{"sources": {...}, "retrieval_info": [...], "metadata": {...}, "usage": {...}, "profit_share": {...}, "response": "<string>"}` | Stream complete. Contains the full response and all metadata (same structure as the non-streaming response). |
| 10 | `error` | `{"message": "<string>"}` | An error occurred. The stream terminates after this event. |

**Example SSE Stream:**

```
event: retrieval_start
data: {"sources": 1}

event: source_complete
data: {"path": "owner/datasource-name", "status": "success", "documents": 3}

event: reranking_start
data: {"documents": 3}

event: reranking_complete
data: {"documents": 3, "time_ms": 45}

event: retrieval_complete
data: {"total_documents": 3, "time_ms": 290}

event: generation_start
data: {}

event: token
data: {"content": "Federated"}

event: token
data: {"content": " learning"}

event: token
data: {"content": " is"}

event: done
data: {"response": "Federated learning is...", "sources": {...}, "retrieval_info": [...], "metadata": {"retrieval_time_ms": 290, "generation_time_ms": 1200, "total_time_ms": 1490}, "usage": {"prompt_tokens": 512, "completion_tokens": 128, "total_tokens": 640}, "profit_share": null}
```

**Notes:**

- Events 3-4 (`reranking_start` / `reranking_complete`) are only emitted when reranking is triggered (i.e., when documents are retrieved from data sources).
- Event 7 (`token`) is only emitted when the model supports streaming. For non-streaming models, event 8 (`generation_heartbeat`) is emitted every 3 seconds until the full response is ready.
- Event 9 (`done`) always contains the complete `response` string, even if individual tokens were streamed.
- If an error occurs at any phase, event 10 (`error`) is emitted and the stream ends.

**Errors:**

| Status | Cause |
|---|---|
| 400 | Invalid request |
| 401 | Invalid or expired satellite token |
| 422 | Request body validation failed |
| 500 | Internal processing error (may also appear as an `error` SSE event mid-stream) |

---

## Environment Variables

The aggregator is configured via environment variables with the `AGGREGATOR_` prefix.

| Variable | Default | Description |
|---|---|---|
| `AGGREGATOR_PORT` | `8001` | Port the aggregator listens on. |
| `AGGREGATOR_SYFTHUB_URL` | -- | URL of the SyftHub backend (for JWKS validation and API calls). |
| `AGGREGATOR_RETRIEVAL_TIMEOUT` | `30` | Timeout in seconds for the retrieval phase. |
| `AGGREGATOR_GENERATION_TIMEOUT` | `120` | Timeout in seconds for the generation phase. |
| `AGGREGATOR_TOTAL_TIMEOUT` | `180` | Maximum total time in seconds for a chat request. |
| `AGGREGATOR_DEFAULT_TOP_K` | `5` | Default number of documents to retrieve per data source. |
| `AGGREGATOR_MAX_TOP_K` | `20` | Maximum allowed value for `top_k`. |
| `AGGREGATOR_MAX_DATA_SOURCES` | `10` | Maximum number of data sources per request. |
| `AGGREGATOR_NATS_URL` | -- | NATS server URL for tunneled endpoint communication. |
| `AGGREGATOR_NATS_AUTH_TOKEN` | -- | Authentication token for connecting to NATS. |
| `AGGREGATOR_NATS_TUNNEL_TIMEOUT` | `30` | Timeout in seconds for NATS tunnel requests. |
| `AGGREGATOR_CORS_ORIGINS` | -- | Comma-separated list of allowed CORS origins. |
| `AGGREGATOR_SYFTHUB_JWKS_CACHE_TTL` | `3600` | Time in seconds to cache the backend's JWKS for satellite token validation. |
| `AGGREGATOR_MODEL_STREAMING_ENABLED` | `false` | Whether to enable streaming from model endpoints (when supported). |
