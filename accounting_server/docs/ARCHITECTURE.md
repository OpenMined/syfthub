# Unified Global Ledger & Payment Abstraction Layer

## Architecture Design Document

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Domain Model](#3-domain-model)
4. [REST API Design](#4-rest-api-design)
5. [Database Design](#5-database-design)
6. [Payment Provider Abstraction](#6-payment-provider-abstraction)
7. [Transaction Processing & Consistency](#7-transaction-processing--consistency)
8. [Async Settlement & Webhooks](#8-async-settlement--webhooks)
9. [Security Architecture](#9-security-architecture)
10. [Scalability & Resilience](#10-scalability--resilience)
11. [Implementation Roadmap](#11-implementation-roadmap)

---

## 1. Executive Summary

### 1.1 Purpose

A centralized financial orchestration server that acts as an abstraction layer between disparate global payment ecosystems. The system uses an internal unit of account ("Accounting Credits") to enable:

- Seamless P2P transfers within the platform
- Value accumulation in a unified environment
- Standardized integration with external payment providers
- Async settlement to external platforms at user discretion

### 1.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Hexagonal (Ports & Adapters) | Decouples core ledger logic from external payment providers |
| Consistency | Strong (CP system) | Financial transactions require ACID guarantees |
| Database | PostgreSQL | ACID compliance, complex queries, JSON support |
| API Style | REST (Level 2 Richardson) | Wide adoption, cacheable, standard tooling |
| Transaction Model | Double-entry ledger | Audit trail, balance integrity, regulatory compliance |
| Async Pattern | 202 Accepted + Polling/Webhooks | Settlement can take minutes to days |

---

## 2. System Architecture

### 2.1 Hexagonal Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DRIVING ADAPTERS                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  REST API   │  │   Webhooks  │  │     CLI     │  │   Admin Dashboard   │ │
│  │  Controller │  │   Receiver  │  │   Commands  │  │      (Future)       │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼────────────────┼────────────────┼────────────────────┼────────────┘
          │                │                │                    │
          ▼                ▼                ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            INPUT PORTS (Interfaces)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ TransferService │  │ DepositService  │  │    WithdrawalService        │  │
│  │    Interface    │  │    Interface    │  │       Interface             │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────┬───────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION CORE                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          USE CASES                                     │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │   Execute    │ │   Process    │ │   Initiate   │ │   Process    │  │  │
│  │  │   Transfer   │ │   Deposit    │ │  Withdrawal  │ │    Refund    │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        DOMAIN MODEL                                    │  │
│  │  ┌──────────┐ ┌────────────┐ ┌─────────────┐ ┌────────────────────┐   │  │
│  │  │  Account │ │Transaction │ │   Ledger    │ │   PaymentMethod    │   │  │
│  │  │  Entity  │ │   Entity   │ │   Entry     │ │      Entity        │   │  │
│  │  └──────────┘ └────────────┘ └─────────────┘ └────────────────────┘   │  │
│  │  ┌──────────┐                                                         │  │
│  │  │ ApiToken │                                                         │  │
│  │  │  Entity  │                                                         │  │
│  │  └──────────┘                                                         │  │
│  │  ┌──────────┐ ┌────────────┐ ┌─────────────┐                          │  │
│  │  │  Money   │ │IdempotencyK│ │  Transfer   │                          │  │
│  │  │  (VO)    │ │    (VO)    │ │   (VO)      │                          │  │
│  │  └──────────┘ └────────────┘ └─────────────┘                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OUTPUT PORTS (Interfaces)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ AccountRepo     │  │ TransactionRepo │  │   PaymentProviderPort       │  │
│  │   Interface     │  │    Interface    │  │       Interface             │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────┬───────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DRIVEN ADAPTERS                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   PostgreSQL    │  │     Redis       │  │    Payment Provider         │  │
│  │    Adapter      │  │    Adapter      │  │       Adapters              │  │
│  └─────────────────┘  └─────────────────┘  │  ┌───────┐ ┌───────┐        │  │
│                                            │  │Stripe │ │PayPal │ ...    │  │
│                                            │  └───────┘ └───────┘        │  │
│                                            └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **REST API Controller** | HTTP request/response handling, validation, authentication |
| **Use Cases** | Business workflow orchestration, transaction boundaries |
| **Domain Model** | Core business rules, invariant enforcement |
| **Repository Ports** | Abstract data persistence interface |
| **Payment Provider Port** | Abstract external payment operations |
| **Adapters** | Concrete implementations for each external system |

### 2.3 Directory Structure

```
src/
├── domain/                      # Core business logic (no external dependencies)
│   ├── entities/
│   │   ├── Account.ts
│   │   ├── Transaction.ts
│   │   ├── LedgerEntry.ts
│   │   ├── PaymentMethod.ts
│   │   ├── ApiToken.ts          # API token for programmatic access
│   │   └── WithdrawalRequest.ts
│   ├── value-objects/
│   │   ├── Money.ts
│   │   ├── AccountId.ts
│   │   ├── TransactionId.ts
│   │   ├── ApiTokenId.ts         # API token identifier
│   │   └── IdempotencyKey.ts
│   └── errors/
│       ├── InsufficientFundsError.ts
│       ├── AccountNotFoundError.ts
│       ├── TokenNotFoundError.ts    # API token errors
│       └── InvalidTokenError.ts
│
├── application/                 # Use cases and port definitions
│   ├── ports/
│   │   ├── input/              # Driving ports (interfaces for use cases)
│   │   │   ├── TransferService.ts
│   │   │   ├── DepositService.ts
│   │   │   ├── WithdrawalService.ts
│   │   │   └── ApiTokenService.ts   # API token management port
│   │   └── output/             # Driven ports (interfaces for adapters)
│   │       ├── AccountRepository.ts
│   │       ├── TransactionRepository.ts
│   │       ├── IdempotencyStore.ts
│   │       ├── ApiTokenRepository.ts   # API token persistence
│   │       └── PaymentProviderGateway.ts
│   └── use-cases/
│       ├── ExecuteTransfer.ts
│       ├── ProcessDeposit.ts
│       ├── InitiateWithdrawal.ts
│       └── ManageApiTokens.ts       # Token create, list, revoke
│
├── infrastructure/              # External system adapters
│   ├── persistence/
│   │   ├── PostgresAccountRepository.ts
│   │   ├── PostgresTransactionRepository.ts
│   │   ├── PostgresPaymentMethodRepository.ts
│   │   ├── PostgresApiTokenRepository.ts  # API token persistence
│   │   └── TransactionManager.ts
│   ├── cache/
│   │   └── RedisStores.ts           # Idempotency & rate limiting (with in-memory fallback)
│   ├── payment-providers/
│   │   ├── StripeAdapter.ts
│   │   ├── pix/
│   │   │   └── PixAdapter.ts        # Brazilian instant payment (Efí/Gerencianet)
│   │   ├── xendit/
│   │   │   └── XenditAdapter.ts     # Southeast Asia payments
│   │   └── PaymentProviderFactory.ts
│   ├── http/
│   │   ├── controllers/
│   │   │   ├── AccountController.ts
│   │   │   ├── TransferController.ts
│   │   │   ├── DepositController.ts
│   │   │   ├── WithdrawalController.ts
│   │   │   ├── PaymentMethodController.ts
│   │   │   ├── ApiTokenController.ts    # API token management endpoints
│   │   │   ├── WebhookController.ts
│   │   │   ├── PixController.ts         # PIX-specific endpoints
│   │   │   └── XenditController.ts      # Xendit-specific endpoints
│   │   └── middleware/
│   │       ├── authentication.ts
│   │       ├── idempotency.ts
│   │       ├── rateLimiting.ts
│   │       └── errorHandler.ts          # RFC 9457 Problem Details
│
└── main/                        # Composition root
    ├── config.ts
    ├── container.ts             # Dependency injection setup
    └── server.ts
```

---

## 3. Domain Model

### 3.1 Entity Definitions

#### Account (Aggregate Root)

```typescript
interface Account {
  id: AccountId;                    // UUID
  userId: UserId;                   // Owner reference
  type: AccountType;                // 'user' | 'system' | 'escrow'
  status: AccountStatus;            // 'active' | 'frozen' | 'closed'
  balance: Money;                   // Current balance in internal credits
  availableBalance: Money;          // Balance minus pending holds
  currency: 'CREDIT';               // Internal unit of account
  createdAt: Timestamp;
  updatedAt: Timestamp;
  version: number;                  // Optimistic locking
}
```

#### Transaction (Aggregate Root)

```typescript
interface Transaction {
  id: TransactionId;                // UUID
  idempotencyKey: IdempotencyKey;   // Client-provided dedup key
  type: TransactionType;            // 'transfer' | 'deposit' | 'withdrawal' | 'refund'
  status: TransactionStatus;        // 'pending' | 'completed' | 'failed' | 'reversed'

  // Money movement
  sourceAccountId: AccountId | null;
  destinationAccountId: AccountId | null;
  amount: Money;
  fee: Money;

  // External reference (for deposits/withdrawals)
  externalReference: string | null;
  providerCode: ProviderCode | null;

  // Metadata
  description: string;
  metadata: Record<string, unknown>;

  // Audit
  createdAt: Timestamp;
  completedAt: Timestamp | null;
  entries: LedgerEntry[];           // Double-entry records
}
```

#### Ledger Entry (Entity)

```typescript
interface LedgerEntry {
  id: LedgerEntryId;
  transactionId: TransactionId;
  accountId: AccountId;
  entryType: 'debit' | 'credit';
  amount: Money;
  balanceAfter: Money;              // Running balance for audit
  createdAt: Timestamp;
}
```

#### Payment Method (Entity)

```typescript
interface PaymentMethod {
  id: PaymentMethodId;
  accountId: AccountId;
  providerCode: ProviderCode;       // 'stripe' | 'paypal' | 'bank_transfer'
  type: PaymentMethodType;          // 'card' | 'bank_account' | 'wallet'
  status: PaymentMethodStatus;      // 'pending_verification' | 'verified' | 'disabled'

  // Provider-specific reference (tokenized, never raw credentials)
  externalId: string;               // Stripe payment method ID, PayPal vault ID, etc.

  // Display info (masked)
  displayName: string;              // "Visa •••• 4242"

  // For withdrawals
  isWithdrawable: boolean;

  metadata: Record<string, unknown>;
  createdAt: Timestamp;
  updatedAt: Timestamp;
}
```

#### ApiToken (Entity)

```typescript
interface ApiToken {
  id: ApiTokenId;                   // UUID
  userId: UserId;                   // Token owner
  prefix: string;                   // First 8 chars (for identification)
  tokenHash: Buffer;                // SHA-256 hash of full token (never store plaintext)
  name: string;                     // User-provided name ("CI Pipeline")
  scopes: TokenScope[];             // Granted permissions

  // Lifecycle
  createdAt: Timestamp;
  expiresAt: Timestamp | null;      // null = no expiration
  revokedAt: Timestamp | null;      // Set when revoked
  revokedReason: string | null;

  // Usage tracking
  lastUsedAt: Timestamp | null;
  lastUsedIp: string | null;

  version: number;                  // Optimistic locking
}

type TokenScope =
  | 'accounts:read' | 'accounts:write'
  | 'transactions:read'
  | 'deposits:write' | 'withdrawals:write' | 'transfers:write'
  | 'payment-methods:read' | 'payment-methods:write';
```

### 3.2 Value Objects

```typescript
// Immutable money representation
interface Money {
  amount: bigint;                   // Store in smallest unit (cents/credits)
  currency: 'CREDIT' | 'USD' | 'EUR' | string;
}

// Type-safe identifiers
type AccountId = Brand<string, 'AccountId'>;
type TransactionId = Brand<string, 'TransactionId'>;
type IdempotencyKey = Brand<string, 'IdempotencyKey'>;
type ProviderCode = 'stripe' | 'pix' | 'xendit';
```

### 3.3 Domain Events

Domain events are defined as TypeScript interfaces within the entity and use-case files. The following event types are supported for async processing and webhook delivery:

| Event Type | Trigger |
|------------|---------|
| `transfer.completed` | P2P transfer succeeded |
| `deposit.pending` | Deposit initiated |
| `deposit.completed` | Deposit funds credited |
| `deposit.failed` | Deposit failed |
| `withdrawal.pending` | Withdrawal initiated, funds held |
| `withdrawal.completed` | Withdrawal settled |
| `withdrawal.failed` | Withdrawal failed, funds released |
| `refund.completed` | Refund processed |
| `account.created` | New account created |
| `payment_method.verified` | Payment method verified |

Events are published through the webhook delivery system (see Section 8).

---

## 4. REST API Design

### 4.1 Base URL & Versioning

```
Base URL: https://api.ledger.example.com/v1
Versioning: URL path (explicit, cacheable)
```

### 4.2 Authentication

All endpoints require authentication via Bearer token (JWT):

```
Authorization: Bearer <jwt_token>
```

### 4.3 Resource Endpoints

#### 4.3.1 Accounts

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/accounts` | Create a new account | Yes (with Idempotency-Key) |
| `GET` | `/accounts` | List user's accounts | Yes |
| `GET` | `/accounts/{id}` | Get account details | Yes |
| `GET` | `/accounts/{id}/balance` | Get current balance | Yes |
| `GET` | `/accounts/{id}/transactions` | List account transactions | Yes |

**Create Account**
```http
POST /v1/accounts
Content-Type: application/json
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{
  "type": "user",
  "metadata": {
    "display_name": "Main Wallet"
  }
}
```

**Response: 201 Created**
```http
HTTP/1.1 201 Created
Location: /v1/accounts/acc_abc123
Content-Type: application/json

{
  "id": "acc_abc123",
  "type": "user",
  "status": "active",
  "balance": {
    "amount": "0",
    "currency": "CREDIT"
  },
  "available_balance": {
    "amount": "0",
    "currency": "CREDIT"
  },
  "created_at": "2026-02-06T10:00:00Z",
  "metadata": {
    "display_name": "Main Wallet"
  }
}
```

**Get Balance**
```http
GET /v1/accounts/acc_abc123/balance
```

**Response: 200 OK**
```json
{
  "account_id": "acc_abc123",
  "balance": {
    "amount": "10000",
    "currency": "CREDIT"
  },
  "available_balance": {
    "amount": "9500",
    "currency": "CREDIT"
  },
  "pending_deposits": {
    "amount": "0",
    "currency": "CREDIT"
  },
  "pending_withdrawals": {
    "amount": "500",
    "currency": "CREDIT"
  },
  "as_of": "2026-02-06T10:30:00Z"
}
```

#### 4.3.2 Transfers (P2P)

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/transfers` | Execute P2P transfer | Yes (with Idempotency-Key) |
| `GET` | `/transfers/{id}` | Get transfer details | Yes |

**Execute Transfer**
```http
POST /v1/transfers
Content-Type: application/json
Idempotency-Key: 7c9e6679-7425-40de-944b-e07fc1f90ae7

{
  "source_account_id": "acc_abc123",
  "destination_account_id": "acc_def456",
  "amount": {
    "amount": "1000",
    "currency": "CREDIT"
  },
  "description": "Payment for services",
  "metadata": {
    "invoice_id": "inv_789"
  }
}
```

**Response: 201 Created**
```http
HTTP/1.1 201 Created
Location: /v1/transfers/txn_xyz789
Content-Type: application/json

{
  "id": "txn_xyz789",
  "type": "transfer",
  "status": "completed",
  "source_account_id": "acc_abc123",
  "destination_account_id": "acc_def456",
  "amount": {
    "amount": "1000",
    "currency": "CREDIT"
  },
  "fee": {
    "amount": "0",
    "currency": "CREDIT"
  },
  "description": "Payment for services",
  "created_at": "2026-02-06T10:35:00Z",
  "completed_at": "2026-02-06T10:35:00Z",
  "metadata": {
    "invoice_id": "inv_789"
  }
}
```

**Insufficient Funds Response: 422 Unprocessable Entity**
```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json

{
  "type": "https://api.ledger.example.com/problems/insufficient-funds",
  "title": "Insufficient Funds",
  "status": 422,
  "detail": "Account acc_abc123 has insufficient available balance. Required: 1000 CREDIT, Available: 500 CREDIT.",
  "instance": "/v1/transfers",
  "account_id": "acc_abc123",
  "required_amount": "1000",
  "available_amount": "500"
}
```

#### 4.3.3 Deposits (External → Internal)

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/deposits` | Initiate deposit | Yes (with Idempotency-Key) |
| `GET` | `/deposits/{id}` | Get deposit status | Yes |
| `POST` | `/deposits/{id}/confirm` | Manual confirmation (admin) | Yes |

**Initiate Deposit**
```http
POST /v1/deposits
Content-Type: application/json
Idempotency-Key: 9f8e7d6c-5b4a-3c2d-1e0f-123456789abc

{
  "account_id": "acc_abc123",
  "amount": {
    "amount": "5000",
    "currency": "USD"
  },
  "payment_method_id": "pm_stripe_xyz",
  "metadata": {
    "source": "mobile_app"
  }
}
```

**Response: 202 Accepted** (Async processing)
```http
HTTP/1.1 202 Accepted
Location: /v1/deposits/dep_qrs789
Retry-After: 5
Content-Type: application/json

{
  "id": "dep_qrs789",
  "status": "pending",
  "account_id": "acc_abc123",
  "amount": {
    "amount": "5000",
    "currency": "USD"
  },
  "credits_amount": {
    "amount": "5000",
    "currency": "CREDIT"
  },
  "provider_code": "stripe",
  "provider_status": "processing",
  "created_at": "2026-02-06T10:40:00Z",
  "estimated_completion": "2026-02-06T10:45:00Z"
}
```

**Get Deposit Status**
```http
GET /v1/deposits/dep_qrs789
```

**Response: 200 OK** (Completed)
```json
{
  "id": "dep_qrs789",
  "status": "completed",
  "account_id": "acc_abc123",
  "amount": {
    "amount": "5000",
    "currency": "USD"
  },
  "credits_amount": {
    "amount": "5000",
    "currency": "CREDIT"
  },
  "fee": {
    "amount": "50",
    "currency": "CREDIT"
  },
  "net_credits": {
    "amount": "4950",
    "currency": "CREDIT"
  },
  "provider_code": "stripe",
  "external_reference": "pi_abc123xyz",
  "created_at": "2026-02-06T10:40:00Z",
  "completed_at": "2026-02-06T10:42:30Z"
}
```

#### 4.3.4 Withdrawals (Internal → External)

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/withdrawals` | Initiate withdrawal | Yes (with Idempotency-Key) |
| `GET` | `/withdrawals/{id}` | Get withdrawal status | Yes |
| `POST` | `/withdrawals/{id}/cancel` | Cancel pending withdrawal | No |

**Initiate Withdrawal**
```http
POST /v1/withdrawals
Content-Type: application/json
Idempotency-Key: abc12345-def6-7890-ghij-klmnopqrstuv

{
  "account_id": "acc_abc123",
  "amount": {
    "amount": "2000",
    "currency": "CREDIT"
  },
  "payment_method_id": "pm_bank_456",
  "description": "Withdrawal to bank account"
}
```

**Response: 202 Accepted**
```http
HTTP/1.1 202 Accepted
Location: /v1/withdrawals/wth_lmn456
Retry-After: 30
Content-Type: application/json

{
  "id": "wth_lmn456",
  "status": "pending",
  "account_id": "acc_abc123",
  "amount": {
    "amount": "2000",
    "currency": "CREDIT"
  },
  "destination_amount": {
    "amount": "1980",
    "currency": "USD"
  },
  "fee": {
    "amount": "20",
    "currency": "CREDIT"
  },
  "provider_code": "bank_transfer",
  "payment_method_id": "pm_bank_456",
  "created_at": "2026-02-06T11:00:00Z",
  "estimated_completion": "2026-02-08T11:00:00Z"
}
```

#### 4.3.5 Payment Methods

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/payment-methods` | Link new payment method | Yes (with Idempotency-Key) |
| `GET` | `/payment-methods` | List payment methods | Yes |
| `GET` | `/payment-methods/{id}` | Get payment method details | Yes |
| `DELETE` | `/payment-methods/{id}` | Unlink payment method | Yes |
| `POST` | `/payment-methods/{id}/verify` | Verify payment method | Yes (with Idempotency-Key) |

**Link Payment Method**
```http
POST /v1/payment-methods
Content-Type: application/json
Idempotency-Key: pm-link-12345

{
  "account_id": "acc_abc123",
  "provider_code": "stripe",
  "type": "card",
  "provider_token": "tok_visa_4242",
  "set_as_default": true
}
```

**Response: 201 Created**
```json
{
  "id": "pm_stripe_xyz",
  "account_id": "acc_abc123",
  "provider_code": "stripe",
  "type": "card",
  "status": "verified",
  "display_name": "Visa •••• 4242",
  "is_default": true,
  "is_withdrawable": false,
  "expires_at": "2028-12-01T00:00:00Z",
  "created_at": "2026-02-06T11:30:00Z"
}
```

#### 4.3.6 Refunds

| Method | Endpoint | Description | Idempotent |
|--------|----------|-------------|------------|
| `POST` | `/refunds` | Initiate refund | Yes (with Idempotency-Key) |
| `GET` | `/refunds/{id}` | Get refund status | Yes |

**Initiate Refund**
```http
POST /v1/refunds
Content-Type: application/json
Idempotency-Key: refund-txn-xyz789

{
  "transaction_id": "txn_xyz789",
  "amount": {
    "amount": "500",
    "currency": "CREDIT"
  },
  "reason": "customer_request",
  "description": "Partial refund per customer request"
}
```

**Response: 201 Created**
```json
{
  "id": "ref_abc123",
  "status": "completed",
  "original_transaction_id": "txn_xyz789",
  "amount": {
    "amount": "500",
    "currency": "CREDIT"
  },
  "reason": "customer_request",
  "created_at": "2026-02-06T12:00:00Z",
  "completed_at": "2026-02-06T12:00:01Z"
}
```

#### 4.3.7 Transactions (Read-only Query)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/transactions` | List transactions (with filters) |
| `GET` | `/transactions/{id}` | Get transaction details |

**List Transactions with Filters**
```http
GET /v1/transactions?account_id=acc_abc123&type=transfer&status=completed&limit=20&cursor=eyJpZCI6InR4bl8xMjMifQ==
```

**Response: 200 OK**
```json
{
  "data": [
    {
      "id": "txn_xyz789",
      "type": "transfer",
      "status": "completed",
      "source_account_id": "acc_abc123",
      "destination_account_id": "acc_def456",
      "amount": {
        "amount": "1000",
        "currency": "CREDIT"
      },
      "created_at": "2026-02-06T10:35:00Z"
    }
  ],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6InR4bl83ODkifQ=="
  }
}
```

#### 4.3.8 Webhooks (Subscription Management)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhooks` | Register webhook endpoint |
| `GET` | `/webhooks` | List webhooks |
| `GET` | `/webhooks/{id}` | Get webhook details |
| `PATCH` | `/webhooks/{id}` | Update webhook |
| `DELETE` | `/webhooks/{id}` | Delete webhook |

**Register Webhook**
```http
POST /v1/webhooks
Content-Type: application/json

{
  "url": "https://merchant.example.com/webhooks/ledger",
  "events": [
    "deposit.completed",
    "withdrawal.completed",
    "withdrawal.failed",
    "transfer.completed"
  ],
  "secret": "whsec_your_signing_secret"
}
```

**Response: 201 Created**
```json
{
  "id": "wh_abc123",
  "url": "https://merchant.example.com/webhooks/ledger",
  "events": [
    "deposit.completed",
    "withdrawal.completed",
    "withdrawal.failed",
    "transfer.completed"
  ],
  "status": "active",
  "created_at": "2026-02-06T12:30:00Z"
}
```

### 4.4 Pagination

All list endpoints use **cursor-based pagination**:

```http
GET /v1/transactions?limit=20&cursor=eyJpZCI6InR4bl8xMjMifQ==
```

Response includes:
```json
{
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6InR4bl83ODkifQ==",
    "prev_cursor": "eyJpZCI6InR4bl8xMDAifQ=="
  }
}
```

**Rationale**: Cursor pagination provides consistent performance regardless of offset depth and handles concurrent inserts correctly.

### 4.5 Filtering & Sorting

```http
GET /v1/transactions?account_id=acc_abc123&type=transfer,deposit&status=completed&created_after=2026-01-01T00:00:00Z&sort=-created_at
```

| Parameter | Format | Example |
|-----------|--------|---------|
| `type` | Comma-separated values | `type=transfer,deposit` |
| `status` | Comma-separated values | `status=pending,completed` |
| `created_after` | ISO 8601 | `created_after=2026-01-01T00:00:00Z` |
| `created_before` | ISO 8601 | `created_before=2026-02-01T00:00:00Z` |
| `sort` | Field with optional `-` prefix for desc | `sort=-created_at` |

### 4.6 Rate Limiting

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1707220800
```

| Tier | Rate Limit | Burst |
|------|------------|-------|
| Standard | 1000 req/min | 50 |
| Premium | 5000 req/min | 200 |
| Enterprise | Custom | Custom |

### 4.7 Error Response Format (RFC 9457)

All errors use Problem Details format:

```json
{
  "type": "https://api.ledger.example.com/problems/insufficient-funds",
  "title": "Insufficient Funds",
  "status": 422,
  "detail": "Account acc_abc123 has insufficient available balance.",
  "instance": "/v1/transfers",
  "trace_id": "req_abc123xyz"
}
```

### 4.8 Idempotency

All mutating operations require `Idempotency-Key` header:

```http
POST /v1/transfers
Idempotency-Key: 7c9e6679-7425-40de-944b-e07fc1f90ae7
```

Server behavior:
1. Key not found → Process request, store result
2. Key found, body matches → Return stored response
3. Key found, body differs → Return `422 Unprocessable Entity`

Keys expire after 24 hours.

---

## 5. Database Design

### 5.1 Technology Choice

**PostgreSQL** selected for:
- ACID transactions (critical for financial data)
- Complex query support (reporting, analytics)
- JSON/JSONB for flexible metadata
- Excellent concurrency control
- Mature ecosystem

### 5.2 Schema

```sql
-- Core tables
CREATE TABLE accounts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    type            VARCHAR(20) NOT NULL CHECK (type IN ('user', 'system', 'escrow')),
    status          VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'closed')),
    balance         BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
    available_balance BIGINT NOT NULL DEFAULT 0,
    currency        VARCHAR(10) NOT NULL DEFAULT 'CREDIT',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT positive_balance CHECK (balance >= 0),
    CONSTRAINT positive_available CHECK (available_balance >= 0),
    CONSTRAINT available_lte_balance CHECK (available_balance <= balance)
);

CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_status ON accounts(status) WHERE status = 'active';

CREATE TABLE transactions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key     VARCHAR(255) NOT NULL,
    type                VARCHAR(20) NOT NULL CHECK (type IN ('transfer', 'deposit', 'withdrawal', 'refund', 'fee')),
    status              VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'reversed')),

    source_account_id   UUID REFERENCES accounts(id),
    destination_account_id UUID REFERENCES accounts(id),

    amount              BIGINT NOT NULL CHECK (amount > 0),
    fee                 BIGINT NOT NULL DEFAULT 0 CHECK (fee >= 0),
    currency            VARCHAR(10) NOT NULL DEFAULT 'CREDIT',

    external_reference  VARCHAR(255),
    provider_code       VARCHAR(50),

    description         TEXT,
    metadata            JSONB DEFAULT '{}',
    error_details       JSONB,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,

    -- Reference to original transaction (for refunds)
    parent_transaction_id UUID REFERENCES transactions(id),

    CONSTRAINT valid_accounts CHECK (
        (type = 'transfer' AND source_account_id IS NOT NULL AND destination_account_id IS NOT NULL) OR
        (type = 'deposit' AND destination_account_id IS NOT NULL) OR
        (type = 'withdrawal' AND source_account_id IS NOT NULL) OR
        (type IN ('refund', 'fee'))
    )
);

CREATE UNIQUE INDEX idx_transactions_idempotency ON transactions(idempotency_key);
CREATE INDEX idx_transactions_source ON transactions(source_account_id, created_at DESC);
CREATE INDEX idx_transactions_destination ON transactions(destination_account_id, created_at DESC);
CREATE INDEX idx_transactions_status ON transactions(status) WHERE status IN ('pending', 'processing');
CREATE INDEX idx_transactions_type_created ON transactions(type, created_at DESC);

-- Double-entry ledger
CREATE TABLE ledger_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  UUID NOT NULL REFERENCES transactions(id),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    entry_type      VARCHAR(10) NOT NULL CHECK (entry_type IN ('debit', 'credit')),
    amount          BIGINT NOT NULL CHECK (amount > 0),
    balance_after   BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ledger_transaction ON ledger_entries(transaction_id);
CREATE INDEX idx_ledger_account ON ledger_entries(account_id, created_at DESC);

-- Payment methods
CREATE TABLE payment_methods (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID NOT NULL REFERENCES accounts(id),
    provider_code   VARCHAR(50) NOT NULL,
    type            VARCHAR(30) NOT NULL CHECK (type IN ('card', 'bank_account', 'wallet', 'crypto')),
    status          VARCHAR(30) NOT NULL DEFAULT 'pending_verification' CHECK (status IN ('pending_verification', 'verified', 'disabled')),

    external_id     VARCHAR(255) NOT NULL,  -- Provider's token/ID
    display_name    VARCHAR(100) NOT NULL,  -- "Visa •••• 4242"

    is_default      BOOLEAN NOT NULL DEFAULT false,
    is_withdrawable BOOLEAN NOT NULL DEFAULT false,

    metadata        JSONB DEFAULT '{}',
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_provider_external UNIQUE (provider_code, external_id)
);

CREATE INDEX idx_payment_methods_account ON payment_methods(account_id);

-- Idempotency store (could also use Redis)
CREATE TABLE idempotency_keys (
    key             VARCHAR(255) PRIMARY KEY,
    user_id         UUID NOT NULL,
    endpoint        VARCHAR(100) NOT NULL,
    request_hash    VARCHAR(64) NOT NULL,
    response_code   INTEGER NOT NULL,
    response_body   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

-- API tokens for programmatic access
CREATE TABLE api_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    token_prefix    CHAR(8) NOT NULL,
    token_hash      BYTEA NOT NULL,
    name            TEXT NOT NULL,
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    last_used_ip    INET,
    revoked_at      TIMESTAMPTZ,
    revoked_reason  TEXT,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_name_length CHECK (char_length(name) BETWEEN 1 AND 100)
);

-- Fast lookup by hash for authentication
CREATE UNIQUE INDEX idx_api_tokens_hash ON api_tokens (token_hash) WHERE revoked_at IS NULL;
-- List user's tokens efficiently
CREATE INDEX idx_api_tokens_user_id ON api_tokens (user_id, created_at DESC) WHERE revoked_at IS NULL;

-- Webhook subscriptions
CREATE TABLE webhooks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    url             VARCHAR(2048) NOT NULL,
    secret          VARCHAR(255) NOT NULL,
    events          TEXT[] NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhooks_user ON webhooks(user_id);
CREATE INDEX idx_webhooks_events ON webhooks USING GIN(events);

-- Webhook delivery log
CREATE TABLE webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id      UUID NOT NULL REFERENCES webhooks(id),
    event_type      VARCHAR(100) NOT NULL,
    payload         JSONB NOT NULL,

    status          VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'failed')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    next_retry_at   TIMESTAMPTZ,

    response_code   INTEGER,
    response_body   TEXT,
    error_message   TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_deliveries_pending ON webhook_deliveries(next_retry_at) WHERE status = 'pending';
```

### 5.3 Consistency Guarantees

#### Transaction Processing (Transfer Example)

```sql
BEGIN;

-- 1. Lock source account (SELECT FOR UPDATE)
SELECT * FROM accounts WHERE id = :source_id FOR UPDATE;

-- 2. Verify sufficient balance
-- (Application validates available_balance >= amount)

-- 3. Debit source account
UPDATE accounts
SET balance = balance - :amount,
    available_balance = available_balance - :amount,
    version = version + 1,
    updated_at = NOW()
WHERE id = :source_id AND version = :expected_version;

-- 4. Credit destination account
UPDATE accounts
SET balance = balance + :amount,
    available_balance = available_balance + :amount,
    version = version + 1,
    updated_at = NOW()
WHERE id = :destination_id;

-- 5. Create transaction record
INSERT INTO transactions (...) VALUES (...);

-- 6. Create ledger entries (double-entry)
INSERT INTO ledger_entries (transaction_id, account_id, entry_type, amount, balance_after)
VALUES
    (:txn_id, :source_id, 'debit', :amount, :source_new_balance),
    (:txn_id, :destination_id, 'credit', :amount, :dest_new_balance);

COMMIT;
```

#### Optimistic Locking

Account updates use version-based optimistic locking to prevent lost updates:

```typescript
async function updateAccountBalance(accountId: string, delta: bigint, expectedVersion: number): Promise<Account> {
  const result = await db.query(`
    UPDATE accounts
    SET balance = balance + $1,
        version = version + 1,
        updated_at = NOW()
    WHERE id = $2 AND version = $3
    RETURNING *
  `, [delta, accountId, expectedVersion]);

  if (result.rowCount === 0) {
    throw new OptimisticLockError('Account was modified concurrently');
  }

  return result.rows[0];
}
```

---

## 6. Payment Provider Abstraction

### 6.1 Provider Port Interface

```typescript
// Output port - defines what the core expects from payment providers
interface PaymentProviderGateway {
  // Identity
  readonly providerCode: ProviderCode;

  // Deposit flow (external → internal)
  createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent>;
  confirmPaymentIntent(intentId: string): Promise<PaymentConfirmation>;

  // Withdrawal flow (internal → external)
  initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation>;
  getTransferStatus(transferId: string): Promise<TransferStatus>;
  cancelTransfer(transferId: string): Promise<void>;

  // Payment method management
  tokenizePaymentMethod(request: TokenizeRequest): Promise<TokenizedMethod>;
  verifyPaymentMethod(methodId: string): Promise<VerificationResult>;
  deletePaymentMethod(methodId: string): Promise<void>;

  // Refunds
  createRefund(request: RefundRequest): Promise<RefundResult>;

  // Webhooks
  verifyWebhookSignature(payload: string, signature: string): boolean;
  parseWebhookEvent(payload: string): ProviderEvent;
}

// Request/Response types
interface CreatePaymentIntentRequest {
  amount: Money;
  currency: string;
  paymentMethodId: string;
  metadata: Record<string, string>;
}

interface PaymentIntent {
  id: string;
  status: 'requires_payment_method' | 'requires_confirmation' | 'processing' | 'succeeded' | 'failed';
  clientSecret?: string;  // For client-side confirmation
}

interface InitiateTransferRequest {
  amount: Money;
  currency: string;
  destination: {
    type: 'bank_account' | 'card' | 'wallet';
    externalId: string;
  };
  metadata: Record<string, string>;
}

interface TransferInitiation {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  estimatedArrival?: Date;
}
```

### 6.2 Adapter Implementations

#### Stripe Adapter

```typescript
class StripeAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'stripe';

  private stripe: Stripe;

  constructor(apiKey: string) {
    this.stripe = new Stripe(apiKey, { apiVersion: '2025-01-01' });
  }

  async createPaymentIntent(request: CreatePaymentIntentRequest): Promise<PaymentIntent> {
    const intent = await this.stripe.paymentIntents.create({
      amount: Number(request.amount.amount),
      currency: request.currency.toLowerCase(),
      payment_method: request.paymentMethodId,
      metadata: request.metadata,
      confirm: true,
    });

    return {
      id: intent.id,
      status: this.mapStatus(intent.status),
      clientSecret: intent.client_secret ?? undefined,
    };
  }

  async initiateTransfer(request: InitiateTransferRequest): Promise<TransferInitiation> {
    // Stripe uses Payouts for bank transfers
    const payout = await this.stripe.payouts.create({
      amount: Number(request.amount.amount),
      currency: request.currency.toLowerCase(),
      destination: request.destination.externalId,
      metadata: request.metadata,
    });

    return {
      id: payout.id,
      status: this.mapPayoutStatus(payout.status),
      estimatedArrival: payout.arrival_date
        ? new Date(payout.arrival_date * 1000)
        : undefined,
    };
  }

  verifyWebhookSignature(payload: string, signature: string): boolean {
    try {
      this.stripe.webhooks.constructEvent(
        payload,
        signature,
        process.env.STRIPE_WEBHOOK_SECRET!
      );
      return true;
    } catch {
      return false;
    }
  }

  // ... other methods
}
```

#### PIX Adapter (Brazil)

The PIX adapter integrates with Efí (formerly Gerencianet) for Brazilian instant payments:

```typescript
class PixAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'pix';

  // Key features:
  // - QR Code generation for deposits (static and dynamic)
  // - Instant payment notifications via webhook
  // - Real-time settlement (24/7/365)
  // - Low transaction fees
  // - mTLS authentication with certificates
}
```

#### Xendit Adapter (Southeast Asia)

The Xendit adapter supports payments across Indonesia, Philippines, Thailand, Vietnam, and Malaysia:

```typescript
class XenditAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'xendit';

  // Key features:
  // - Multiple payment methods (bank transfer, e-wallets, cards)
  // - Country-specific payment channels
  // - Invoice-based payments
  // - Disbursements to bank accounts
  // - Real-time webhook notifications
}
```

### 6.3 Provider Factory

```typescript
class PaymentProviderFactory {
  private providers: Map<ProviderCode, PaymentProviderGateway> = new Map();

