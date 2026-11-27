# API reference: aggregator

The aggregator runs a retrieval-augmented chat: it queries the data sources a request names,
reranks what comes back, and sends the result to a model endpoint. It is stateless; every
request carries the endpoints and tokens it needs.

- **Base URL (dev):** `http://localhost:8080/aggregator`
- **Base URL (prod):** `https://{domain}/aggregator`
- **Routes:** 6 (two health checks, two chat routes, a URL query route, an agent WebSocket)
- **Last updated:** 2026-11-27

The reverse proxy strips the `/aggregator` prefix, so `/aggregator/api/v1/chat` reaches the
service as `/api/v1/chat`. Paths below are the service's own. The proxy also serves
`GET /api/v1/q` at the site root as `/q`.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /ready` | Readiness |
| `POST /api/v1/chat` | Chat, one JSON response |
| `POST /api/v1/chat/stream` | Chat, Server-Sent Events |
| `GET /api/v1/q` | A query written as a URL, answered as an HTML page |
| `WS /api/v1/agent/session` | A session with an agent endpoint |

---

## Authentication

The aggregator does not authenticate callers and verifies no token. It forwards the tokens a
request carries to the services that do check them: each Space verifies its own satellite
token, and the Hub checks the user's token when a payment is made.

A chat request can carry two kinds of token.

### Satellite tokens, per endpoint

`endpoint_tokens` in the request body maps each endpoint's host to the satellite token minted
for it:

```json
{
  "endpoint_tokens": {
    "https://space-a.example.com": "<satellite token for that host>",
    "https://space-b.example.com": "<satellite token for that host>"
  }
}
```

The aggregator sends an endpoint the token stored under its `url`. If there is none, it falls
back to the token stored under the endpoint's `owner_username`; that form is deprecated, because
a satellite token is bound to one host and an owner may run several. An endpoint with no token
is called without an `Authorization` header.

Mint these with the Hub's `GET /api/v1/token` (or `GET /api/v1/token/guest`), passing
`owner_username` and `resource`. See the [backend reference](backend.md#satellite-tokens).

### The user's Hub token, for payments

When an endpoint answers `402 Payment Required`, the aggregator pays on the user's behalf and
retries. To do that it needs the user's Hub token, taken from the first of:

1. `user_token` in the request body
2. the `Authorization: Bearer <token>` header

Without one, a paid endpoint is not paid and its entry in `retrieval_info` reports an error. See
[Billing](#billing).

---

## Errors

| Status | Body | When |
|---|---|---|
| `400` | `{"detail": "<message>", "billing": {...} or null}` | The pipeline failed, for example the model rejected the request. `billing` reports what was already charged |
| `422` | `{"detail": [...]}` | The request body does not match the schema (FastAPI's validation error) |
| `500` | `{"detail": "Internal server error"}` | Anything unexpected |

A data source that fails does not fail the request: its entry in `retrieval_info` carries the
status and the answer is built from the sources that did respond. The streaming route reports
pipeline failures as an `error` event, not as an HTTP status; see below.

---

## Health

### `GET /health`

**Response `200`:**

```json
{"status": "healthy", "service": "syfthub-aggregator"}
```

### `GET /ready`

Always ready; the aggregator has no dependency it must reach before serving.

**Response `200`:**

```json
{"status": "ready", "checks": {}}
```

---

## Chat

### `POST /api/v1/chat`

Runs the whole pipeline and returns one JSON response.

**Request body:**

```json
{
  "prompt": "What is federated learning?",
  "model": {
    "url": "https://space-a.example.com",
    "slug": "my-model",
    "name": "My Model",
    "tenant_name": "default",
    "owner_username": "alice"
  },
  "data_sources": [
    {
      "url": "https://space-b.example.com",
      "slug": "my-docs",
      "name": "My Docs",
      "owner_username": "bob"
    }
  ],
  "endpoint_tokens": {
    "https://space-a.example.com": "eyJhbGciOiJSUzI1NiIs...",
    "https://space-b.example.com": "eyJhbGciOiJSUzI1NiIs..."
  },
  "user_token": "<hub access token>",
  "top_k": 5,
  "context_limit": 50,
  "max_tokens": 1024,
  "temperature": 0.7,
  "similarity_threshold": 0.5,
  "messages": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello. What would you like to know?"}
  ]
}
```

**Request fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | yes | | The user's question. At least one character |
| `model` | endpoint reference | yes | | The model endpoint that generates the answer |
| `data_sources` | array of endpoint reference | no | `[]` | Data sources to retrieve from, queried in parallel |
| `endpoint_tokens` | object | no | `{}` | Satellite tokens keyed by endpoint `url`; see [Authentication](#authentication) |
| `user_token` | string | no | | The user's Hub token, used to pay when an endpoint answers 402. Falls back to the `Authorization` header |
| `top_k` | integer | no | `5` | Documents to retrieve from each source. 1 to 20 |
| `context_limit` | integer | no | `50` | Most reranked documents, across all sources, that go into the prompt. 1 to 200 |
| `retrieval_only` | boolean | no | `false` | Skip reranking and generation and return the retrieved documents |
| `max_tokens` | integer | no | `1024` | Most tokens the model may generate. At least 1 |
| `temperature` | number | no | `0.7` | Sampling temperature. 0.0 to 2.0 |
| `similarity_threshold` | number | no | `0.5` | Lowest similarity score a retrieved document may have. 0.0 to 1.0 |
| `custom_system_prompt` | string | no | | Replaces the default system prompt |
| `messages` | array | no | `[]` | Earlier turns, each `{"role": "system" \| "user" \| "assistant", "content": "..."}`. Used for generation only; retrieval uses `prompt` |
| `peer_token` | string | no | | Peer token from the Hub's `POST /api/v1/peer-token`, for endpoints reached over NATS |
| `peer_channel` | string | no | | Reply channel issued with the peer token |
| `stream` | boolean | no | `false` | Ignored here; use `/chat/stream` |
| `transaction_tokens` | object | no | `{}` | Deprecated and ignored. Payment uses `user_token` |

`top_k` and `context_limit` do different jobs: `top_k` decides how much each source returns
(and is charged for), `context_limit` decides how much of the combined pool the model sees.

**Endpoint reference:**

| Field | Type | Required | Description |
|---|---|---|---|
| `url` | string | yes | Base URL of the Space that serves the endpoint. A value starting with `tunneling:` is reached over NATS instead of HTTP |
| `slug` | string | yes | The endpoint's slug on that Space. The aggregator calls `{url}/api/v1/endpoints/{slug}/query` |
| `name` | string | no | Display name, for logs and attribution |
| `tenant_name` | string | no | Sent as the `X-Tenant-Name` header, for a multi-tenant Space |
| `owner_username` | string | no | The endpoint owner. Forms the `owner/slug` path used in results |
| `query_override` | string | no | Sent to this data source in place of `prompt`, for example a URL for a URL-fetching source |

**Response `200`:**

```json
{
  "response": "Federated learning is a machine learning approach where...",
  "sources": {
    "Introduction to FL": {
      "slug": "bob/my-docs",
      "content": "Federated learning allows multiple parties to..."
    }
  },
  "retrieval_info": [
    {"path": "bob/my-docs", "documents_retrieved": 3, "status": "success", "error_message": null}
  ],
  "metadata": {"retrieval_time_ms": 245, "generation_time_ms": 1830, "total_time_ms": 2075},
  "usage": {"prompt_tokens": 512, "completion_tokens": 256, "total_tokens": 768},
  "profit_share": {"bob/my-docs": 1.0},
  "billing": {
    "total_cost": 0.02,
    "currency": "USD",
    "entries": [
      {"source": "bob/my-docs", "status": "charged", "amount": 0.02, "currency": "USD"}
    ]
  }
}
```

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `response` | string | The generated answer. Empty when `retrieval_only` is set |
| `sources` | object | Retrieved documents keyed by title, each with `slug` (the `owner/slug` path it came from) and `content` |
| `retrieval_info` | array | One entry per data source: `path`, `documents_retrieved`, `status`, `error_message` |
| `metadata` | object | `retrieval_time_ms`, `generation_time_ms`, `total_time_ms` |
| `usage` | object or null | `prompt_tokens`, `completion_tokens`, `total_tokens`, when the model reports them |
| `profit_share` | object or null | Each source's share of the answer, `owner/slug` to a fraction from 0 to 1, worked out from the citations in the answer. Null when no retrieved documents went into the prompt |
| `billing` | object or null | What the queried endpoints charged; see [Billing](#billing). Null when no endpoint reported any |

`retrieval_info[].status` is one of:

| Status | Meaning |
|---|---|
| `success` | The source answered |
| `error` | The source failed |
| `timeout` | The source did not answer in time |
| `payment_failed` | The source asked for payment and the payment failed, for example for lack of balance |
| `access_denied` | The source refused the caller |

---

### `POST /api/v1/chat/stream`

The same pipeline, reported as it runs. Takes the same request body as `POST /api/v1/chat`.

**Response `200`** with `Content-Type: text/event-stream`. Each event is:

```
event: <name>
data: <json>
```

**Events, in order:**

| Event | Data | When |
|---|---|---|
| `retrieval_start` | `{"sources": <int>}` | Retrieval begins; `sources` is the number of data sources |
| `source_complete` | `{"path": "<owner/slug>", "status": "<status>", "documents": <int>}` | Once per data source, as each finishes |
| `reranking_start` | `{"documents": <int>}` | Only if documents were retrieved |
| `reranking_complete` | `{"documents": <int>, "time_ms": <int>}` | `documents` is the number kept after `context_limit` |
| `retrieval_complete` | `{"total_documents": <int>, "time_ms": <int>}` | Retrieval and reranking are done |
| `generation_start` | `{}` | The model is called |
| `generation_heartbeat` | `{"elapsed_ms": <int>}` | Repeated while a model that does not stream is working |
| `token` | `{"content": "<string>"}` | A piece of the answer. A model that does not stream sends the whole answer as one `token` |
| `done` | see below | The last event of a successful run |
| `error` | `{"message": "<string>", "billing": {...} or null}` | The run failed; no further events follow |

**The `done` event** carries:

| Field | Present | Description |
|---|---|---|
| `sources` | always | As in the JSON response |
| `retrieval_info` | always | As in the JSON response, without `error_message` |
| `metadata` | always | As in the JSON response |
| `usage` | when the model reports it | Token counts |
| `response` | when retrieved documents went into the prompt | The full answer with citation positions marked. Replace the streamed text with it |
| `profit_share` | when retrieved documents went into the prompt | As in the JSON response |
| `billing` | when an endpoint reported charges | As in the JSON response |

The answer is the concatenation of the `token` events; `done.response` replaces it only when
present.

**The `error` event** is sent when:

- a data source answers `access_denied`. The run stops before generation, because answering
  without a source the user chose would give the wrong context
- generation fails. `billing` then reports what the data sources already charged

**Example:**

```
event: retrieval_start
data: {"sources": 1}

