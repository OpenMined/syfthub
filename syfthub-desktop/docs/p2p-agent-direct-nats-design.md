# Direct P2P Agent Sessions over NATS — Design

**Status:** Phases 1–6 implemented. 1–4 verified (Go build + embedded-NATS integration test); 5–6 build/compile clean but not stack-verified — the auth-callout is untested and the TS SDK was not type-checked in this environment.
**Date:** 2026-05-18
**Scope:** `sdk/golang/syfthubapi`, `sdk/golang/syfthub`, `syfthub-desktop`, `cli`, `components/aggregator`, `components/backend`, `deploy/nats`

**Decisions**
- **D1 — Crypto:** static-static identity ECDH (no forward secrecy). The `-v2` HKDF labels reserve room for a `-v3` ephemeral leg.
- **D2 — Auth:** a dedicated NATS auth-callout micro-service.
- No backwards compatibility required — the agent wire protocol may change and the aggregator agent path is deleted outright.

---

## 1. Motivation

An interactive agent session between two desktop apps is currently relayed by the aggregator's `/agent/session` WebSocket endpoint. The aggregator generates the tunnel's ephemeral keypair and holds the private key, so **it decrypts every agent request and response** — it is a trusted plaintext middlebox. For the RAG `/chat` path the aggregator does real compute; for the agent path it is pure WebSocket↔NATS plumbing.

Both desktops already run `syfthubapi` and already speak NATS (every tunneling host does). This refactor removes the aggregator from the agent path: the two peers pub/sub directly on each other's NATS subjects with **true end-to-end encryption** between them.

**Goals:** (1) genuine E2E encryption for agent sessions; (2) one transport/connection codebase in `syfthubapi`; (3) finish the half-built peer-token design with a real NATS authorization layer; (4) delete the aggregator agent path entirely.

## 2. Target architecture

```
        DESKTOP A (client+host)              DESKTOP B (client+host)
   ┌──────────────────────────────┐    ┌──────────────────────────────┐
   │ transport.NATSConn  ── one shared *nats.Conn per app ──           │
   │   ├ NATSTransport  (inbound host: subscribe syfthub.spaces.{me})  │
   │   └ AgentDialer    (outbound client: M concurrent sessions)       │
   │ identity key = ~/.config/syfthub/tunnel_key (X25519)              │
   └───────────────┬──────────────┘    └───────────────┬──────────────┘
                   └──────────────┬────────────────────┘
                          ┌───────┴────────┐
                          │  NATS broker   │  auth-callout → per-conn scoped perms
                          └───────┬────────┘
                          ┌───────┴────────┐
                          │  Backend       │  tokens, keys, directory + peer-token Redis
                          └────────────────┘
   Aggregator: RAG /chat only — OUT of the agent path entirely.
```

One `nats.Conn` per app multiplexes every session it participates in — *N* inbound hosted sessions (routed off the shared `syfthub.spaces.{me}` subscription by `session_id`) and *M* outbound client sessions (each with its own `syfthub.peer.{channel}` subscription). The CLI runs the same `NATSConn` with only an `AgentDialer` attached.

## 3. Crypto — protocol v2 (identity-keyed)

Both peers hold a long-term X25519 identity key (the desktop reuses its host `tunnel_key`; the CLI persists `~/.config/syfthub/identity.key`; the browser uses a per-session in-memory keypair).

```
shared   = X25519(my_identity_priv, peer_identity_pub)
req_key  = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-request-v2")
resp_key = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-response-v2")
per message: AES-256-GCM, fresh random 12-byte nonce, AAD = correlation_id
```

The identity-pair shared secret is stable, so `session_id` is the HKDF **salt** that makes each session's keys unique. The scheme is symmetric — one `SessionCipher` serves both peers (client: `EncryptRequest`/`DecryptResponse`; host: `DecryptRequest`/`EncryptResponse`). The sender's identity **public** key travels in the plaintext wrapper (`sender_public_key`). No ephemeral keys, no private-key retention.

