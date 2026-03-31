# SyftHub LLM Chat Workflow — Complete Architecture

> End-to-end trace of a chat request from the React frontend through the backend, aggregator, NATS tunnel, desktop/CLI node, and Go SDK endpoint handler.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Relationship Map](#2-component-relationship-map)
3. [Complete Chat Sequence (High Level)](#3-complete-chat-sequence-high-level)
4. [Phase 1: Frontend — User Input to API Call](#4-phase-1-frontend--user-input-to-api-call)
5. [Phase 2: Token Acquisition](#5-phase-2-token-acquisition)
6. [Phase 3: Aggregator — RAG Orchestration](#6-phase-3-aggregator--rag-orchestration)
7. [Phase 4: Transport Decision — HTTP vs NATS](#7-phase-4-transport-decision--http-vs-nats)
8. [Phase 5: NATS Tunnel Protocol](#8-phase-5-nats-tunnel-protocol)
9. [Phase 6: Desktop/CLI — Endpoint Execution](#9-phase-6-desktopcli--endpoint-execution)
10. [Phase 7: Response Assembly & Streaming](#10-phase-7-response-assembly--streaming)
11. [SSE Event Lifecycle](#11-sse-event-lifecycle)
12. [Authentication & Token Architecture](#12-authentication--token-architecture)
13. [NATS Encryption Protocol](#13-nats-encryption-protocol)
14. [Branch Logic: Streaming vs Non-Streaming](#14-branch-logic-streaming-vs-non-streaming)
15. [Branch Logic: Authenticated vs Guest](#15-branch-logic-authenticated-vs-guest)
16. [Citation & Attribution Pipeline](#16-citation--attribution-pipeline)
17. [Error Handling Across Layers](#17-error-handling-across-layers)
18. [Data Models Reference](#18-data-models-reference)

---

## 1. System Overview

```mermaid
graph TB
    subgraph "User's Browser"
        FE[React Frontend<br/>port 3000]
    end

    subgraph "SyftHub Cloud"
        NG[Nginx Reverse Proxy<br/>port 8080]
        BE[Backend Hub API<br/>FastAPI · port 8000]
        AG[Aggregator Service<br/>FastAPI · port 8001]
        NATS[NATS Broker<br/>port 4222 / WS]
        DB[(PostgreSQL)]
        RD[(Redis)]
    end

    subgraph "User's Machine"
        DA[Desktop App / CLI<br/>Go · NATS client]
        EP[Local Endpoints<br/>Python handlers]
    end

    FE -->|"all requests"| NG
    NG -->|"/api/v1/*"| BE
    NG -->|"/aggregator/api/v1/*"| AG

    BE --> DB
    BE --> RD

    AG -->|"HTTP direct"| EP2[Remote Endpoints]
    AG -->|"NATS tunnel"| NATS
    NATS -->|"encrypted"| DA
    DA -->|"subprocess"| EP

    BE -.->|"token endpoints"| FE
    AG -.->|"SSE stream"| FE

    style FE fill:#4A90D9,color:#fff
    style BE fill:#E8A838,color:#fff
    style AG fill:#7B68EE,color:#fff
    style NATS fill:#27AE60,color:#fff
    style DA fill:#E74C3C,color:#fff
    style NG fill:#95A5A6,color:#fff
```

**Key insight**: The backend is NOT in the chat request path. Chat requests flow directly from frontend → aggregator. The backend only provides authentication tokens.

---

## 2. Component Relationship Map

```mermaid
graph LR
    subgraph "Frontend Layer"
        CV[ChatView] --> UCW[useChatWorkflow]
        SI[SearchInput] --> CV
        UCW --> SDK_TS["@syfthub/sdk<br/>TypeScript"]
    end

    subgraph "Token Layer (Backend)"
        SDK_TS -->|"GET /api/v1/token"| SAT[Satellite Token EP]
        SDK_TS -->|"POST /api/v1/accounting/transaction-tokens"| TXN[Transaction Token EP]
        SDK_TS -->|"POST /api/v1/peer-token"| PEER[Peer Token EP]
    end

    subgraph "Aggregator Layer"
        SDK_TS -->|"POST /aggregator/api/v1/chat/stream"| CHAT_EP[Chat Stream EP]
        CHAT_EP --> ORCH[Orchestrator]
        ORCH --> RET[Retrieval Service]
        ORCH --> RERANK[Reranker<br/>ONNX]
        ORCH --> PB[Prompt Builder]
        ORCH --> GEN[Generation Service]
    end

    subgraph "Transport Layer"
        RET -->|"HTTP"| HTTP_T[HTTP Client]
        RET -->|"NATS"| NATS_T[NATS Transport]
        GEN -->|"HTTP"| HTTP_T
        GEN -->|"NATS"| NATS_T
    end

    subgraph "Endpoint Layer (Desktop/CLI)"
        NATS_T -->|"encrypted pub/sub"| NATS_H[NATS Handler]
        HTTP_T -->|"direct POST"| HTTP_H[HTTP Handler]
        NATS_H --> PROC[RequestProcessor]
        HTTP_H --> PROC
        PROC --> REG[Endpoint Registry]
        REG --> EXEC[SubprocessExecutor<br/>Python handler]
    end

    style CV fill:#4A90D9,color:#fff
    style ORCH fill:#7B68EE,color:#fff
    style NATS_T fill:#27AE60,color:#fff
    style PROC fill:#E74C3C,color:#fff
```

---

## 3. Complete Chat Sequence (High Level)

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend<br/>(React)
    participant BE as Backend<br/>(FastAPI)
    participant AG as Aggregator<br/>(FastAPI)
    participant NATS as NATS Broker
    participant Space as Desktop/CLI<br/>(Go)
    participant EP as Endpoint<br/>(Python)

    User->>FE: Type query, select model & sources
    FE->>FE: Validate input, resolve source IDs

    rect rgb(255, 243, 224)
        Note over FE,BE: Phase 1 — Token Acquisition
        par Satellite Tokens
            FE->>BE: GET /api/v1/token?aud={owner}
            BE-->>FE: RS256 JWT (60s TTL)
        and Transaction Tokens
            FE->>BE: POST /api/v1/accounting/transaction-tokens
            BE-->>FE: Billing tokens per owner
        and Peer Token (if tunneling)
            FE->>BE: POST /api/v1/peer-token
            BE-->>FE: peer_token + peer_channel + nats_url
        end
    end

    rect rgb(224, 247, 250)
        Note over FE,AG: Phase 2 — Chat Stream
        FE->>AG: POST /aggregator/api/v1/chat/stream<br/>(prompt, model, sources, all tokens)
        AG-->>FE: SSE: retrieval_start

        rect rgb(232, 245, 233)
            Note over AG,EP: Phase 3 — Retrieval (parallel per source)
            par For each data source
                alt HTTP endpoint
                    AG->>EP: POST {url}/query<br/>Authorization: Bearer {satellite_token}
                    EP-->>AG: documents[]
                else NATS tunnel endpoint
                    AG->>AG: Encrypt payload (X25519 + AES-256-GCM)
                    AG->>NATS: PUB syfthub.spaces.{owner}
                    NATS->>Space: Encrypted request
                    Space->>Space: Decrypt, verify token
                    Space->>EP: Invoke handler
                    EP-->>Space: documents[]
                    Space->>Space: Encrypt response
                    Space->>NATS: PUB syfthub.peer.{channel}
                    NATS-->>AG: Encrypted response
                    AG->>AG: Decrypt response
                end
            end
        end

        AG-->>FE: SSE: source_complete (per source)
        AG-->>FE: SSE: retrieval_complete

        AG->>AG: Rerank documents (ONNX)
        AG-->>FE: SSE: reranking_start / reranking_complete

        AG->>AG: Build augmented prompt
        AG-->>FE: SSE: generation_start

        rect rgb(243, 229, 245)
            Note over AG,EP: Phase 4 — LLM Generation
            alt HTTP model
                AG->>EP: POST {url}/query<br/>Authorization: Bearer {satellite_token}
                EP-->>AG: LLM response
            else NATS tunnel model
                AG->>NATS: PUB syfthub.spaces.{owner}
                NATS->>Space: Encrypted request
                Space->>EP: Invoke model handler
                EP-->>Space: LLM response
                Space->>NATS: PUB syfthub.peer.{channel}
                NATS-->>AG: Encrypted response
            end
        end

        AG-->>FE: SSE: token (repeated, chunked)
        AG-->>FE: SSE: generation_heartbeat (periodic)
        AG->>AG: Annotate citations, compute attribution
        AG-->>FE: SSE: done (response + sources + metadata)
    end

    FE->>FE: Parse citations, update UI
    FE->>User: Display formatted response with sources
```

---

## 4. Phase 1: Frontend — User Input to API Call

### Component Hierarchy

```mermaid
graph TD
    CP[ChatPage] -->|"navigation state"| CV[ChatView]
    CV -->|"renders"| SI[SearchInput]
    CV -->|"renders"| ML[MessageList]
    CV -->|"renders"| STAT[StatusIndicator]
    CV -->|"uses"| UCW[useChatWorkflow hook]
    SI -->|"@mention"| AC[Autocomplete]
    SI -->|"model picker"| MP[ModelSelector]
    ML -->|"per message"| MM[MarkdownMessage]
    MM -->|"citations"| CIT[CitationHighlight]

    UCW -->|"dispatches"| RED[workflowReducer]
    UCW -->|"calls"| SDK[SyftHubClient]
    RED -->|"state updates"| CV

    style UCW fill:#E8A838,color:#fff
    style SDK fill:#4A90D9,color:#fff
```

### useChatWorkflow State Machine

```mermaid
statediagram-v2
    [*] --> idle
    idle --> preparing: submitQuery()
    preparing --> streaming: executeWithSources()
    streaming --> streaming: SSE events
    streaming --> complete: done event
    streaming --> error: error event / abort
    preparing --> error: validation failure
    complete --> idle: new query
    error --> idle: new query
```

### Frontend Request Flow

```mermaid
flowchart TD
    A[User clicks Send] --> B{Input valid?}
    B -->|No| ERR1[Show validation error]
    B -->|Yes| C[Resolve source IDs → full paths]
    C --> D[Set phase = preparing]

    D --> E[Collect unique endpoint owners]
    E --> F{User authenticated?}

    F -->|Yes| G1[GET /api/v1/token?aud=owner<br/>for each unique owner]
    F -->|No| G2[GET /api/v1/token/guest?aud=owner<br/>for each unique owner]

    G1 --> H{Any tunneling endpoints?}
    G2 --> H

    H -->|Yes| I[POST /api/v1/peer-token<br/>with target_usernames]
    H -->|No| J[Skip peer token]

    I --> K[Build ChatRequest body]
    J --> K

    F -->|Yes| L[POST /api/v1/accounting/transaction-tokens]
    L --> K

    K --> M[POST /aggregator/api/v1/chat/stream]
    M --> N[Set phase = streaming]
    N --> O[Process SSE events via AsyncIterable]

    style A fill:#4A90D9,color:#fff
    style M fill:#7B68EE,color:#fff
    style O fill:#27AE60,color:#fff
```

### ChatRequest Body (sent to aggregator)

```json
{
  "prompt": "What are the key features?",
  "model": {
    "url": "https://space.example.com",
    "slug": "gpt-model",
    "name": "GPT Model",
    "owner_username": "alice"
  },
  "data_sources": [
    {
      "url": "tunneling:bob",
      "slug": "docs-dataset",
      "name": "Docs",
      "owner_username": "bob"
    }
  ],
  "endpoint_tokens": {
    "alice": "eyJ...(satellite JWT)...",
    "bob": "eyJ...(satellite JWT)..."
  },
  "transaction_tokens": {
    "alice": "tx_token_alice",
    "bob": "tx_token_bob"
  },
  "peer_token": "peer_jwt_for_nats",
  "peer_channel": "a1b2c3d4-uuid",
  "top_k": 5,
  "max_tokens": 1024,
  "temperature": 0.7,
  "similarity_threshold": 0.5,
  "stream": true,
  "messages": [
    {"role": "user", "content": "Previous question"},
    {"role": "assistant", "content": "Previous answer"}
  ]
}
```

---

## 5. Phase 2: Token Acquisition

```mermaid
sequenceDiagram
    participant SDK as TS SDK
    participant BE as Backend Hub

    Note over SDK: Collect unique owners from model + data_sources

    par Satellite Tokens (one per owner)
        SDK->>BE: GET /api/v1/token?aud=alice
        BE->>BE: Validate user active<br/>Sign RS256 JWT (sub=user, aud=alice, 60s)
        BE-->>SDK: {target_token, expires_in: 60}

        SDK->>BE: GET /api/v1/token?aud=bob
        BE-->>SDK: {target_token, expires_in: 60}
    and Transaction Tokens (batch)
        SDK->>BE: POST /api/v1/accounting/transaction-tokens<br/>{owner_usernames: ["alice", "bob"]}
        BE->>BE: For each owner:<br/>  1. Look up owner email<br/>  2. POST to accounting service
        BE-->>SDK: {tokens: {"alice": "tx1", "bob": "tx2"}, errors: {}}
    and Peer Token (if tunneling detected)
        SDK->>BE: POST /api/v1/peer-token<br/>{target_usernames: ["bob"]}
        BE->>BE: Generate peer channel UUID<br/>Store in Redis with TTL
        BE-->>SDK: {peer_token, peer_channel, expires_in, nats_url}
    end

    Note over SDK: All tokens collected → build ChatRequest
```

### Token Types Comparison

| Token | Endpoint | Signing | TTL | Purpose | Auth Required |
|-------|----------|---------|-----|---------|---------------|
| **Hub Access** | Login | HS256 | 30min | Authenticate with backend | N/A (login) |
| **Satellite** | `GET /api/v1/token` | RS256 | 60s | Authorize endpoint access | Yes (or guest variant) |
| **Transaction** | `POST /api/v1/accounting/transaction-tokens` | External | Varies | Billing authorization | Yes |
| **Peer** | `POST /api/v1/peer-token` | Internal | Short | NATS P2P communication | Yes (or guest variant) |

---

## 6. Phase 3: Aggregator — RAG Orchestration

### Orchestrator Pipeline

```mermaid
flowchart TD
    REQ[ChatRequest received] --> RESOLVE[Resolve EndpointRefs<br/>→ ResolvedEndpoints]
    RESOLVE --> CHECK_TUNNEL{Any tunneling<br/>endpoints?}

    CHECK_TUNNEL -->|Yes, no peer_token| GEN_PEER[Generate ephemeral<br/>peer_channel UUID]
    CHECK_TUNNEL -->|Yes, has peer_token| RETRIEVE
    CHECK_TUNNEL -->|No tunneling| RETRIEVE
    GEN_PEER --> RETRIEVE

    RETRIEVE[Parallel Retrieval<br/>asyncio.gather per source] --> |SSE: retrieval_start| R_START
    R_START --> R_EACH

    subgraph "Per Data Source (parallel)"
        R_EACH[Query data source] --> R_TYPE{Transport?}
        R_TYPE -->|HTTP| R_HTTP[POST url/query<br/>Bearer satellite_token]
        R_TYPE -->|NATS| R_NATS[Encrypt & publish<br/>to syfthub.spaces.owner]
        R_HTTP --> R_DONE[RetrievalResult]
        R_NATS --> R_DONE
    end

    R_DONE --> |SSE: source_complete| S_COMPLETE
    S_COMPLETE --> ALL_DONE{All sources<br/>complete?}
    ALL_DONE -->|No| R_EACH
    ALL_DONE -->|Yes| |SSE: retrieval_complete| RERANK_CHECK

    RERANK_CHECK{Documents > 0?}
    RERANK_CHECK -->|No| BUILD_PROMPT
    RERANK_CHECK -->|Yes| RERANK

    RERANK[Rerank via ONNX<br/>CENTRAL_REEMBEDDING] --> |SSE: reranking_start/complete| BUILD_PROMPT

    BUILD_PROMPT[PromptBuilder.build<br/>system + context + history + query] --> GEN

    GEN[Generation Service] --> |SSE: generation_start| GEN_TYPE{Transport?}
    GEN_TYPE -->|HTTP| GEN_HTTP[POST model_url/query<br/>Bearer satellite_token]
    GEN_TYPE -->|NATS| GEN_NATS[Encrypt & publish<br/>to syfthub.spaces.owner]

    GEN_HTTP --> STREAM_CHECK{Streaming enabled?}
    GEN_NATS --> STREAM_CHECK

    STREAM_CHECK -->|Yes| TOKENS[Yield token events<br/>SSE: token]
    STREAM_CHECK -->|No| HEARTBEAT[Periodic heartbeat<br/>SSE: generation_heartbeat]

    TOKENS --> ANNOTATE
    HEARTBEAT --> ANNOTATE

    ANNOTATE[Annotate citations<br/>cite:N → cite:N-start:end] --> ATTRIB[Compute profit_share<br/>per source]
    ATTRIB --> |SSE: done| DONE[Final response + metadata]

    style REQ fill:#7B68EE,color:#fff
    style RETRIEVE fill:#27AE60,color:#fff
    style RERANK fill:#E8A838,color:#fff
    style GEN fill:#E74C3C,color:#fff
    style DONE fill:#4A90D9,color:#fff
```

### Retrieval Service Detail

```mermaid
flowchart LR
    subgraph "retrieve() — parallel mode"
        Q[query + data_sources] --> TASKS["asyncio.gather(*tasks)"]
        TASKS --> DS1[Source 1: POST url/query]
        TASKS --> DS2[Source 2: POST url/query]
        TASKS --> DS3[Source 3: NATS tunnel]
        DS1 --> MERGE[Merge all RetrievalResults]
        DS2 --> MERGE
        DS3 --> MERGE
    end

    subgraph "retrieve_streaming() — first-completed mode"
        Q2[query + data_sources] --> TASKS2["asyncio.wait(FIRST_COMPLETED)"]
        TASKS2 --> |"yields as each completes"| YIELD[AsyncGenerator yields<br/>RetrievalResult per source]
    end
```

### Prompt Builder — Context Assembly

```mermaid
flowchart TD
    PB[PromptBuilder.build] --> HAS_CTX{Has retrieved<br/>documents?}

    HAS_CTX -->|No| NO_CTX[System prompt:<br/>"You are a helpful assistant"]
    HAS_CTX -->|Yes| HAS_DICT{context_dict<br/>provided?}

    HAS_DICT -->|Yes| CITE_PATH["Citation path:<br/>System prompt includes numbered docs<br/>[1] Title: content...<br/>Instruct model to use [cite:N]"]
    HAS_DICT -->|No| XML_PATH["XML path:<br/>System prompt wraps docs in XML<br/>&lt;context&gt;&lt;document&gt;...&lt;/document&gt;&lt;/context&gt;"]

    NO_CTX --> ADD_HIST
    CITE_PATH --> ADD_HIST
    XML_PATH --> ADD_HIST

    ADD_HIST{Chat history?}
    ADD_HIST -->|Yes| HIST[Prepend history messages<br/>user/assistant alternating]
    ADD_HIST -->|No| FINAL

    HIST --> FINAL[Final messages array:<br/>system + history + user query]
```

---

## 7. Phase 4: Transport Decision — HTTP vs NATS

```mermaid
flowchart TD
    EP_URL[endpoint.url] --> CHECK{URL starts with<br/>'tunneling:' ?}

    CHECK -->|No → HTTP| HTTP_PATH
    CHECK -->|Yes → NATS| NATS_PATH

    subgraph "HTTP Direct Path"
        HTTP_PATH[Build target URL] --> HTTP_REQ["POST {url}/api/v1/endpoints/{slug}/query"]
        HTTP_REQ --> HTTP_HEADERS["Headers:<br/>Authorization: Bearer {satellite_token}<br/>Content-Type: application/json<br/>X-Transaction-Token: {txn_token}"]
        HTTP_HEADERS --> HTTP_RESP[Parse JSON response]
        HTTP_RESP --> HTTP_RETRY{Status 5xx?}
        HTTP_RETRY -->|Yes, attempts < 2| HTTP_REQ
        HTTP_RETRY -->|No| HTTP_RESULT[Return result]
    end

    subgraph "NATS Tunnel Path"
        NATS_PATH[Extract username from URL<br/>tunneling:alice → alice] --> FETCH_KEY["Fetch space's X25519 public key<br/>GET /api/v1/nats/encryption-key/{username}<br/>(cached 300s)"]
        FETCH_KEY --> ENCRYPT[Generate ephemeral keypair<br/>ECDH + HKDF → AES key<br/>AES-256-GCM encrypt payload]
        ENCRYPT --> PUB["Publish to NATS<br/>subject: syfthub.spaces.{username}"]
        PUB --> SUB["Subscribe to reply<br/>subject: syfthub.peer.{peer_channel}"]
        SUB --> WAIT[Wait for response<br/>timeout: 30s data / 120s model]
        WAIT --> DECRYPT[Decrypt response<br/>ECDH with retained ephemeral key]
        DECRYPT --> NATS_RESULT[Return result]
    end

    style CHECK fill:#E8A838,color:#fff
    style HTTP_PATH fill:#4A90D9,color:#fff
    style NATS_PATH fill:#27AE60,color:#fff
```

---

## 8. Phase 5: NATS Tunnel Protocol

### Message Flow

```mermaid
sequenceDiagram
    participant AG as Aggregator
    participant HUB as Hub Backend
    participant NATS as NATS Broker
    participant SP as Space (Desktop/CLI)

    Note over AG: Need to call endpoint owned by "alice"<br/>URL = "tunneling:alice"

    AG->>HUB: GET /api/v1/nats/encryption-key/alice
    HUB-->>AG: {encryption_public_key: "base64url..."}
    Note over AG: Cache key for 300s

    AG->>AG: Generate ephemeral X25519 keypair<br/>(eph_priv, eph_pub)
    AG->>AG: shared = ECDH(eph_priv, alice_pub)
    AG->>AG: aes_key = HKDF(shared, info="syfthub-tunnel-request-v1")
    AG->>AG: ciphertext = AES-256-GCM(aes_key, nonce, payload, AAD=correlation_id)

    AG->>NATS: PUB syfthub.spaces.alice<br/>{protocol, correlation_id, reply_to,<br/>encryption_info, encrypted_payload}

    NATS->>SP: Deliver message

    SP->>SP: shared = ECDH(alice_priv, eph_pub)
    SP->>SP: aes_key = HKDF(shared, info="syfthub-tunnel-request-v1")
    SP->>SP: payload = AES-256-GCM.Open(aes_key, nonce, ciphertext, AAD=correlation_id)

    SP->>SP: Verify satellite_token<br/>Look up endpoint by slug<br/>Invoke handler

    SP->>SP: Generate fresh ephemeral keypair<br/>(resp_eph_priv, resp_eph_pub)
    SP->>SP: shared = ECDH(resp_eph_priv, req_eph_pub)
    SP->>SP: aes_key = HKDF(shared, info="syfthub-tunnel-response-v1")
    SP->>SP: ciphertext = AES-256-GCM(aes_key, nonce, response, AAD=correlation_id)

    SP->>NATS: PUB syfthub.peer.{peer_channel}<br/>{protocol, correlation_id, status,<br/>encryption_info, encrypted_payload, timing}

    NATS-->>AG: Deliver response

    AG->>AG: shared = ECDH(eph_priv, resp_eph_pub)
    AG->>AG: aes_key = HKDF(shared, info="syfthub-tunnel-response-v1")
    AG->>AG: response = AES-256-GCM.Open(...)
```

### NATS Subject Naming

```mermaid
graph LR
    subgraph "Subject Namespace"
        S1["syfthub.spaces.{username}"]
        S2["syfthub.peer.{peer_channel}"]
    end

    AG[Aggregator] -->|"publishes request"| S1
    SP[Space] -->|"subscribes"| S1
    SP -->|"publishes response"| S2
    AG -->|"subscribes"| S2

    style S1 fill:#27AE60,color:#fff
    style S2 fill:#E8A838,color:#fff
```

### Wire Message Format

```mermaid
classDiagram
    class TunnelRequest {
        +protocol: "syfthub-tunnel/v1"
        +type: "endpoint_request"
        +correlation_id: UUID
        +reply_to: peer_channel
        +endpoint: EndpointInfo
        +satellite_token: string
        +timeout_ms: int
        +encryption_info: EncryptionInfo
        +encrypted_payload: base64url
    }

    class TunnelResponse {
        +protocol: "syfthub-tunnel/v1"
        +type: "endpoint_response"
        +correlation_id: UUID
        +status: "success" | "error"
        +endpoint_slug: string
        +encryption_info: EncryptionInfo
        +encrypted_payload: base64url
        +error: ErrorInfo?
        +timing: TimingInfo
    }

    class EncryptionInfo {
        +algorithm: "X25519-ECDH-AES-256-GCM"
        +ephemeral_public_key: base64url
        +nonce: base64url (12 bytes)
    }

    class EndpointInfo {
        +slug: string
        +type: "model" | "data_source"
    }

    class TimingInfo {
        +received_at: ISO8601
        +processed_at: ISO8601
        +duration_ms: int
    }

    TunnelRequest --> EncryptionInfo
    TunnelRequest --> EndpointInfo
    TunnelResponse --> EncryptionInfo
    TunnelResponse --> TimingInfo
```

---

## 9. Phase 6: Desktop/CLI — Endpoint Execution

### Space Startup Flow

```mermaid
sequenceDiagram
    participant App as Desktop App
    participant FS as Filesystem
    participant HUB as Hub Backend
    participant NATS as NATS Broker

    App->>FS: Load settings.json<br/>(~/.config/syfthub/)
    App->>HUB: Authenticate with API key
    HUB-->>App: username, user info

    App->>App: Set SPACE_URL = tunneling:{username}

    alt Key file exists
        App->>FS: Load X25519 keypair<br/>(~/.config/syfthub/tunnel_key)
    else First run
        App->>App: Generate X25519 keypair
        App->>FS: Save key atomically<br/>(O_CREATE|O_EXCL, mode 0600)
    end

    App->>HUB: PUT /api/v1/nats/encryption-key<br/>{encryption_public_key: base64url}

    App->>FS: Scan endpoints directory<br/>(README.md frontmatter + runner.py)
    App->>App: Build endpoint registry

    App->>HUB: POST /api/v1/endpoints/sync<br/>(register all endpoints with hub)

    App->>HUB: GET /api/v1/nats/credentials
    HUB-->>App: {nats_url, auth_token}

    App->>NATS: Connect(url, token)<br/>Subscribe("syfthub.spaces.{username}")
    Note over App,NATS: Ready to receive requests
```

### Request Processing Pipeline

```mermaid
flowchart TD
    MSG[NATS Message Received] --> PARSE[Parse JSON → TunnelRequest]
    PARSE --> ENC_CHECK{encryption_info &<br/>encrypted_payload present?}

    ENC_CHECK -->|No| REJECT[Reject — no plaintext allowed]
    ENC_CHECK -->|Yes| DECRYPT[Decrypt payload<br/>X25519 ECDH + AES-256-GCM]

    DECRYPT --> VERIFY[Verify satellite_token<br/>POST /api/v1/verify]
    VERIFY --> LOOKUP[Registry.Get(slug)]
    LOOKUP --> ENABLED{Endpoint enabled?}

    ENABLED -->|No| ERR_DISABLED[Error: ENDPOINT_DISABLED]
    ENABLED -->|Yes| TYPE_CHECK{Endpoint type?}

    TYPE_CHECK -->|data_source| DS_PARSE[Parse DataSourceQueryRequest<br/>Extract query from messages]
    TYPE_CHECK -->|model| M_PARSE[Parse ModelQueryRequest<br/>Extract messages array]

    DS_PARSE --> INVOKE
    M_PARSE --> INVOKE

    INVOKE{File-based endpoint?}
    INVOKE -->|Yes| SUBPROCESS[SubprocessExecutor.Execute<br/>Python handler via stdin/stdout]
    INVOKE -->|No| IN_MEMORY[Call registered Go handler]

    SUBPROCESS --> RESPONSE[Build TunnelResponse]
    IN_MEMORY --> RESPONSE

    RESPONSE --> ENC_RESP[Encrypt response<br/>Fresh ephemeral keypair]
    ENC_RESP --> PUBLISH["Publish to NATS<br/>syfthub.peer.{peer_channel}"]

    style MSG fill:#27AE60,color:#fff
    style DECRYPT fill:#E8A838,color:#fff
    style VERIFY fill:#E74C3C,color:#fff
    style PUBLISH fill:#4A90D9,color:#fff
```

---

## 10. Phase 7: Response Assembly & Streaming

```mermaid
flowchart TD
    subgraph "Aggregator Response Assembly"
        GEN_RESULT[Generation result<br/>(raw text with cite:N tags)] --> ANNOTATE["Annotate citations<br/>[cite:N] → [cite:N-start:end]"]
        ANNOTATE --> ATTRIB[Compute profit_share<br/>per source using attribution lib]
        ATTRIB --> BUILD_RESP[Build final response<br/>+ sources + metadata + usage]
        BUILD_RESP --> SSE_DONE["Emit SSE: done"]
    end

    subgraph "Frontend Response Processing"
        SSE_DONE --> PARSE_EVT[Parse done event]
        PARSE_EVT --> UPDATE_STATE[Dispatch SET_COMPLETE<br/>phase = complete]
        UPDATE_STATE --> ON_COMPLETE[onComplete callback]
        ON_COMPLETE --> ADD_MSG[Add assistant message<br/>to message history]
        ADD_MSG --> PARSE_CIT[parseCitations<br/>extract cite:N-start:end markers]
        PARSE_CIT --> BUILD_MD[buildCitedMarkdown<br/>inject HTML mark + sup badges]
        BUILD_MD --> RENDER[Render MarkdownMessage<br/>with highlighted citations]
    end

    style GEN_RESULT fill:#7B68EE,color:#fff
    style RENDER fill:#4A90D9,color:#fff
```

---

## 11. SSE Event Lifecycle

```mermaid
sequenceDiagram
    participant AG as Aggregator
    participant FE as Frontend

    Note over AG,FE: SSE Stream (text/event-stream)

    AG->>FE: event: retrieval_start<br/>data: {"sources": 3}
    Note over FE: Initialize progress bar

    AG->>FE: event: source_complete<br/>data: {"path": "alice/docs", "status": "success", "documents": 12}
    AG->>FE: event: source_complete<br/>data: {"path": "bob/wiki", "status": "success", "documents": 8}
    AG->>FE: event: source_complete<br/>data: {"path": "carol/faq", "status": "error", "documents": 0}
    Note over FE: Update per-source status

    AG->>FE: event: retrieval_complete<br/>data: {"total_documents": 20, "time_ms": 1523}
    Note over FE: Mark retrieval phase done

    AG->>FE: event: reranking_start<br/>data: {"documents": 20}
    AG->>FE: event: reranking_complete<br/>data: {"documents": 5, "time_ms": 342}
    Note over FE: Show reranked count

    AG->>FE: event: generation_start<br/>data: {}
    Note over FE: Show "Generating..."

    loop Every token chunk
        AG->>FE: event: token<br/>data: {"content": "The key "}
        AG->>FE: event: token<br/>data: {"content": "features are "}
        AG->>FE: event: token<br/>data: {"content": "[cite:1] ..."}
    end

    loop Every ~500ms (if non-streaming model)
        AG->>FE: event: generation_heartbeat<br/>data: {"elapsed_ms": 2500}
    end

    AG->>FE: event: done<br/>data: {"response": "...", "sources": {...},<br/>"metadata": {...}, "usage": {...}, "profit_share": {...}}
    Note over FE: Display final response with citations
```

### SSE Event Types Reference

| Event | Payload | Phase | Purpose |
|-------|---------|-------|---------|
| `retrieval_start` | `{sources: N}` | Retrieval | N data sources will be queried |
| `source_complete` | `{path, status, documents}` | Retrieval | One source finished |
| `retrieval_complete` | `{total_documents, time_ms}` | Retrieval | All sources done |
| `reranking_start` | `{documents: N}` | Reranking | Starting to rerank N docs |
| `reranking_complete` | `{documents: N, time_ms}` | Reranking | Top N selected after rerank |
| `generation_start` | `{}` | Generation | LLM generation beginning |
| `generation_heartbeat` | `{elapsed_ms}` | Generation | Periodic liveness signal |
| `token` | `{content: "..."}` | Generation | Streamed response chunk |
| `done` | `{response, sources, metadata, usage, profit_share}` | Complete | Final result |
| `error` | `{message: "..."}` | Error | Pipeline failure |

---

## 12. Authentication & Token Architecture

```mermaid
graph TB
    subgraph "Token Hierarchy"
        HUB_TOKEN["Hub Access Token<br/>HS256 · 30min<br/>Authenticates user with backend"]
        SAT_TOKEN["Satellite Token<br/>RS256 · 60s<br/>Authorizes endpoint access"]
        TXN_TOKEN["Transaction Token<br/>External · varies<br/>Billing authorization"]
        PEER_TOKEN["Peer Token<br/>Internal · short<br/>NATS P2P auth"]
        GUEST_SAT["Guest Satellite Token<br/>RS256 · 60s<br/>sub=guest, no auth needed"]
    end

    USER[User Login] -->|"POST /api/v1/auth/login"| HUB_TOKEN
    HUB_TOKEN -->|"GET /api/v1/token?aud=X"| SAT_TOKEN
    HUB_TOKEN -->|"POST /api/v1/accounting/transaction-tokens"| TXN_TOKEN
    HUB_TOKEN -->|"POST /api/v1/peer-token"| PEER_TOKEN

    ANON[Anonymous User] -->|"GET /api/v1/token/guest?aud=X"| GUEST_SAT
    ANON -->|"POST /api/v1/nats/guest-peer-token"| PEER_TOKEN

    SAT_TOKEN -->|"in ChatRequest.endpoint_tokens"| AG[Aggregator]
    TXN_TOKEN -->|"in ChatRequest.transaction_tokens"| AG
    PEER_TOKEN -->|"in ChatRequest.peer_token"| AG
    GUEST_SAT -->|"in ChatRequest.endpoint_tokens"| AG

    AG -->|"Authorization: Bearer {sat_token}"| EP[Endpoint]
    AG -->|"X-Transaction-Token: {txn}"| EP

    style HUB_TOKEN fill:#E8A838,color:#fff
    style SAT_TOKEN fill:#4A90D9,color:#fff
    style TXN_TOKEN fill:#E74C3C,color:#fff
    style PEER_TOKEN fill:#27AE60,color:#fff
```

### Satellite Token Claims

```mermaid
classDiagram
    class SatelliteToken {
        +sub: user_id (or "guest")
        +aud: target_owner_username
        +iss: hub_url
        +exp: now + 60s
        +role: "admin" | "user" | "guest"
        +iat: now
        +kid: key_id
        ---
        Signing: RS256
        Verification: JWKS at /.well-known/jwks.json
    }
```

---

## 13. NATS Encryption Protocol

```mermaid
graph TB
    subgraph "Request Encryption (Aggregator → Space)"
        A1[Generate ephemeral keypair<br/>eph_priv, eph_pub] --> A2["ECDH(eph_priv, space_longterm_pub)<br/>→ shared_secret"]
        A2 --> A3["HKDF-SHA256(shared_secret)<br/>info='syfthub-tunnel-request-v1'<br/>→ 32-byte AES key"]
        A3 --> A4["AES-256-GCM.Seal(key, nonce, payload)<br/>AAD = correlation_id"]
        A4 --> A5["Send: eph_pub + nonce + ciphertext"]
    end

    subgraph "Request Decryption (Space)"
        B1["Receive: eph_pub + nonce + ciphertext"] --> B2["ECDH(space_longterm_priv, eph_pub)<br/>→ same shared_secret"]
        B2 --> B3["HKDF-SHA256(shared_secret)<br/>info='syfthub-tunnel-request-v1'<br/>→ same AES key"]
        B3 --> B4["AES-256-GCM.Open(key, nonce, ciphertext)<br/>AAD = correlation_id"]
    end

    subgraph "Response Encryption (Space → Aggregator)"
        C1["Generate fresh ephemeral keypair<br/>resp_eph_priv, resp_eph_pub"] --> C2["ECDH(resp_eph_priv, request_eph_pub)<br/>→ response_shared_secret"]
        C2 --> C3["HKDF-SHA256(response_shared_secret)<br/>info='syfthub-tunnel-response-v1'<br/>← different info!"]
        C3 --> C4["AES-256-GCM.Seal(key, nonce, response)<br/>AAD = correlation_id"]
        C4 --> C5["Send: resp_eph_pub + nonce + ciphertext"]
    end

    subgraph "Response Decryption (Aggregator)"
        D1["Receive: resp_eph_pub + nonce + ciphertext"] --> D2["ECDH(request_eph_priv, resp_eph_pub)<br/>→ same response_shared_secret"]
        D2 --> D3["HKDF-SHA256(response_shared_secret)<br/>info='syfthub-tunnel-response-v1'<br/>→ same AES key"]
        D3 --> D4["AES-256-GCM.Open(key, nonce, ciphertext)<br/>AAD = correlation_id"]
    end

    A5 -.->|"NATS"| B1
    C5 -.->|"NATS"| D1

    style A4 fill:#E74C3C,color:#fff
    style B4 fill:#27AE60,color:#fff
    style C4 fill:#E74C3C,color:#fff
    style D4 fill:#27AE60,color:#fff
```

### Key Properties

| Property | Value |
|----------|-------|
| **Key Agreement** | X25519 ECDH |
| **KDF** | HKDF-SHA256, no salt |
| **Symmetric Cipher** | AES-256-GCM (12-byte nonce) |
| **AAD** | correlation_id (UUID) |
| **Domain Separation** | Request: `syfthub-tunnel-request-v1`, Response: `syfthub-tunnel-response-v1` |
| **Forward Secrecy** | Yes — ephemeral keys per request and per response |
| **Key Persistence** | Space long-term key on disk (mode 0600), aggregator ephemeral per-request |

---

## 14. Branch Logic: Streaming vs Non-Streaming

```mermaid
flowchart TD
    REQ[Chat Request] --> STREAM{request.stream?}

    STREAM -->|true| STREAM_PATH
    STREAM -->|false| SYNC_PATH

    subgraph "Streaming Path (POST /chat/stream)"
        STREAM_PATH[StreamingResponse<br/>media_type=text/event-stream] --> S_RET[retrieve_streaming<br/>asyncio.wait FIRST_COMPLETED]
        S_RET --> S_YIELD[Yield source_complete<br/>as each source finishes]
        S_YIELD --> S_RERANK[Rerank if documents > 0]
        S_RERANK --> S_GEN_CHECK{model_streaming_enabled?}

        S_GEN_CHECK -->|true| S_GEN_STREAM["generate_stream()<br/>yield token events"]
        S_GEN_CHECK -->|false| S_GEN_SYNC["generate() as asyncio.Task<br/>yield heartbeat every 500ms<br/>until task completes"]

        S_GEN_STREAM --> S_DONE[Yield done event]
        S_GEN_SYNC --> S_DONE
    end

    subgraph "Non-Streaming Path (POST /chat)"
        SYNC_PATH[JSON Response] --> NS_RET["retrieve()<br/>asyncio.gather all sources"]
        NS_RET --> NS_RERANK[Rerank]
        NS_RERANK --> NS_GEN["generate()<br/>single call, await result"]
        NS_GEN --> NS_RESP[Return ChatResponse JSON]
    end

    style STREAM fill:#E8A838,color:#fff
    style S_GEN_STREAM fill:#27AE60,color:#fff
    style S_GEN_SYNC fill:#7B68EE,color:#fff
```

---

## 15. Branch Logic: Authenticated vs Guest

```mermaid
flowchart TD
    USER_CHECK{User authenticated?}

    USER_CHECK -->|Yes| AUTH_PATH
    USER_CHECK -->|No| GUEST_PATH

    subgraph "Authenticated Path"
        AUTH_PATH[Has hub access token] --> AUTH_SAT["GET /api/v1/token?aud={owner}<br/>per unique owner"]
        AUTH_SAT --> AUTH_TXN["POST /api/v1/accounting/transaction-tokens<br/>{owner_usernames: [...]}"]
        AUTH_TXN --> AUTH_PEER{Tunneling endpoints?}
        AUTH_PEER -->|Yes| AUTH_PEER_TOK["POST /api/v1/peer-token<br/>{target_usernames: [...]}"]
        AUTH_PEER -->|No| AUTH_BUILD[Build request]
        AUTH_PEER_TOK --> AUTH_BUILD
    end

    subgraph "Guest Path"
        GUEST_PATH[No authentication] --> GUEST_SAT["GET /api/v1/token/guest?aud={owner}<br/>(IP rate-limited)"]
        GUEST_SAT --> GUEST_TXN[No transaction tokens<br/>guests cannot be billed]
        GUEST_TXN --> GUEST_PEER{Tunneling endpoints?}
        GUEST_PEER -->|Yes| GUEST_PEER_TOK["POST /api/v1/nats/guest-peer-token<br/>(IP rate-limited)"]
        GUEST_PEER -->|No| GUEST_BUILD[Build request]
        GUEST_PEER_TOK --> GUEST_BUILD
    end

    AUTH_BUILD --> SEND[Send to Aggregator]
    GUEST_BUILD --> SEND

    subgraph "Endpoint-Side Verification"
        SEND --> EP_VERIFY{Space verifies token}
        EP_VERIFY --> ROLE_CHECK{token.role?}
        ROLE_CHECK -->|"user/admin"| FULL_ACCESS[Full access<br/>policies may apply]
        ROLE_CHECK -->|"guest"| GUEST_CHECK{Endpoint allows<br/>guest access?}
        GUEST_CHECK -->|Yes| LIMITED[Limited access<br/>no billing]
        GUEST_CHECK -->|No| DENIED[403 POLICY_DENIED]
    end

    style AUTH_PATH fill:#4A90D9,color:#fff
    style GUEST_PATH fill:#95A5A6,color:#fff
    style DENIED fill:#E74C3C,color:#fff
```

---

## 16. Citation & Attribution Pipeline

```mermaid
flowchart TD
    subgraph "1. Prompt Construction"
        DOCS[Retrieved documents] --> NUMBER["Number documents:<br/>[1] Title: content...<br/>[2] Title: content..."]
        NUMBER --> SYSTEM["System prompt instructs:<br/>'Use [cite:N] to reference sources'"]
        SYSTEM --> LLM[Send to LLM]
    end

    subgraph "2. LLM Generation"
        LLM --> RAW["Raw response:<br/>'The key feature [cite:1] is<br/>performance [cite:2]...'"]
    end

    subgraph "3. Aggregator Annotation"
        RAW --> ANNOTATE["_annotate_cite_positions():<br/>[cite:1] → [cite:1-0:15]<br/>[cite:2] → [cite:2-20:42]<br/>(adds character positions)"]
        ANNOTATE --> ATTRIB["_compute_attribution():<br/>Count cite references per source<br/>→ profit_share: {owner/slug: 0.6, ...}"]
    end

    subgraph "4. Frontend Rendering"
        ATTRIB --> FE_PARSE["parseCitations():<br/>Extract [cite:N-start:end] markers"]
        FE_PARSE --> FE_BUILD["buildCitedMarkdown():<br/>Inject HTML highlights<br/>&lt;mark&gt; + &lt;sup&gt; badges"]
        FE_BUILD --> RENDER["Render with click-to-source<br/>highlight + source panel"]
    end

    style LLM fill:#7B68EE,color:#fff
    style ANNOTATE fill:#E8A838,color:#fff
    style RENDER fill:#4A90D9,color:#fff
```

---

## 17. Error Handling Across Layers

```mermaid
flowchart TD
    subgraph "Frontend Errors"
        FE1[Validation Error] --> FE_SHOW[Show inline error]
        FE2[AuthenticationError] --> FE_REAUTH[Prompt re-login]
        FE3[AggregatorError] --> FE_MSG[Show error message]
        FE4[AbortError] --> FE_CANCEL[Silently cancel]
        FE5[Network Error] --> FE_RETRY[Show connection error]
    end

    subgraph "Aggregator Errors"
        AG1[Retrieval timeout] --> AG_PARTIAL["Per-source error<br/>SSE: source_complete status=timeout<br/>Continue with other sources"]
        AG2[Retrieval error] --> AG_PARTIAL
        AG3[Reranking failure] --> AG_FALLBACK["Silent fallback<br/>Use raw score sort"]
        AG4[Generation 5xx] --> AG_RETRY["Retry up to 2x"]
        AG5[Generation 403] --> AG_FAIL["SSE: error event<br/>{message: 'Access denied'}"]
        AG6[NATS timeout] --> AG_NATS_ERR["NATSTransportError<br/>→ SSE: error event"]
    end

    subgraph "Space Errors"
        SP1[Decryption failure] --> SP_ERR1["Error: DECRYPTION_FAILED<br/>HTTP 400"]
        SP2[Token invalid] --> SP_ERR2["Error: AUTH_FAILED<br/>HTTP 401"]
        SP3[Endpoint not found] --> SP_ERR3["Error: ENDPOINT_NOT_FOUND<br/>HTTP 404"]
        SP4[Policy denied] --> SP_ERR4["Error: POLICY_DENIED<br/>HTTP 403"]
        SP5[Handler crash] --> SP_ERR5["Error: EXECUTION_FAILED<br/>HTTP 500"]
        SP6[Timeout] --> SP_ERR6["Error: TIMEOUT<br/>HTTP 504"]
    end

    AG_PARTIAL -.-> FE3
    AG_FAIL -.-> FE3
    AG_NATS_ERR -.-> FE3
    SP_ERR1 -.-> AG6
    SP_ERR2 -.-> AG5
```

### Error Code Reference (Space → Aggregator)

| Code | HTTP Status | Meaning |
|------|------------|---------|
| `AUTH_FAILED` | 401 | Satellite token invalid/expired |
| `ENDPOINT_NOT_FOUND` | 404 | Slug not in registry |
| `POLICY_DENIED` | 403 | Endpoint policy rejected request |
| `EXECUTION_FAILED` | 500 | Handler threw an error |
| `TIMEOUT` | 504 | Handler exceeded timeout |
| `INVALID_REQUEST` | 400 | Malformed request payload |
| `ENDPOINT_DISABLED` | 503 | Endpoint exists but disabled |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `DECRYPTION_FAILED` | 400 | NATS payload decrypt error |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

## 18. Data Models Reference

### Request/Response Flow

```mermaid
classDiagram
    class ChatRequest {
        +prompt: string
        +model: EndpointRef
        +data_sources: EndpointRef[]
        +endpoint_tokens: map~string,string~
        +transaction_tokens: map~string,string~
        +peer_token: string?
        +peer_channel: string?
        +top_k: int = 5
        +max_tokens: int = 1024
        +temperature: float = 0.7
        +similarity_threshold: float = 0.5
        +stream: bool
        +messages: Message[]
        +custom_system_prompt: string?
        +retrieval_only: bool = false
    }

    class EndpointRef {
        +url: string
        +slug: string
        +name: string
        +tenant_name: string?
        +owner_username: string?
        +query_override: string?
    }

    class Message {
        +role: "system"|"user"|"assistant"
        +content: string
    }

    class ChatResponse {
        +response: string
        +sources: map~string,DocumentSource~
        +retrieval_info: SourceInfo[]
        +metadata: ResponseMetadata
        +usage: TokenUsage?
        +profit_share: map~string,float~?
    }

    class DocumentSource {
        +slug: string
        +content: string
    }

    class ResponseMetadata {
        +retrieval_time_ms: int
        +generation_time_ms: int
        +total_time_ms: int
    }

    class TokenUsage {
        +prompt_tokens: int
        +completion_tokens: int
        +total_tokens: int
    }

    ChatRequest --> EndpointRef
    ChatRequest --> Message
    ChatResponse --> DocumentSource
    ChatResponse --> ResponseMetadata
    ChatResponse --> TokenUsage
```

### Retrieval Data Flow

```mermaid
classDiagram
    class RetrievalResult {
        +source_path: string
        +documents: Document[]
        +status: "success"|"error"|"timeout"
        +error_message: string?
        +latency_ms: int
    }

    class Document {
        +content: string
        +metadata: map
        +score: float
        +title: string?
    }

    class GenerationResult {
        +response: string
        +latency_ms: int
        +usage: TokenUsage?
    }

    class ResolvedEndpoint {
        +path: string
        +url: string
        +slug: string
        +name: string
        +owner_username: string
        +endpoint_type: "model"|"data_source"
        +tenant_name: string?
    }

    RetrievalResult --> Document
```

---

## Appendix A: File Reference

| Layer | Key File | Purpose |
|-------|----------|---------|
| **Frontend** | `components/frontend/src/hooks/use-chat-workflow.ts` | Chat workflow state machine |
| | `components/frontend/src/components/chat/chat-view.tsx` | Chat UI container |
| | `components/frontend/src/components/chat/search-input.tsx` | Query input with model/source selection |
| | `components/frontend/src/lib/citation-utils.ts` | Citation parsing & rendering |
| **TS SDK** | `sdk/typescript/src/resources/chat.ts` | Chat API client, SSE parsing |
| | `sdk/typescript/src/resources/auth.ts` | Token acquisition (satellite, transaction, peer) |
| **Backend** | `components/backend/src/syfthub/api/endpoints/token.py` | Satellite token generation |
| | `components/backend/src/syfthub/api/endpoints/accounting.py` | Transaction token generation |
| | `components/backend/src/syfthub/api/endpoints/peer.py` | Peer token generation |
| **Aggregator** | `components/aggregator/src/aggregator/api/endpoints/chat.py` | Chat endpoint handlers |
| | `components/aggregator/src/aggregator/services/orchestrator.py` | RAG pipeline orchestration |
| | `components/aggregator/src/aggregator/services/retrieval.py` | Data source retrieval |
| | `components/aggregator/src/aggregator/services/model.py` | Model client (HTTP) |
| | `components/aggregator/src/aggregator/services/prompt_builder.py` | Prompt construction |
| | `components/aggregator/src/aggregator/clients/nats_transport.py` | NATS client (aggregator side) |
| **Go SDK** | `sdk/golang/syfthub/chat.go` | Hub client chat/stream |
| | `sdk/golang/syfthub/auth.go` | Token acquisition (Go client) |
| | `sdk/golang/syfthubapi/processor.go` | Request processing pipeline |
| | `sdk/golang/syfthubapi/transport/nats.go` | NATS transport (space side) |
| | `sdk/golang/syfthubapi/transport/crypto.go` | X25519 + AES-256-GCM encryption |
| | `sdk/golang/syfthubapi/transport/http.go` | HTTP transport (space side) |

## Appendix B: Environment Variables

| Component | Variable | Default | Purpose |
|-----------|----------|---------|---------|
| Backend | `SATELLITE_TOKEN_EXPIRE_SECONDS` | 60 | Satellite token TTL |
| Backend | `NATS_AUTH_TOKEN` | — | Required for peer token endpoints |
| Backend | `NATS_WS_PUBLIC_URL` | — | WebSocket URL in peer token response |
| Aggregator | `AGGREGATOR_MODEL_STREAMING_ENABLED` | false | Enable token-by-token streaming from model |
| Aggregator | `AGGREGATOR_SYFTHUB_URL` | — | Hub URL for endpoint resolution |
| Space | `SYFTHUB_URL` | — | Hub backend URL |
| Space | `SYFTHUB_API_KEY` | — | PAT for authentication |
| Space | `SPACE_URL` | — | Public URL or `tunneling:{username}` |
| Space | `SERVER_PORT` | 8000 | HTTP listen port |
| Space | `HEARTBEAT_TTL_SECONDS` | 300 | Health ping interval base |

## Appendix C: Timeout Reference

| Timeout | Value | Context |
|---------|-------|---------|
| Satellite token TTL | 60s | Must re-fetch frequently |
| Data source query | 30s | HTTP proxy timeout |
| Model query | 120s | HTTP proxy timeout |
| NATS request timeout | `timeout_ms` in request or 120s default | Per-request configurable |
| Hub API call | 30s | Default httpx timeout |
| Aggregator API call | 120s | Default for generation |
| Heartbeat interval | TTL × 0.8 (default 240s) | Periodic health ping |
| Encryption key cache | 300s | Aggregator caches space public keys |