event: source_complete
data: {"path": "bob/my-docs", "status": "success", "documents": 3}

event: reranking_start
data: {"documents": 3}

event: reranking_complete
data: {"documents": 3, "time_ms": 45}

event: retrieval_complete
data: {"total_documents": 3, "time_ms": 290}

event: generation_start
data: {}

event: token
data: {"content": "Federated learning is..."}

event: done
data: {"sources": {...}, "retrieval_info": [...], "metadata": {"retrieval_time_ms": 290, "generation_time_ms": 1200, "total_time_ms": 1490}}
```

---

## URL query

### `GET /api/v1/q`

A query written as a URL and answered as a static HTML page, for `curl` and other clients
that run no JavaScript. The route resolves the endpoints through the Hub, mints the satellite
tokens and runs the pipeline.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `q` | string | yes | | `source1\|source2!prompt`: data sources separated by `\|`, then `!`, then the prompt |
| `aggregate` | boolean | no | `false` | `true` reranks and generates an answer. `false` returns the retrieved documents only |

Each source is an `owner/slug` path or a URL. A URL (anything with a scheme, or a dot in its
first segment, such as `example.com`) is fetched through the endpoint named by
`AGGREGATOR_URL_FETCHER_SLUG`. The model is always the one named by
`AGGREGATOR_DEFAULT_QUERY_MODEL`.

```bash
curl "http://localhost:8080/q?q=alice/wiki|bob/docs!compare+approaches&aggregate=true"
curl "http://localhost:8080/q?q=example.com!summarize+this+site"
```

**Auth:** optional `Authorization: Bearer <hub token>`. With it, endpoints are resolved and
tokens minted as that user; without it, as a guest.

**Response:** HTML. The result is also embedded as JSON in
`<script id="query-result" type="application/json">`:

```json
{
  "query": "compare approaches",
  "model": "owner/model-slug",
  "data_sources": ["alice/wiki", "bob/docs"],
  "answer": "...",
  "sources": {"<title>": {"slug": "alice/wiki", "content": "..."}},
  "error": null
}
```

| Status | When |
|---|---|
| `200` | The query ran |
| `400` | `q` has no `!`, has an empty prompt or a malformed source, or names no source while `aggregate` is false |
| `502` | An endpoint could not be resolved, or the pipeline failed |
| `500` | Anything unexpected |

Error responses are the same HTML page with `error` set and `answer` null.

---

## Agent sessions

### `WS /api/v1/agent/session`

A two-way session with an agent endpoint on a Space, relayed over NATS and encrypted to the
Space's public key. Messages in both directions are JSON objects with a `type`.

**Flow:**

1. The client connects and, within 30 seconds, sends `session.start`.
2. The server answers `session.created` with the session id.
3. The server relays the agent's events to the client, and the client's messages to the agent,
   until the session ends.
4. If the client disconnects, the server tells the Space to cancel.

**`session.start`** (client to server):

```json
{
  "type": "session.start",
  "payload": {
    "prompt": "Summarise last week's incidents",
    "endpoint": {"owner": "alice", "slug": "ops-agent"},
    "satellite_token": "<satellite token for the Space>",
    "peer_channel": "<channel from the peer token>",
    "config": {},
    "messages": []
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `prompt` | string | yes | The first prompt |
| `endpoint` | object | yes | `owner` and `slug` of the agent endpoint |
| `satellite_token` | string | yes | Satellite token the Space will verify |
| `peer_token` | string | no | Peer token from the Hub |
| `peer_channel` | string | no | Reply channel; generated when omitted |
| `config` | object | no | Agent configuration, passed through |
| `messages` | array | no | Earlier turns |
| `transaction_token` | string | no | Passed through to the Space |

**Other client messages:**

| Type | Payload | Effect |
|---|---|---|
| `user.message` | `content`, optional `satellite_token` | Forwarded to the agent |
| `user.confirm` | `tool_call_id`, optional `modifications` | Approves a tool call |
| `user.deny` | `tool_call_id`, optional `reason` | Rejects a tool call |
| `user.cancel`, `session.close` | | Cancels the session |
| `ping` | | Answered with `{"type": "pong"}` |

**Server messages.** `session.created` is `{"type", "session_id", "payload": {"session_id"}}`.
Every event relayed from the agent has this envelope:

```json
{
  "type": "agent.message",
  "session_id": "8f1c...",
  "sequence": 4,
  "timestamp": "2026-11-27T09:30:00+00:00",
  "payload": {"content": "...", "is_complete": true}
}
```

| Type | Payload |
|---|---|
| `agent.thinking` | `content`, `is_streaming` |
| `agent.tool_call` | `tool_call_id`, `tool_name`, `arguments`, `requires_confirmation`, `description` |
| `agent.tool_result` | `tool_call_id`, `status` (`success` or `error`), `result`, `error`, `duration_ms` |
| `agent.message` | `content`, `is_complete` |
| `agent.token` | `token` |
| `agent.status` | `status`, `detail`, `progress` (0 to 1) |
| `agent.request_input` | `prompt`. The agent waits for a `user.message` |
| `agent.error` | `code`, `message`, `recoverable` |
| `session.completed` | `session_id`. Ends the session |
| `session.failed` | `error`, `reason`. Ends the session |

The event types come from the Space; the aggregator relays whatever it sends.

**Errors raised by the aggregator** arrive as `agent.error`:

| Code | When | Close code |
|---|---|---|
| `SESSION_START_TIMEOUT` | No `session.start` within 30 seconds | 1008 |
| `INVALID_MESSAGE` | The first message is not `session.start` | 1008 |
| `INVALID_PAYLOAD` | The `session.start` payload is invalid | 1008 |
| `SPACE_KEY_ERROR` | The Space's encryption key could not be fetched | 1011 |
| `INTERNAL_ERROR` | Anything unexpected | |

A session with no client message for 30 minutes is cancelled.

---

## Billing

Endpoints may charge per query. Payment follows the HTTP 402 flow:

1. The aggregator calls the endpoint.
2. The endpoint answers `402` with a `WWW-Authenticate` challenge.
3. The aggregator sends the challenge to the Hub's `POST /api/v1/wallet/pay` with the user's
   Hub token, and gets a payment credential back.
4. The aggregator retries the call with the credential in the `X-Payment` header.

Each endpoint reports what it did in its response. The aggregator collects those reports into
`billing`:

| Field | Type | Description |
|---|---|---|
| `entries` | array | Every policy entry the endpoints reported, each with a `source` set to the endpoint's `owner/slug` |
| `total_cost` | number or null | Sum of the entries whose `status` is `charged`. Null when nothing was charged or the charges are in more than one currency |
| `currency` | string or null | The currency of the charged entries when they all share one |

`billing` is returned on failures too (in the `400` body and in the `error` event), because
data sources may have been paid before the model failed.

---

## Environment variables

Settings are read from the environment with the `AGGREGATOR_` prefix.

| Variable | Default | Description |
|---|---|---|
| `AGGREGATOR_HOST` | `0.0.0.0` | Address the service binds to |
| `AGGREGATOR_PORT` | `8001` | Port the service listens on |
| `AGGREGATOR_DEBUG` | `false` | Serves `/docs` and `/redoc` when true |
| `AGGREGATOR_SYFTHUB_URL` | `http://localhost:8000` | The Hub's URL: endpoint resolution and tokens for `/q`, payments, error reports |
| `AGGREGATOR_RETRIEVAL_TIMEOUT` | `30` | Seconds to wait for a data source |
| `AGGREGATOR_GENERATION_TIMEOUT` | `120` | Seconds to wait for the model |
| `AGGREGATOR_MODEL_STREAMING_ENABLED` | `false` | Stream tokens from the model. Off until Spaces support it |
| `AGGREGATOR_NATS_URL` | `nats://nats:4222` | NATS server, for endpoints reached by tunnel |
| `AGGREGATOR_NATS_AUTH_TOKEN` | empty | NATS token, needed for endpoints reached by tunnel |
| `AGGREGATOR_NATS_TUNNEL_TIMEOUT` | `30` | Seconds to wait for a tunnelled reply |
| `AGGREGATOR_DEFAULT_QUERY_MODEL` | `testuser/llm-proxy` | Model used by `/q`, as `owner/slug` |
| `AGGREGATOR_URL_FETCHER_SLUG` | `testuser/url-fetcher` | Data source that fetches URLs for `/q`, as `owner/slug` |
| `AGGREGATOR_CORS_ORIGINS` | `["http://localhost:3000", "http://localhost:8080"]` | Allowed CORS origins |
| `AGGREGATOR_LOG_LEVEL` | `INFO` | Log level |
| `AGGREGATOR_LOG_FORMAT` | `json` | `json` or `console` |
| `AGGREGATOR_LOG_REQUEST_HEADERS` | `false` | Log request headers. Debugging only |
| `AGGREGATOR_LOG_REQUEST_BODY` | `false` | Log request bodies. Debugging only |

Five more settings are defined but not read by any code, so setting them changes nothing:
`AGGREGATOR_TOTAL_TIMEOUT`, `AGGREGATOR_DEFAULT_TOP_K`, `AGGREGATOR_MAX_TOP_K`,
`AGGREGATOR_MAX_DATA_SOURCES` and `AGGREGATOR_SYFTHUB_JWKS_CACHE_TTL`. The limits on `top_k`
and `context_limit` are fixed in the request schema.

---

## Related

- [Backend API reference](backend.md)
- [Aggregator architecture](../architecture/components/aggregator.md)