  constructor(config: ProviderConfig) {
    // Register providers based on configuration
    if (config.stripe?.enabled) {
      this.providers.set('stripe', new StripeAdapter(config.stripe.apiKey));
    }
    if (config.pix?.enabled) {
      this.providers.set('pix', new PixAdapter(config.pix));
    }
    if (config.xendit?.enabled) {
      this.providers.set('xendit', new XenditAdapter(config.xendit));
    }
  }

  getProvider(code: ProviderCode): PaymentProviderGateway {
    const provider = this.providers.get(code);
    if (!provider) {
      throw new UnsupportedProviderError(`Provider '${code}' is not configured`);
    }
    return provider;
  }

  getSupportedProviders(): ProviderCode[] {
    return Array.from(this.providers.keys());
  }
}
```

### 6.4 Adding New Providers

To add a new payment provider:

1. **Implement the adapter** in `src/infrastructure/payment-providers/`:
```typescript
class NewProviderAdapter implements PaymentProviderGateway {
  readonly providerCode: ProviderCode = 'new_provider';
  // Implement all interface methods
}
```

2. **Add configuration** in `.env.example` and `src/main/config.ts`

3. **Register in factory** (`PaymentProviderFactory.ts`):
```typescript
if (config.newProvider?.enabled) {
  this.providers.set('new_provider', new NewProviderAdapter(config.newProvider));
}
```

4. **Add webhook controller** if the provider uses webhooks

No changes to core business logic required.

---

## 7. Transaction Processing & Consistency

### 7.1 Double-Entry Bookkeeping

Every value movement creates balanced ledger entries:

```
Transfer: Alice → Bob, 100 CREDITS

