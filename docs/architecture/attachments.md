# Attachments — P2P File Transfer Protocol

**Status:** v1 (in development)
**Owners:** aggregator + syfthubapi + frontend
**Spec version:** `syfthub-attachments/v1`

## Goals

Enable users to attach files (documents, images) to agent prompts, and let agents
emit generated files (images, documents) back to the user — over the existing
P2P CLIENT ⇄ aggregator ⇄ NATS ⇄ HOST chain, preserving the platform's encryption
posture (NATS sees only ciphertext; aggregator decrypts as it does today for
event relay).

## Non-goals (v1)

- Per-endpoint MIME / size / quota policy YAML (deferred to v2)
- Streaming / progressive file emission (final-only in v1)
- Direct P2P (WebRTC) data channels — bytes still flow through NATS infrastructure
- Persistence beyond session end (Object Store TTL cleans up)
- Resumable uploads (re-upload from scratch on failure)
- Group recipients (one wrapped key per attachment, single recipient)

## Capability negotiation

Both peers declare attachment support in `session.start`:

```json
{
  "type": "session.start",
  "payload": {
    "...": "...",
    "capabilities": ["attachments"]
  }
}
```

Peers that omit the `capabilities` field continue to operate as before
(attachments simply unavailable). Peers MUST NOT emit attachment events if
either side has not declared the capability.

## Endpoint opt-in

Endpoint frontmatter (HOST side):

```yaml
slug: my-agent
type: agent
accepts_attachments: false   # default false; must be true to receive files
```

If `accepts_attachments: false`, the HOST's `agentNATSBridge` rejects inbound
attachment events with tunnel error code `ATTACHMENT_NOT_ACCEPTED` before any
download is attempted.

## Wire-level event shapes

### Metadata event (rides the existing encrypted event channel)

User → HOST direction:

```json
{
  "type": "user.attachment",
  "session_id": "<sid>",
  "sequence": 42,
  "timestamp": "2026-05-13T...",
  "payload": {
    "file_id":          "att-<uuid>",
    "name":             "report.pdf",
    "mime":             "application/pdf",
    "size_bytes":       2456321,
    "plaintext_sha256": "<hex>",
    "transport":        "inline" | "object_store",

    // Inline tier (size_bytes <= 65536):
    "inline_data_b64":  "<b64 of plaintext>",

    // Object-store tier (size_bytes > 65536):
    "object_bucket":    "syft-att-{session_id}",
    "object_key":       "att-<uuid>",
    "chunk_size":       65536,
    "wrapped_key": {
      "algorithm":  "AES-256-GCM",
      "ciphertext": "<b64>",
      "nonce":      "<b64>",
      "info":       "syfthub-attachment-v1"
    }
  }
}
```

Agent → user direction uses event type `agent.attachment` and identical payload
shape.

### Inline tier (v1 phase 1)

When `size_bytes <= 65536`, the producer sets `transport: "inline"` and
embeds the plaintext bytes as base64 in `inline_data_b64`. No Object Store,
no wrapped key — the event's existing end-to-end encryption layer already
protects the bytes. Consumer materializes to a tempfile and forwards a path
to the runner.

### Object-store tier (v1 phase 2)

When `size_bytes > 65536`, the producer:

1. Generates a fresh 32-byte AES-256 key `K` and 12-byte base-nonce `N`.
2. Encrypts the file plaintext with AES-256-GCM, chunked at `chunk_size`
   (default 64 KiB). Chunk `i` uses nonce `N || u32_BE(i)` and AAD =
   `file_id || u32_BE(i)`.
3. Streams ciphertext into JetStream Object Store bucket
   `syft-att-{session_id}`, key `att-<uuid>`.
4. Wraps `K` with the session AES key derived from `SessionEncryptor` /
   aggregator session ephemeral private key, using a sub-key derived via
   HKDF-Expand(session_key, info = `syfthub-attachment-v1` || file_id).
5. Emits the metadata event with `transport: "object_store"` and the
   `wrapped_key` block.

Consumer:

1. Decrypts the metadata event (existing path).
2. Unwraps `K` from `wrapped_key` using the session AES key + same HKDF.
3. Streams ciphertext from Object Store, decrypts chunk-by-chunk, writes to
   tempfile, verifies plaintext SHA-256, then notifies the runner with a
   path.

## Key derivation

Per-file AES key K is independent of the session key (so file ciphertext at
rest in Object Store does not compromise the session). Wrapping uses the
session-derived AES key as a KEK:

```
file_kek = HKDF-Expand(session_aes_key, info = "syfthub-attachment-v1" || file_id, L = 32)
wrapped_key.ciphertext = AES-256-GCM(file_kek, K, nonce = wrapped_key.nonce, aad = file_id)
```

