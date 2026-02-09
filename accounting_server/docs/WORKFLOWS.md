# System Workflows

Visual sequence diagrams for the main workflows in the Unified Global Ledger.

---

## Table of Contents

1. [P2P Transfer](#1-p2p-transfer)
2. [Deposit Flow](#2-deposit-flow)
3. [Withdrawal Flow](#3-withdrawal-flow)
4. [PIX Payment (Brazil)](#4-pix-payment-brazil)
5. [Xendit Invoice Payment (Southeast Asia)](#5-xendit-invoice-payment-southeast-asia)
6. [Idempotency Handling](#6-idempotency-handling)
7. [Webhook Processing](#7-webhook-processing)
8. [API Token Authentication](#8-api-token-authentication)
9. [API Token Management](#9-api-token-management)

---

## 1. P2P Transfer

Internal credit transfer between two accounts with confirmation flow.

```mermaid
sequenceDiagram
    autonumber
    participant Sender as Sender Client
    participant API as Ledger API
    participant DB as PostgreSQL
    participant Recipient as Recipient Client

    Sender->>+API: POST /v1/transfers
    Note right of Sender: Idempotency-Key: uuid<br/>source_account_id<br/>destination_account_id<br/>amount: 1000 CREDIT

    API->>+DB: BEGIN TRANSACTION

    API->>DB: Check idempotency key
    DB-->>API: Key not found

    API->>DB: Lock source & dest accounts (ORDER BY id)
    Note right of DB: Prevents deadlock

    DB-->>API: Accounts locked

    API->>API: Validate sufficient balance

    alt Insufficient Funds
        API-->>Sender: 422 Insufficient Funds
    end

    API->>DB: Debit source account<br/>(balance -= 1000, available -= 1000)
    API->>DB: Credit destination account<br/>(balance += 1000, available += 1000)
    API->>DB: Create transaction record
    API->>DB: Create ledger entries (debit + credit)
    API->>DB: Store idempotency result

    API->>DB: COMMIT
    DB-->>-API: Success

    API-->>-Sender: 201 Created<br/>status: completed

    Note over Sender,Recipient: Funds transferred instantly
```

### Transfer with Confirmation (Optional Flow)

For transfers requiring recipient confirmation:

```mermaid
sequenceDiagram
    autonumber
    participant Sender as Sender
    participant API as Ledger API
    participant DB as PostgreSQL
    participant Recipient as Recipient

    Sender->>+API: POST /v1/transfers

    API->>+DB: BEGIN TRANSACTION
    API->>DB: Hold funds (available_balance -= amount)
    API->>DB: Create pending transaction
    API->>DB: Generate confirmation_token
    DB-->>-API: Token: txn_confirm_abc123

    API-->>-Sender: 202 Accepted<br/>status: pending<br/>confirmation_token

    Note over Sender,Recipient: Sender shares token with recipient (out-of-band)

    Recipient->>+API: POST /v1/transfers/confirm
    Note right of Recipient: confirmation_token: txn_confirm_abc123

    API->>+DB: BEGIN TRANSACTION
    API->>DB: Validate token & status
    API->>DB: Transfer funds to recipient
    API->>DB: Create ledger entries
    API->>DB: Update status: completed
    DB-->>-API: Success

    API-->>-Recipient: 200 OK<br/>status: completed

    Note over Sender,Recipient: Or sender can cancel:

    Sender->>+API: POST /v1/transfers/{id}/cancel
    API->>DB: Release held funds
    API->>DB: Update status: cancelled
    API-->>-Sender: 200 OK<br/>status: cancelled
```

---

## 2. Deposit Flow

External funds deposited via payment provider (Stripe example).

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant API as Ledger API
    participant DB as PostgreSQL
    participant Stripe as Stripe
    participant Webhook as Webhook Worker

    Client->>+API: POST /v1/deposits
    Note right of Client: account_id<br/>amount: 50 USD<br/>payment_method_id

    API->>+DB: BEGIN TRANSACTION
    API->>DB: Create pending transaction
    API->>DB: Store idempotency key
    DB-->>-API: Transaction ID: dep_123

    API->>+Stripe: Create PaymentIntent
    Note right of Stripe: amount: 5000 (cents)<br/>currency: USD<br/>payment_method: pm_xxx<br/>confirm: true

    Stripe-->>-API: PaymentIntent created<br/>status: processing

    API-->>-Client: 202 Accepted<br/>status: pending<br/>Location: /v1/deposits/dep_123

    Note over Client,Stripe: Async processing...

    Stripe->>+Webhook: POST /webhooks/stripe
    Note right of Stripe: type: payment_intent.succeeded<br/>id: pi_abc123

    Webhook->>Webhook: Verify signature (HMAC)

    Webhook->>+DB: BEGIN TRANSACTION
    Webhook->>DB: Find transaction by external_reference
    Webhook->>DB: Credit account (balance += 5000)
    Webhook->>DB: Create ledger entry
    Webhook->>DB: Update transaction: completed
    DB-->>-Webhook: Success

    Webhook-->>-Stripe: 200 OK

    Client->>+API: GET /v1/deposits/dep_123
    API->>DB: Query transaction
    API-->>-Client: 200 OK<br/>status: completed<br/>net_credits: 4950 CREDIT
```

---

## 3. Withdrawal Flow

Internal credits withdrawn to external destination.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant API as Ledger API
    participant DB as PostgreSQL
    participant Stripe as Stripe
    participant Webhook as Webhook Worker

    Client->>+API: POST /v1/withdrawals
    Note right of Client: account_id<br/>amount: 2000 CREDIT<br/>payment_method_id

    API->>+DB: BEGIN TRANSACTION
    API->>DB: Lock account (FOR UPDATE)
    DB-->>API: Account locked

    API->>API: Validate available_balance >= 2000

    alt Insufficient Balance
        API-->>Client: 422 Insufficient Funds
    end

    API->>DB: Hold funds<br/>(available_balance -= 2000)
    API->>DB: Create pending withdrawal
    DB-->>-API: Withdrawal ID: wth_456

    API-->>-Client: 202 Accepted<br/>status: pending<br/>estimated_completion: 2-3 days

    Note over API,Stripe: Async payout processing

    API->>+Stripe: Create Payout
    Note right of Stripe: amount: 1980 (after fee)<br/>destination: ba_xxx

    Stripe-->>-API: Payout created<br/>id: po_xyz<br/>arrival_date: 2 days

    Note over Client,Stripe: 1-3 business days later...

    Stripe->>+Webhook: POST /webhooks/stripe
    Note right of Stripe: type: payout.paid<br/>id: po_xyz

    Webhook->>Webhook: Verify signature

    Webhook->>+DB: BEGIN TRANSACTION
    Webhook->>DB: Find withdrawal by external_reference
    Webhook->>DB: Debit account (balance -= 2000)
    Webhook->>DB: Create ledger entries
    Webhook->>DB: Update withdrawal: completed
    DB-->>-Webhook: Success

    Webhook-->>-Stripe: 200 OK

    Note over Client,Webhook: If payout fails:

    rect rgb(255, 230, 230)
        Stripe->>+Webhook: POST /webhooks/stripe
        Note right of Stripe: type: payout.failed<br/>failure_message: "..."

        Webhook->>+DB: BEGIN TRANSACTION
        Webhook->>DB: Release held funds<br/>(available_balance += 2000)
        Webhook->>DB: Update withdrawal: failed
        DB-->>-Webhook: Success

        Webhook-->>-Stripe: 200 OK
    end
```

---

## 4. PIX Payment (Brazil)

Brazilian instant payment flow with QR code.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client App
    participant API as Ledger API
    participant PIX as Efí (PIX Provider)
    participant Payer as Payer's Bank App
    participant Webhook as Webhook Worker

    Client->>+API: POST /v1/pix/charges
    Note right of Client: amount: 15000 (R$150,00)<br/>expires_in_seconds: 3600<br/>description: "Order #123"

    API->>+PIX: Create Cobrança Imediata
    PIX-->>-API: Charge created<br/>txid: abc123<br/>QR code payload

    API-->>-Client: 201 Created<br/>txid: abc123<br/>qr_code (base64 + payload)

    Client->>Client: Display QR Code

    Note over Payer: User scans QR with bank app

    Payer->>+PIX: Scan QR Code
    PIX-->>Payer: Show payment details
    Payer->>PIX: Confirm payment (PIN/biometric)
    PIX->>PIX: Process instant transfer
    PIX-->>-Payer: Payment confirmed

    Note over PIX: Instant notification (~2 seconds)

    PIX->>+Webhook: POST /webhooks/pix
    Note right of PIX: pix[0].txid: abc123<br/>pix[0].valor: "150.00"<br/>pix[0].endToEndId: E00...

    Webhook->>Webhook: Verify mTLS certificate
    Webhook->>Webhook: Validate signature

    Webhook->>+API: Process deposit
    API->>API: Find account by charge metadata
    API->>API: Credit account (15000 CREDIT)
    API->>API: Create ledger entries
    API-->>-Webhook: Success

    Webhook-->>-PIX: 200 OK

    Client->>+API: GET /v1/pix/charges/abc123
    API-->>-Client: status: CONCLUIDA<br/>paid_at: 2026-02-07T12:15:00Z<br/>end_to_end_id: E00...
```

### PIX Key Lookup

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant API as Ledger API
    participant PIX as Efí (PIX Provider)
    participant DICT as Central Bank DICT

    Client->>+API: POST /v1/pix/keys/lookup
    Note right of Client: key_type: cpf<br/>key_value: 12345678901

    API->>+PIX: Query DICT
    PIX->>+DICT: Lookup PIX key
    DICT-->>-PIX: Key info
    PIX-->>-API: Holder details

    API-->>-Client: 200 OK<br/>holder: João Silva<br/>bank: Banco do Brasil<br/>account: ****5678
```

---

## 5. Xendit Invoice Payment (Southeast Asia)

Payment via Xendit invoice (payment link) with multiple payment options.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Merchant App
    participant API as Ledger API
    participant Xendit as Xendit
    participant Customer as Customer
    participant Webhook as Webhook Worker

    Client->>+API: POST /v1/xendit/invoices
    Note right of Client: external_id: order_123<br/>amount: 150000 IDR<br/>payment_methods: [BCA, OVO]

    API->>+Xendit: Create Invoice
    Xendit-->>-API: Invoice created<br/>id: inv_abc<br/>invoice_url: checkout.xendit.co/...

    API-->>-Client: 201 Created<br/>invoice_url: https://checkout.xendit.co/inv_abc

    Client->>Customer: Send payment link (email/SMS/in-app)

    Customer->>+Xendit: Open payment link
    Xendit-->>Customer: Display payment options<br/>(Bank Transfer, E-Wallet, etc.)

    Customer->>Xendit: Select OVO
    Xendit-->>Customer: Redirect to OVO app

    Customer->>Customer: Approve in OVO app

    Customer->>Xendit: Payment completed
    Xendit-->>-Customer: Success page

    Xendit->>+Webhook: POST /webhooks/xendit
    Note right of Xendit: event: invoice.paid<br/>id: inv_abc<br/>paid_amount: 150000

    Webhook->>Webhook: Verify X-Callback-Token

    Webhook->>+API: Process deposit
    API->>API: Find account by metadata
    API->>API: Credit account
    API->>API: Create ledger entries
    API-->>-Webhook: Success

    Webhook-->>-Xendit: 200 OK

    Client->>+API: GET /v1/xendit/invoices/inv_abc
    API-->>-Client: status: PAID<br/>paid_at: 2026-02-07T12:30:00Z
```

### Virtual Account Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as Merchant
    participant API as Ledger API
    participant Xendit as Xendit
    participant Customer as Customer
    participant Bank as Customer's Bank

    Client->>+API: POST /v1/xendit/virtual-accounts
    Note right of Client: bank_code: BCA<br/>name: John Doe<br/>expected_amount: 150000

    API->>+Xendit: Create Virtual Account
    Xendit-->>-API: VA created<br/>account_number: 1234567890

    API-->>-Client: 201 Created<br/>account_number: 1234567890<br/>bank_code: BCA

    Client->>Customer: Display VA details

    Customer->>+Bank: Transfer to VA
    Note right of Customer: Bank: BCA<br/>Account: 1234567890<br/>Amount: 150000

    Bank->>+Xendit: Notify payment
    Xendit-->>-Bank: Confirmed
    Bank-->>-Customer: Transfer success

    Xendit->>+API: POST /webhooks/xendit
    Note right of Xendit: callback_virtual_account_id<br/>amount: 150000

    API->>API: Credit merchant account
    API-->>-Xendit: 200 OK
```

---

## 6. Idempotency Handling

How duplicate requests are handled safely.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant API as Ledger API
    participant Store as Idempotency Store
    participant DB as PostgreSQL

    Note over Client,DB: First Request

    Client->>+API: POST /v1/transfers<br/>Idempotency-Key: key-123

    API->>+Store: Check key-123
    Store-->>-API: Not found

    API->>+DB: Process transfer
    DB-->>-API: Success (txn_abc)

    API->>Store: Store result<br/>key: key-123<br/>response: {id: txn_abc, status: completed}

    API-->>-Client: 201 Created<br/>{id: txn_abc, status: completed}

    Note over Client,DB: Duplicate Request (same body)

    Client->>+API: POST /v1/transfers<br/>Idempotency-Key: key-123

    API->>+Store: Check key-123
    Store-->>-API: Found, hash matches

    Note right of API: Return cached response<br/>No database operation

    API-->>-Client: 201 Created<br/>{id: txn_abc, status: completed}

    Note over Client,DB: Duplicate Key with Different Body

    Client->>+API: POST /v1/transfers<br/>Idempotency-Key: key-123
    Note right of Client: Different amount!

    API->>+Store: Check key-123
    Store-->>-API: Found, hash mismatch!

    API-->>-Client: 422 Unprocessable Entity<br/>Idempotency key reused with different body
```

---

## 7. Webhook Processing

Inbound webhook handling with retry logic.

```mermaid
sequenceDiagram
    autonumber
    participant Provider as Payment Provider
    participant API as Webhook Endpoint
    participant Queue as Message Queue
    participant Worker as Webhook Worker
    participant DB as PostgreSQL

    Provider->>+API: POST /webhooks/stripe
    Note right of Provider: Headers:<br/>Stripe-Signature: t=...,v1=...

    API->>API: Verify HMAC signature

    alt Invalid Signature
        API-->>Provider: 401 Unauthorized
    end

    API->>API: Parse event payload
    API->>API: Check delivery_id (dedup)

    alt Already Processed
        API-->>Provider: 200 OK (duplicate)
    end

    API->>+Queue: Enqueue event
    Queue-->>-API: Queued

    API-->>-Provider: 200 OK
    Note right of Provider: Must respond < 5 seconds

    Queue->>+Worker: Dequeue event

    Worker->>+DB: BEGIN TRANSACTION

    alt payment_intent.succeeded
        Worker->>DB: Find deposit by external_ref
        Worker->>DB: Credit account
        Worker->>DB: Create ledger entries
        Worker->>DB: Update status: completed
    else payout.paid
        Worker->>DB: Find withdrawal by external_ref
        Worker->>DB: Debit account
        Worker->>DB: Create ledger entries
        Worker->>DB: Update status: completed
    else payout.failed
        Worker->>DB: Find withdrawal by external_ref
        Worker->>DB: Release held funds
        Worker->>DB: Update status: failed
    end

    DB-->>-Worker: Success

    Worker->>DB: Mark event processed
    Worker-->>-Queue: ACK

    Note over Worker,Queue: If processing fails:

    rect rgb(255, 230, 230)
        Worker->>Queue: NACK (retry)
        Note right of Queue: Exponential backoff:<br/>1m → 5m → 25m → 2h → 10h

        alt Max Retries Exceeded
            Queue->>Queue: Move to Dead Letter Queue
        end
    end
```

### Outbound Webhook Delivery

```mermaid
sequenceDiagram
    autonumber
    participant API as Ledger API
    participant DB as PostgreSQL
    participant Queue as Delivery Queue
    participant Worker as Delivery Worker
    participant Merchant as Merchant Webhook

    API->>+DB: Transaction completed
    DB-->>-API: Success

    API->>+DB: Find subscribed webhooks
    DB-->>-API: [webhook_1, webhook_2]

    loop For each webhook
        API->>+DB: Create delivery record
        DB-->>-API: delivery_id

        API->>Queue: Enqueue delivery job
    end

    Queue->>+Worker: Dequeue job

    Worker->>Worker: Generate signature<br/>HMAC-SHA256(payload, secret)

    Worker->>+Merchant: POST {webhook_url}
    Note right of Worker: Headers:<br/>X-Webhook-Signature: sha256=...<br/>X-Webhook-Timestamp: 1707307200<br/>X-Delivery-Id: del_123

    alt Success (2xx)
        Merchant-->>-Worker: 200 OK
        Worker->>DB: Mark delivered
    else Failure (4xx/5xx/timeout)
        Merchant-->>Worker: 500 Error
        Worker->>DB: Increment attempts
        Worker->>Queue: Schedule retry<br/>(exponential backoff)
    end

    Worker-->>-Queue: Done
```

---

## Account Balance States

Understanding balance vs available_balance.

```mermaid
stateDiagram-v2
    [*] --> Active: Account Created

    Active --> Active: Transfer In<br/>balance += X<br/>available += X
    Active --> Active: Transfer Out<br/>balance -= X<br/>available -= X

    Active --> PendingWithdrawal: Withdrawal Initiated<br/>available -= X<br/>(balance unchanged)

    PendingWithdrawal --> Active: Withdrawal Completed<br/>balance -= X
    PendingWithdrawal --> Active: Withdrawal Failed<br/>available += X<br/>(released)
    PendingWithdrawal --> Active: Withdrawal Cancelled<br/>available += X

    Active --> Frozen: Admin Freeze
    Frozen --> Active: Admin Unfreeze

    Frozen --> Closed: Admin Close
    Active --> Closed: Admin Close<br/>(if balance = 0)

    Closed --> [*]
```

---

## Transaction State Machine

```mermaid
stateDiagram-v2
    [*] --> Pending: Created

    Pending --> Processing: Provider accepted
    Pending --> Completed: Instant completion
    Pending --> Failed: Validation failed
    Pending --> Cancelled: User cancelled

    Processing --> Completed: Provider confirmed
    Processing --> Failed: Provider rejected

    Completed --> Reversed: Refund processed

    Failed --> [*]
    Cancelled --> [*]
    Reversed --> [*]
    Completed --> [*]
```

---

## Double-Entry Ledger

Every transaction creates balanced entries.

```mermaid
flowchart LR
    subgraph Transfer ["Transfer: Alice → Bob (1000 CREDIT)"]
        direction TB
        T[Transaction<br/>type: transfer<br/>amount: 1000]

        subgraph Entries
            D[Debit Entry<br/>Alice: -1000<br/>balance_after: 4000]
            C[Credit Entry<br/>Bob: +1000<br/>balance_after: 2000]
        end

        T --> D
        T --> C
    end

    style D fill:#ffcccc
    style C fill:#ccffcc
```

```mermaid
flowchart LR
    subgraph Deposit ["Deposit: Stripe → Alice (5000 CREDIT)"]
        direction TB
        T[Transaction<br/>type: deposit<br/>amount: 5000]

        subgraph Entries
            D[Debit Entry<br/>Stripe Pool: -5000]
            C[Credit Entry<br/>Alice: +5000<br/>balance_after: 5000]
        end

        T --> D
        T --> C
    end

    style D fill:#ffcccc
    style C fill:#ccffcc
```

**Invariant**: Sum of all debits = Sum of all credits (always balanced)

---

## 8. API Token Authentication

Authentication flow using API tokens for programmatic access.

```mermaid
sequenceDiagram
    autonumber
    participant Client as API Client
    participant API as Ledger API
    participant Auth as Auth Middleware
    participant TokenSvc as Token Service
    participant DB as PostgreSQL

    Client->>+API: GET /v1/accounts
    Note right of Client: Authorization: Bearer at_abc12345_secret...

    API->>+Auth: Authenticate request

    Auth->>Auth: Detect token type (at_ prefix)

    Auth->>+TokenSvc: validateToken(token, clientIP)

    TokenSvc->>TokenSvc: Parse token format<br/>(at_<prefix>_<secret>)

    TokenSvc->>TokenSvc: Hash token with SHA-256

    TokenSvc->>+DB: Find token by hash
    Note right of DB: WHERE token_hash = $1<br/>AND revoked_at IS NULL

    alt Token Not Found
        DB-->>TokenSvc: null
        TokenSvc-->>Auth: null
        Auth-->>Client: 401 Unauthorized<br/>Invalid or revoked token
    end

    DB-->>-TokenSvc: Token record

    TokenSvc->>TokenSvc: Check expiration

    alt Token Expired
        TokenSvc-->>Auth: null
        Auth-->>Client: 401 Unauthorized<br/>Token expired
    end

    TokenSvc->>DB: Update last_used_at, last_used_ip
    Note right of DB: Async, non-blocking

    TokenSvc-->>-Auth: Valid ApiToken

    Auth->>Auth: Attach user to request<br/>(userId, scopes, isApiToken=true)

    Auth-->>-API: Authenticated

    API->>API: Check required scopes

    alt Missing Scopes
        API-->>Client: 403 Forbidden<br/>Required scopes: accounts:read
    end

    API->>+DB: Query accounts
    DB-->>-API: Account data

    API-->>-Client: 200 OK<br/>Account list
```

### Token Format

```
at_<prefix>_<secret>
│    │        │
│    │        └── 32 random bytes (base64url, ~43 chars)
│    └── 8 hex chars (stored for identification)
└── Type prefix (identifies as API token)
```

### Dual Authentication Flow

```mermaid
flowchart TD
    A[Incoming Request] --> B{Authorization Header?}
    B -->|No| C[401 Missing Authorization]
    B -->|Yes| D{Bearer Token?}
    D -->|No| E[401 Invalid Format]
    D -->|Yes| F{Token starts with 'at_'?}
    F -->|Yes| G[API Token Auth]
    F -->|No| H[JWT Auth]

    G --> I{Token Service<br/>configured?}
    I -->|No| J[401 API tokens<br/>not configured]
    I -->|Yes| K[Validate API Token]
    K --> L{Valid?}
    L -->|No| M[401 Invalid/Expired/Revoked]
    L -->|Yes| N[Attach User<br/>isApiToken=true]

    H --> O[Verify JWT Signature]
    O --> P{Valid?}
    P -->|No| Q[401 Invalid Token]
    P -->|Yes| R[Attach User<br/>isApiToken=false]

    N --> S[Continue to Handler]
    R --> S
```

---

## 9. API Token Management

Lifecycle management for API tokens.

### Token Creation

```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant API as Ledger API
    participant UseCase as ManageApiTokens
    participant DB as PostgreSQL

    User->>+API: POST /v1/api-tokens
    Note right of User: Authorization: Bearer <JWT><br/>name: "CI Pipeline"<br/>scopes: ["accounts:read"]

    API->>API: Verify JWT auth (not API token)

    alt Using API Token
        API-->>User: 403 Forbidden<br/>Cannot create tokens with API token
    end

    API->>API: Validate request body

    API->>+UseCase: createToken(userId, name, scopes)

    UseCase->>+DB: Count user's active tokens
    DB-->>-UseCase: count: 5

    alt Token Limit Reached
        UseCase-->>API: TooManyTokensError
        API-->>User: 429 Too Many Tokens
    end

    UseCase->>UseCase: Generate secure token<br/>at_<prefix>_<secret>

    UseCase->>UseCase: Hash token (SHA-256)

    UseCase->>+DB: Save token record
    Note right of DB: Store: id, user_id, prefix,<br/>token_hash, name, scopes

    DB-->>-UseCase: Saved

    UseCase-->>-API: { token, apiToken }

    API-->>-User: 201 Created<br/>token: at_abc12345_...<br/>⚠️ Only shown once!
```

### Token Revocation

```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant API as Ledger API
    participant UseCase as ManageApiTokens
    participant DB as PostgreSQL

    User->>+API: DELETE /v1/api-tokens/{id}
    Note right of User: Authorization: Bearer <JWT><br/>reason: "Compromised"

    API->>API: Verify JWT auth

    API->>+UseCase: revokeToken(tokenId, userId, reason)

    UseCase->>+DB: Find token by ID
    DB-->>-UseCase: Token record

    alt Token Not Found
        UseCase-->>API: TokenNotFoundError
        API-->>User: 404 Not Found
    end

    alt Token Belongs to Different User
        UseCase-->>API: TokenAuthorizationError
        API-->>User: 403 Forbidden
    end

    alt Already Revoked
        UseCase-->>API: Token (already revoked)
        API-->>User: 200 OK (idempotent)
    end

    UseCase->>UseCase: Set revoked_at, revoked_reason

    UseCase->>+DB: Update token
    DB-->>-UseCase: Updated

    UseCase-->>-API: Revoked token

    API-->>-User: 200 OK<br/>revoked_at: 2026-02-07T...

    Note over User,DB: Token immediately invalid<br/>for authentication
```

### Scope Enforcement

```mermaid
flowchart TD
    A[API Request with Token] --> B{Authenticate}
    B --> C[Token Valid]
    C --> D[Endpoint Handler]
    D --> E{requireScope middleware}

    E --> F{isApiToken?}
    F -->|No/JWT| G[Allow - Full Access]
    F -->|Yes| H{Has required scopes?}

    H -->|Yes| I[Allow Request]
    H -->|No| J[403 Forbidden<br/>Missing scopes]

    subgraph Scopes
        S1[accounts:read]
        S2[accounts:write]
        S3[transactions:read]
        S4[deposits:write]
        S5[withdrawals:write]
        S6[transfers:write]
        S7[payment-methods:read]
        S8[payment-methods:write]
    end
```

### Token Lifecycle States

```mermaid
stateDiagram-v2
    [*] --> Active: Token Created

    Active --> Active: Used for Authentication<br/>(last_used_at updated)

    Active --> Expired: expires_at reached
    Active --> Revoked: User/Admin revokes

    Expired --> [*]: Cannot authenticate
    Revoked --> [*]: Cannot authenticate

    note right of Active: Valid for API access
    note right of Expired: Auto-invalid after expiry
    note right of Revoked: Immediately invalid
```