Account     | Debit  | Credit | Balance After
------------|--------|--------|---------------
Alice       | 100    |        | 400
Bob         |        | 100    | 600

Sum of Debits = Sum of Credits (balanced)
```

### 7.2 Transaction State Machine

```
                    ┌─────────────┐
                    │   PENDING   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │PROCESSING│  │COMPLETED │  │  FAILED  │
       └────┬─────┘  └──────────┘  └──────────┘
            │                           ▲
            └───────────────────────────┘

       COMPLETED ───► REVERSED (for refunds)
```

### 7.3 Idempotency Implementation

```typescript
class IdempotencyMiddleware {
  constructor(private store: IdempotencyStore) {}

  async handle(req: Request, next: () => Promise<Response>): Promise<Response> {
    const key = req.headers['idempotency-key'];
    if (!key) {
      throw new BadRequestError('Idempotency-Key header required');
    }

    const userId = req.user.id;
    const endpoint = `${req.method}:${req.path}`;
    const requestHash = this.hashBody(req.body);

    // Check for existing key
    const existing = await this.store.get(key, userId, endpoint);

    if (existing) {
      // Key exists - verify request body matches
      if (existing.requestHash !== requestHash) {
        throw new UnprocessableEntityError(
          'Idempotency key already used with different request body'
        );
      }
      // Return cached response
      return new Response(existing.responseBody, { status: existing.responseCode });
    }

    // Process request
    const response = await next();

    // Store result (only for successful responses)
    if (response.status < 500) {
      await this.store.set({
        key,
        userId,
        endpoint,
        requestHash,
        responseCode: response.status,
        responseBody: await response.json(),
        expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000), // 24 hours
      });
    }