The session AES key is what `SessionEncryptor` derived once at session start.
On the aggregator (CLIENT-facing) side, the session ephemeral private key
retained by `NATSSessionTransport._session_ephemeral_priv` derives the same
material via ECDH(eph_priv, HOST_response_eph_pub) → HKDF (response info).

## Bucket lifecycle (Object Store)

- Bucket: `syft-att-{session_id}` — UUID-scoped, unguessable.
- TTL: 1 hour after last access; 24 hour hard cap.
- Created lazily on first attachment per session.
- Deleted on session end (aggregator `finally` block) OR by JetStream
  TTL eviction, whichever comes first.

## Platform-level quotas (v1)

Enforced at aggregator + backend, NOT per-endpoint (v2 scope).

| Limit | Default | Where |
|---|---|---|
| Per-file max size | 25 MiB | aggregator pre-flight + backend signed cap |
| Per-session aggregate | 100 MiB | aggregator session state |
| Per-session file count | 20 | aggregator session state |
| Per-user daily bytes | 1 GiB | backend Redis counter |
| Per-user daily file count | 100 | backend Redis counter |
| Object Store TTL | 3600 s | NATS JetStream bucket config |

Pre-flight failure → HTTP 413 (size) or 429 (rate). Failures emit
`agent.error` with code `ATTACHMENT_QUOTA_EXCEEDED` over the WS for UI
surfacing.

## HTTP side-endpoints (Object Store tier)

Aggregator exposes:

- `POST /agent/session/{sid}/attachment` (multipart)
  - Headers: `Idempotency-Key`, `X-Attachment-Direction: outbound`
  - Body: multipart `name=file`, plus `metadata=<json>` field
  - Response: `201 {file_id, transport, ...}` or `413` / `429`

- `GET /agent/session/{sid}/attachment/{file_id}`
  - Supports HTTP range requests for resume
  - Response: `200`/`206` with `Content-Type` from metadata

Both endpoints require the CLIENT to be the WS-active owner of `sid`
(verified via session-state lookup; no separate auth on the HTTP path).

## Failure modes

| Code | Meaning | Recovery |
|---|---|---|
| `ATTACHMENT_QUOTA_EXCEEDED` | size or rate exceeded | none — caller chunks or waits |
| `ATTACHMENT_NOT_ACCEPTED` | endpoint opted out | none — try a different endpoint |
| `ATTACHMENT_INTEGRITY` | SHA mismatch after decrypt | retry once |
| `ATTACHMENT_DECRYPT_FAILED` | wrapped key unwrap or chunk decrypt failed | retry once (key rotation) |
| `ATTACHMENT_NOT_FOUND` | Object Store key missing (TTL evicted) | session must restart |
| `ATTACHMENT_INVALID_METADATA` | malformed metadata event | drop, log |

## Runner-side protocol

### Filemode (subprocess, JSON-lines)

HOST → runner stdin (inbound user file):

```json
{"type":"user_attachment","file_id":"att-...","path":"/syft/sess-X/att-Y.pdf","name":"report.pdf","mime":"application/pdf","size_bytes":2456321,"sha256":"..."}
```

Runner → HOST stdout (outbound agent file):

```json
{"type":"agent_attachment","path":"/syft/sess-X/out-Z.png","name":"art.png","mime":"image/png"}
```

`path` is always a path on a per-session tempdir created by HOST, with
0700 perms, cleaned up on session end. Bytes never traverse the JSON-line
pipe.

### Containermode (HTTP + SSE)

- Per-session bind mount: `/syft/attachments` inside container ↔ host tempdir.
- New container endpoints in `runner/server.py SessionAPI`:
  - `GET /session/{id}/attachments` → list with metadata
  - `POST /session/{id}/attachment` → multipart for outbound files
  - SSE stream gains `event: user_attachment` frames with `data: {file_id, path, ...}`

`runner/session.py` API:

```python
async def handler(session):
    async for msg in session.receive():
        if msg.type == "user_attachment":
            path = msg.path  # ready to read
            # ... process

    file_id = await session.send_attachment(
        Path("/tmp/result.png"),  # or io.BytesIO
        mime="image/png",
        name="result.png",
    )
    await session.message(f"Here's your image: attachment://{file_id}")
```

## Markdown integration

The `attachment://{file_id}` URI scheme is reserved for inline
references to attachments within agent messages. Desktop UI resolves
these via a small `react-markdown` plugin to blob URLs of decrypted
content; CLI substitutes the saved path.

## Observability

- `attachment_bytes_total{direction, mime_class}` (counter)
- `attachment_errors_total{code}` (counter)
- `attachment_duration_seconds{direction}` (histogram, p50/p99)
- Audit log entry per upload/download (metadata only)

## Versioning

- The capability string `attachments` implies the schema documented here.
- Future schema bumps will use `attachments/v2`, negotiated via the same
  capabilities array; v1 peers see v2 events as `INVALID_METADATA` and
  reject.