**Tradeoff (D1):** static-static ECDH has no forward secrecy — theft of an identity key exposes recorded past sessions. Deliberate; `-v3` upgrade path reserved. The v1 ephemeral scheme (`crypto.go`) stays for the aggregator-relayed model/data_source path.

## 4. Wire protocol v2

NATS message wrapper (plaintext); subjects: client→host on `syfthub.spaces.{host}`, host→client on `syfthub.peer.{peer_channel}`.

```json
{
  "protocol": "syfthub-agent/v2",
  "type": "agent_session_start | agent_user_message | agent_session_cancel | agent_user_attachment | agent_event",
  "correlation_id": "<uuid; {session_id}-{sequence} for events>",
  "session_id": "<uuid>",
  "reply_to": "<peer_channel>",            // requests only
  "satellite_token": "<RS256 JWT>",        // session_start only
  "sender_public_key": "<b64url X25519 identity pubkey>",
  "nonce": "<b64url 12 bytes>",
  "encrypted_payload": "<b64url AES-256-GCM ciphertext+tag>"
}
```

## 5. NATS auth-callout

Makes the peer token real (today `pt_…` is minted, stored in Redis, and enforced nowhere).

- `nats.conf`: add `accounts { SYFTHUB, AUTH }`, replace `authorization{token}` with `authorization{auth_callout{...}}`. Server-config mode + one account signing nkey — *not* full operator mode.
- **Dedicated auth-callout micro-service (D2):** a NATS client connecting as the `AUTH`-account user (direct creds, exempt from callout), subscribed to `$SYS.REQ.USER.AUTH`. Per connection it inspects the presented token and signs a scoped user JWT:

| Presented credential | Granted permissions |
|---|---|
| peer token `pt_…` (Redis lookup) | pub `syfthub.spaces.{targets}`, sub `syfthub.peer.{channel}`, ObjStore `syft-att-{…}` |
| host token (new, Redis-backed, bound to user U) | sub `syfthub.spaces.{U}`, pub `syfthub.peer.*`, JetStream |
| service token (backend + aggregator only) | privileged |
| else | reject |

End-user machines (desktop host, desktop client, CLI, browser) get per-connection, subject-scoped, TTL-bound creds. Only backend + aggregator keep a privileged token.

## 6. Package & connection structure

| New / changed | What |
|---|---|
| `syfthubapi/transport/crypto_session.go` *(new)* | `SessionCipher` + `NewSessionCipher` — v2 identity-keyed crypto. |
| `syfthubapi/transport/conn.go` *(new)* | `NATSConn` — owns the single `*nats.Conn`; used by both roles. |
| `syfthubapi/transport/agent_dial.go` *(new)* | `AgentDialer` + `AgentClientSession` — the outbound client. |
| `syfthubapi/transport/nats.go` | `NATSTransport` takes an injected `NATSConn`; `agentNATSBridge`/`relayEvents` switch to `SessionCipher`. |
| `agenttypes/events.go` *(new)* | Typed agent event structs moved out of `syfthub/agent_session.go`. |

## 7. Phased plan

1. **Crypto + shared types** — `SessionCipher`; move event types to `agenttypes`; v2 wire structs.
2. **Transport** — `NATSConn`; `AgentDialer`/`AgentClientSession`; host bridge → `SessionCipher`. Two-`SyftAPI` + local-NATS integration test.
3. **Desktop** — rewire `agent_operations.go`/`attachment_operations.go` to `AgentDialer`; `NATSConn` lifecycle up at login. Frontend untouched.
4. **CLI** — rewire `cli/internal/cmd/agent.go`; persist `~/.config/syfthub/identity.key`.
5. **NATS auth-callout** — `nats.conf` accounts; the dedicated callout service; backend host-token minting; every connector off the shared token.
6. **Web migration + deletion** — `components/frontend` agent chat → `nats.ws` + WebCrypto; delete the aggregator agent path and the WSS agent clients.