    return response;
  }
}
```

### 7.4 Concurrency Control

```typescript
class TransferUseCase {
  async execute(command: TransferCommand): Promise<Transaction> {
    // Acquire locks in consistent order (lower ID first) to prevent deadlock
    const [firstId, secondId] = [command.sourceAccountId, command.destinationAccountId]
      .sort();

    return await this.db.transaction(async (tx) => {
      // Lock accounts in order
      const accounts = await tx.query(`
        SELECT * FROM accounts
        WHERE id IN ($1, $2)
        ORDER BY id
        FOR UPDATE
      `, [firstId, secondId]);

      const source = accounts.find(a => a.id === command.sourceAccountId);
      const destination = accounts.find(a => a.id === command.destinationAccountId);

      // Validate
      if (source.available_balance < command.amount) {
        throw new InsufficientFundsError(source.id, command.amount, source.available_balance);
      }

      // Execute transfer
      // ... (debit source, credit destination, create entries)

      return transaction;
    });
  }
}
```

---

## 8. Async Settlement & Webhooks

### 8.1 Deposit Flow (External → Internal)

```
┌────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐
│ Client │     │   API   │     │  Worker  │     │ Provider │
└───┬────┘     └────┬────┘     └────┬─────┘     └────┬─────┘
    │               │               │                │
    │ POST /deposits│               │                │
    │──────────────►│               │                │
    │               │ Create pending│                │
    │               │ transaction   │                │
    │               │               │                │
    │◄──────────────│               │                │
    │ 202 Accepted  │               │                │
    │ + Location    │               │                │
    │               │               │                │
    │               │  Queue job    │                │
    │               │──────────────►│                │
    │               │               │                │
    │               │               │ Create intent  │
    │               │               │───────────────►│
    │               │               │                │
    │               │               │◄───────────────│
    │               │               │ Intent created │
    │               │               │                │
    │ ... time passes (async) ...   │                │
    │               │               │                │
    │               │  Webhook      │                │
    │               │◄──────────────┼────────────────│
    │               │ payment.succeeded              │
    │               │               │                │
    │               │ Credit account│                │
    │               │ Complete txn  │                │
    │               │               │                │
    │ GET /deposits/{id}            │                │
    │──────────────►│               │                │
    │◄──────────────│               │                │
    │ 200 OK        │               │                │
    │ status:completed              │                │