Phase 5 must precede Phase 6 (a browser cannot hold the master token).

## 8. Deletions (Phase 6)

**Done — Go SDK:** `syfthub/agent.go`, `syfthub/agent_session.go`, and `Client.Agent()` + the `agent` field in `client.go`. All six Go modules build clean.

**Aggregator agent path** — a self-contained cluster (`grep` confirms no RAG-path module imports any of it; the only cross-edge is `clients/nats_object_store.py`, imported solely by `attachment_relay.py`):

- `api/endpoints/agent.py`
- `services/session_transport.py`, `services/session_manager.py`,
  `services/attachment_relay.py`, `services/attachment_session_state.py`
- `clients/nats_object_store.py`
- `schemas/agent.py`
- tests `test_attachment_crypto.py`, `test_attachment_relay.py`,
  `test_attachment_schemas.py`, `test_session_attachment_key_handshake.py`,
  `test_session_transport_tunnel_error.py`
- edit `api/router.py` — drop the `agent` import + `include_router(agent.router)`
  and `include_router(attachment_relay.router)`
- edit `api/endpoints/__init__.py` — drop `agent` from the import list

**Kept:** aggregator `crypto.py` + `clients/nats_transport.py` (the RAG model/data_source path still uses both).

**TS SDK:** `resources/agent.ts` is rewritten from a WSS client onto the v2 P2P client — new `src/crypto.ts` (`SessionCipher`) + a `nats.ws`-based `AgentResource`/`AgentSessionClient`.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Two crypto schemes coexist | Dispatched by message type; v1 untouched |
| Auth-callout on every connection's critical path | HA deployment; `AUTH` user uses direct creds (no bootstrap deadlock) |
| Browser X25519 in WebCrypto is recent | Fall back to `@noble/curves` |
| One `nats.Conn` multiplexing inbound + outbound | `NATSConn` + per-session maps; covered by the Phase 2 integration test |
| No forward secrecy (D1) | Documented; `-v3` upgrade path reserved |

## 10. Status

- [x] **Phase 1 — Crypto + shared types**
  - [x] `SessionCipher` identity-keyed v2 crypto + tests
  - [x] Agent event types moved to `agenttypes` (aliased in `syfthub`)
  - [x] v2 wire structs (`AgentEnvelope` in `syfthubapi/agentwire.go`)
- [x] **Phase 2 — Transport**
  - [x] `NATSConn` — the single shared connection
  - [x] `AgentDialer` + `AgentClientSession` (outbound client) + wire/crypto tests
  - [x] Refactored `NATSTransport` onto an injected `NATSConn` (`ownsConn` for the
        host-only `New` path); updated callers (desktop `app.go`, `cli/node_run.go`,
        example) and the `transport` package tests
  - [x] Host `agentNATSBridge` + `relayEvents` swapped to the v2 `AgentEnvelope`
        + `SessionCipher`; `handleMessage` routes v2 agent vs v1 model/data_source
  - [x] `TestAgentSessionEndToEnd` — full v2 P2P session over an embedded
        `nats-server`: client `AgentDialer` ⇄ host `agentNATSBridge`, passes
- [x] **Phase 3 — Desktop integration**
  - [x] `internal/app` builds an `AgentDialer` over the shared `NATSConn`,
        reusing the host's X25519 identity key; exposed via `AgentDialer()`
  - [x] `agent_operations.go` rewired to `AgentDialer.Dial` — fetches the
        satellite token, peer channel, and host encryption key from the hub
  - [x] `syfthub` SDK gains `Auth.GetEncryptionPublicKey`
  - [x] `attachment_operations.go` on the v2 `AgentClientSession`; inline
        attachments work on the direct path (object-store is a follow-up)
  - Note: agent chat now requires the app to be Started (the dialer lives with
    the host transport); login-time connection is a possible refinement