```

### 8.2 Withdrawal Flow (Internal → External)

```
┌────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐
│ Client │     │   API   │     │  Worker  │     │ Provider │
└───┬────┘     └────┬────┘     └────┬─────┘     └────┬─────┘
    │               │               │                │
    │POST /withdrawals              │                │
    │──────────────►│               │                │
    │               │               │                │
    │               │ Validate balance              │
    │               │ Create hold   │                │
    │               │ (available_balance -= amount) │
    │               │               │                │
    │◄──────────────│               │                │
    │ 202 Accepted  │               │                │
    │               │               │                │
    │               │  Queue job    │                │
    │               │──────────────►│                │
    │               │               │                │
    │               │               │ Initiate payout│
    │               │               │───────────────►│
    │               │               │                │
    │               │               │◄───────────────│
    │               │               │ Payout pending │
    │               │               │                │
    │ ... 1-3 business days ...     │                │
    │               │               │                │
    │               │  Webhook      │                │
    │               │◄──────────────┼────────────────│
    │               │ payout.paid   │                │
    │               │               │                │
    │               │ Debit account │                │
    │               │ (balance -= amount)            │
    │               │ Complete txn  │                │
    │               │               │                │
    │ Notification  │               │                │
    │◄──────────────│               │                │
    │ (optional)    │               │                │