- [x] **Phase 4 — CLI integration**
  - [x] `cli agent` rewired from `syfthub.Client.Agent()` (WSS) to the
        `syfthubapi.AgentDialer` — direct NATS, no aggregator
  - [x] CLI persists an X25519 identity at `~/.config/syfthub/identity.key`;
        `transport.LoadOrGenerateKey` exported for it
  - [x] `agent_attachments.go` adapted to the v2 `AgentClientSession`
  - [x] Host fix: `handleSessionStart` now emits a terminal `session.failed`
        after a pre-session `agent.payment_required`, so the client never hangs
- [x] **Phase 5 — NATS auth-callout** *(implemented; not stack-verified)*
  - [x] `components/nats-auth/` — the auth-callout micro-service: validates
        service / host (`ht_`) / peer (`pt_`) tokens against Redis and signs
        subject-scoped user JWTs; `genkey` subcommand. Builds + vets clean.
  - [x] `deploy/nats/nats.{dev,prod}.conf` — `accounts` + `auth_callout`
  - [x] `docker-compose.{dev,deploy}.yml` — `nats-auth` service + env wiring
  - [x] Backend — `create_host_token` mints Redis-backed `ht_` tokens;
        `GET /nats/credentials` returns one; peer channels namespaced per user
        (`syfthub.peer.{username}.{uuid}`) so a symmetric desktop's single
        connection is subject-scoped (`sub syfthub.peer.{me}.>` + own space)
  - Not stack-verifiable here; staged rollout: `nats-auth` up → `nats.conf`
    cutover → connectors onto scoped credentials
- [x] **Phase 6 — Web migration + aggregator deletion** *(Go + Python done; TS web client implemented, not type-checked here)*
  - [x] Deleted the dead Go WSS agent client — `syfthub/agent.go`,
        `syfthub/agent_session.go`, and `Client.Agent()` + the `agent` field
        in `client.go`. All six Go modules still build clean.
  - [x] New TS v2 P2P web agent client in `@syfthub/sdk`:
        `src/crypto.ts` — `SessionCipher` mirroring the Go identity-keyed
        crypto (`@noble/curves` x25519, `@noble/hashes` hkdf+sha256,
        `@noble/ciphers` AES-256-GCM, unpadded base64url);
        `resources/agent.ts` rewritten onto `nats.ws`. `AgentResource` /
        `AgentSessionClient` keep their public API
        (`startSession`/`events()`/`sendMessage`/`confirm`/`deny`/`cancel`/
        `close`), so `components/frontend` `use-agent-workflow.ts` needs no
        change. The browser uses a fresh per-session ephemeral X25519 keypair
        and connects to NATS with the short-lived `pt_` peer token (the
        auth-callout scopes it). Added `Auth.getEncryptionPublicKey`; the
        `on()` listener API was dropped (unused); `@noble/*` + `nats.ws` added
        to `package.json` `dependencies`.
  - [x] Deleted the aggregator agent path — `api/endpoints/agent.py`,
        `services/{session_transport,session_manager,attachment_relay,attachment_session_state}.py`,
        `clients/nats_object_store.py`, `schemas/agent.py`, and 5 agent test
        files; trimmed `api/router.py` + `api/endpoints/__init__.py`.
        `py_compile` + an import grep are clean; the RAG `/chat` path is
        untouched (`crypto.py` + `clients/nats_transport.py` kept).
  - Not verifiable here: the TS SDK has no toolchain in this environment, so
    `crypto.ts` / `agent.ts` are written against the Go reference but were NOT
    type-checked or browser-tested, and the aggregator was not import-checked
    against its venv. Before shipping: `cd sdk/typescript && npm install &&
    npm run typecheck && npm test`; rebuild `components/frontend`; exercise
    web agent chat end-to-end against a running host plus the Phase 5
    auth-callout stack.