```

### 8.3 Webhook Event Processing

```typescript
class WebhookController {
  @Post('/webhooks/:provider')
  async handleProviderWebhook(
    @Param('provider') providerCode: ProviderCode,
    @Body() rawBody: string,
    @Header('X-Webhook-Signature') signature: string
  ) {
    const provider = this.providerFactory.getProvider(providerCode);

    // 1. Verify signature (HMAC)
    if (!provider.verifyWebhookSignature(rawBody, signature)) {
      throw new UnauthorizedError('Invalid webhook signature');
    }

    // 2. Parse event
    const event = provider.parseWebhookEvent(rawBody);

    // 3. Idempotency check (delivery_id)
    const alreadyProcessed = await this.webhookStore.exists(event.deliveryId);
    if (alreadyProcessed) {
      return { received: true, duplicate: true };
    }

    // 4. Enqueue for async processing
    await this.eventQueue.publish({
      type: event.type,
      providerCode,
      payload: event.data,
      deliveryId: event.deliveryId,
    });

    // 5. Mark as received
    await this.webhookStore.markReceived(event.deliveryId);

    // 6. Return 200 immediately (< 5 seconds)
    return { received: true };
  }
}

// Worker processes events asynchronously
class WebhookEventWorker {
  async process(event: WebhookEvent) {
    switch (event.type) {
      case 'payment_intent.succeeded':
        await this.depositService.completeDeposit(event.payload.metadata.transaction_id);
        break;

      case 'payout.paid':
        await this.withdrawalService.completeWithdrawal(event.payload.metadata.transaction_id);
        break;

      case 'payout.failed':
        await this.withdrawalService.failWithdrawal(
          event.payload.metadata.transaction_id,
          event.payload.failure_message
        );
        break;
    }
  }
}
```

### 8.4 Outbound Webhook Delivery

```typescript
class WebhookDispatcher {
  async dispatch(event: DomainEvent) {
    // Find subscribed webhooks
    const webhooks = await this.webhookRepo.findByEvent(event.type);

    for (const webhook of webhooks) {
      // Create delivery record
      const delivery = await this.deliveryRepo.create({
        webhookId: webhook.id,
        eventType: event.type,
        payload: event,
        status: 'pending',
      });

      // Queue for delivery
      await this.deliveryQueue.publish({
        deliveryId: delivery.id,
        webhookId: webhook.id,
        url: webhook.url,
        secret: webhook.secret,
        payload: event,
      });
    }
  }
}

class WebhookDeliveryWorker {
  async deliver(job: DeliveryJob) {
    const signature = this.sign(job.payload, job.secret);

    try {
      const response = await fetch(job.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Webhook-Signature': `sha256=${signature}`,
          'X-Webhook-Timestamp': Date.now().toString(),
          'X-Delivery-Id': job.deliveryId,
        },
        body: JSON.stringify(job.payload),
        signal: AbortSignal.timeout(10000), // 10s timeout
      });

      if (response.ok) {
        await this.markDelivered(job.deliveryId);
      } else {
        await this.scheduleRetry(job, response.status);
      }
    } catch (error) {
      await this.scheduleRetry(job, error);
    }
  }

  private async scheduleRetry(job: DeliveryJob, error: unknown) {
    const delivery = await this.deliveryRepo.get(job.deliveryId);

    if (delivery.attempts >= 5) {
      // Move to dead letter queue
      await this.markFailed(job.deliveryId, error);
      return;
    }

    // Exponential backoff: 1m, 5m, 25m, 2h, 10h
    const delay = Math.pow(5, delivery.attempts) * 60 * 1000;
    await this.deliveryQueue.publish(job, { delay });
    await this.incrementAttempts(job.deliveryId);
  }
}
```

---

## 9. Security Architecture

### 9.1 Authentication

#### JWT Authentication (Interactive Sessions)
- **JWT tokens** with short expiration (15 minutes)
- **Refresh tokens** for session extension (7 days, rotating)
- Full access to all endpoints (no scope restrictions)

```typescript
// JWT payload
interface TokenPayload {
  sub: string;        // User ID
  scope: string[];    // ['accounts:read', 'transfers:write']
  exp: number;        // Expiration
  iat: number;        // Issued at
  jti: string;        // Token ID (for revocation)
}
```

#### API Token Authentication (Programmatic Access)
- **Long-lived tokens** for automation and integrations
- **Scoped access** - only permitted operations
- **Secure storage** - SHA-256 hash only, never plaintext

```typescript
// Token format: at_<prefix>_<secret>
// Example: at_abc12345_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

// Token structure
interface ApiToken {
  id: string;
  userId: string;
  prefix: string;           // 8 chars (visible for identification)
  tokenHash: Buffer;        // SHA-256 hash of full token
  name: string;             // User-provided name
  scopes: TokenScope[];     // Granted permissions
  expiresAt: Date | null;   // Optional expiration
  revokedAt: Date | null;   // Set when revoked
  lastUsedAt: Date | null;  // Usage tracking
  lastUsedIp: string | null;
}

// Available scopes
type TokenScope =
  | 'accounts:read' | 'accounts:write'
  | 'transactions:read'
  | 'deposits:write' | 'withdrawals:write' | 'transfers:write'
  | 'payment-methods:read' | 'payment-methods:write';
```

#### Dual Authentication Flow
```
┌─────────────────────────────────────────────────────────────────┐
│                    Request Authentication                        │
├─────────────────────────────────────────────────────────────────┤
│  1. Extract token from Authorization: Bearer <token>            │
│  2. Detect token type:                                          │
│     - Starts with 'at_' → API Token authentication              │
│     - Otherwise → JWT authentication                            │
│  3. Validate token (signature/hash, expiration, revocation)     │
│  4. Attach user context to request                              │
│  5. For API tokens: enforce scope restrictions per endpoint     │
└─────────────────────────────────────────────────────────────────┘
```

| Security Aspect | Implementation |
|-----------------|----------------|
| Token Storage | SHA-256 hash only (plaintext never stored) |
| Hash Comparison | `crypto.timingSafeEqual` (timing-safe) |
| Token Limit | Max 25 active tokens per user |
| Rate Limiting | Per-token rate limits (1000/min) |
| Audit Trail | Track last_used_at, last_used_ip per token |
| Revocation | Immediate invalidation with reason |

### 9.2 Authorization

**Object-Level Authorization (BOLA Prevention)**:
```typescript
async function getAccount(accountId: string, userId: string): Promise<Account> {
  const account = await this.accountRepo.findById(accountId);

  if (!account) {
    throw new NotFoundError('Account not found');
  }

  // CRITICAL: Verify ownership
  if (account.userId !== userId) {
    throw new ForbiddenError('Access denied');
  }

  return account;
}
```

**Function-Level Authorization**:
```typescript
@UseGuards(RoleGuard)
@Roles('admin')
@Post('/admin/accounts/:id/freeze')
async freezeAccount(@Param('id') accountId: string) {
  // Only admins can freeze accounts
}
```

### 9.3 Input Validation

```typescript
const TransferSchema = z.object({
  source_account_id: z.string().uuid(),
  destination_account_id: z.string().uuid(),
  amount: z.object({
    amount: z.string().regex(/^\d+$/),  // Positive integer string
    currency: z.literal('CREDIT'),
  }),
  description: z.string().max(500).optional(),
  metadata: z.record(z.string()).optional(),
}).refine(
  data => data.source_account_id !== data.destination_account_id,
  { message: 'Cannot transfer to same account' }
);
```

### 9.4 Rate Limiting

| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Transfers | 100/minute | Per user |
| Deposits | 20/hour | Per user |
| Withdrawals | 10/hour | Per user |
| Read operations | 1000/minute | Per user |
| Webhook delivery | 10/second | Per endpoint |

### 9.5 Sensitive Data Handling

- **Never log**: Full card numbers, bank account numbers, passwords, tokens
- **Mask in responses**: Show only last 4 digits ("•••• 4242")
- **Encrypt at rest**: Payment method tokens, webhook secrets
- **TLS 1.3**: All traffic encrypted in transit
- **PCI DSS**: Card data handled by providers (Stripe, PayPal) — never touches our servers

---

## 10. Scalability & Resilience

### 10.1 Horizontal Scaling

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │  API 1  │          │  API 2  │          │  API N  │
   └────┬────┘          └────┬────┘          └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
                    ┌─────────────────┐
                    │ PostgreSQL      │
                    │ (Primary)       │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             ┌──────────┐      ┌──────────┐
             │ Replica 1│      │ Replica 2│
             └──────────┘      └──────────┘
```

### 10.2 Caching Strategy

| Data | Cache | TTL | Invalidation |
|------|-------|-----|--------------|
| Account balance | Redis | 1 minute | On transaction |
| Payment methods | Redis | 5 minutes | On CRUD |
| Provider configs | In-memory | 1 hour | On deploy |
| Rate limit counters | Redis | Sliding window | Automatic |

### 10.3 Circuit Breaker

```typescript
class PaymentProviderCircuitBreaker {
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  private failures = 0;
  private lastFailure?: Date;

  private readonly threshold = 5;
  private readonly timeout = 30000; // 30 seconds

  async call<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'open') {
      if (Date.now() - this.lastFailure!.getTime() > this.timeout) {
        this.state = 'half-open';
      } else {
        throw new ServiceUnavailableError('Circuit breaker open');
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess() {
    this.failures = 0;
    this.state = 'closed';
  }

  private onFailure() {
    this.failures++;
    this.lastFailure = new Date();

    if (this.failures >= this.threshold) {
      this.state = 'open';
    }
  }
}
```

### 10.4 Retry with Exponential Backoff

```typescript
async function withRetry<T>(
  fn: () => Promise<T>,
  options: { maxAttempts: number; baseDelay: number }
): Promise<T> {
  let lastError: Error;

  for (let attempt = 0; attempt < options.maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      if (!isRetryable(error) || attempt === options.maxAttempts - 1) {
        throw error;
      }

      const delay = options.baseDelay * Math.pow(2, attempt) + Math.random() * 1000;
      await sleep(delay);
    }
  }

  throw lastError!;
}
```

### 10.5 Health Checks

```http
GET /health
```

```json
{
  "status": "healthy",
  "version": "1.2.3",
  "checks": {
    "database": { "status": "healthy", "latency_ms": 5 },
    "redis": { "status": "healthy", "latency_ms": 2 },
    "stripe": { "status": "healthy" },
    "paypal": { "status": "degraded", "message": "High latency" }
  }
}
```

---

## 11. Implementation Roadmap

### Phase 1: Core Ledger (Foundation) - COMPLETE
- [x] Database schema setup
- [x] Account management (CRUD)
- [x] P2P transfers with double-entry
- [x] Idempotency implementation
- [x] Basic API endpoints

### Phase 2: External Integration - COMPLETE
- [x] Payment provider port interface
- [x] Stripe adapter (deposits)
- [x] Async job processing
- [x] Inbound webhook handling

### Phase 3: Withdrawals & Payouts - COMPLETE
- [x] Withdrawal flow with holds
- [x] Stripe payouts adapter
- [x] Settlement reconciliation
- [x] Failure handling & reversals

### Phase 4: Multi-Provider - COMPLETE
- [x] PIX adapter (Brazil - via Efí/Gerencianet)
- [x] Xendit adapter (Southeast Asia)
- [x] Provider factory pattern
- [x] Payment method management

### Phase 5: Production Hardening - COMPLETE
- [x] Rate limiting (Redis-backed with in-memory fallback)
- [x] Error handling (RFC 9457 Problem Details)
- [x] Security middleware (Helmet, CORS, JWT)
- [x] Audit logging (Pino logger)

### Phase 6: Scale & Optimize - IN PROGRESS
- [x] Caching layer (Redis stores)
- [ ] Read replicas
- [ ] Performance optimization
- [ ] Load testing

---

## Appendix A: API Quick Reference

| Resource | Create | Read | Update | Delete | List |
|----------|--------|------|--------|--------|------|
| Accounts | `POST /accounts` | `GET /accounts/{id}` | - | - | `GET /accounts` |
| Transfers | `POST /transfers` | `GET /transfers/{id}` | - | - | via `/transactions` |
| Deposits | `POST /deposits` | `GET /deposits/{id}` | - | - | via `/transactions` |
| Withdrawals | `POST /withdrawals` | `GET /withdrawals/{id}` | `POST /{id}/cancel` | - | via `/transactions` |
| Payment Methods | `POST /payment-methods` | `GET /payment-methods/{id}` | - | `DELETE /{id}` | `GET /payment-methods` |
| Refunds | `POST /refunds` | `GET /refunds/{id}` | - | - | via `/transactions` |
| Transactions | - | `GET /transactions/{id}` | - | - | `GET /transactions` |
| Webhooks | `POST /webhooks` | `GET /webhooks/{id}` | `PATCH /{id}` | `DELETE /{id}` | `GET /webhooks` |

---

## Appendix B: Status Code Summary

| Code | Usage in This API |
|------|-------------------|
| 200 | Successful GET, completed sync operations |
| 201 | Resource created (transfers, accounts) |
| 202 | Async operation accepted (deposits, withdrawals) |
| 204 | Successful DELETE |
| 400 | Malformed request syntax |
| 401 | Missing/invalid authentication |
| 403 | Authenticated but not authorized (BOLA) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, version mismatch) |
| 422 | Validation error (insufficient funds, invalid state) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service unavailable (circuit breaker open) |

---

## Appendix C: Event Types

| Event | Trigger |
|-------|---------|
| `account.created` | New account created |
| `transfer.completed` | P2P transfer succeeded |
| `deposit.pending` | Deposit initiated |
| `deposit.completed` | Deposit funds credited |
| `deposit.failed` | Deposit failed |
| `withdrawal.pending` | Withdrawal initiated, funds held |
| `withdrawal.completed` | Withdrawal settled |
| `withdrawal.failed` | Withdrawal failed, funds released |
| `refund.completed` | Refund processed |
| `payment_method.verified` | Payment method verified |
