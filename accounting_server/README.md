# Unified Global Ledger & Payment Abstraction Layer

A centralized financial orchestration server that acts as an abstraction layer between disparate global payment ecosystems.

## Features

- **Centralized Ledger Engine**: Double-entry bookkeeping with ACID transactions
- **P2P Transfers**: Instant internal credit transfers between accounts
- **Multi-Provider Integration**: Stripe, PIX (Brazil), and Xendit (Southeast Asia) adapters
- **Async Settlement**: Deposit and withdrawal with webhook-based status updates
- **Idempotent Operations**: Safe retry handling for all mutations
- **Rate Limiting**: Configurable per-endpoint rate limits
- **RFC 9457 Errors**: Standard Problem Details error format
- **API Tokens**: Scoped, long-lived tokens for programmatic access

## Quick Start

### Prerequisites

- Node.js 20+
- PostgreSQL 15+
- Redis (optional, for production)

### Installation

```bash
# Install dependencies
npm install

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
```

### Environment Variables

```bash
# Server
PORT=3000
NODE_ENV=development

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ledger
DATABASE_POOL_SIZE=10

# JWT Authentication
JWT_SECRET=your-secret-key-minimum-32-characters
JWT_ISSUER=ledger-api
JWT_AUDIENCE=ledger-api

# Stripe (optional)
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# PIX - Brazilian Instant Payment (optional)
PIX_ENABLED=false
PIX_PROVIDER=efi
PIX_CLIENT_ID=...
PIX_CLIENT_SECRET=...

# Xendit - Southeast Asia (optional)
XENDIT_ENABLED=false
XENDIT_API_KEY=xnd_development_...
```

### Database Setup

```bash
# Run migrations
npm run migrate:up

# Or manually
psql $DATABASE_URL < migrations/001_initial_schema.sql
```

### Running

```bash
# Development
npm run dev

# Production
npm run build
npm start
```

## API Overview

### Authentication

All API endpoints require authentication via Bearer token. Two methods are supported:

**JWT Token** (interactive sessions):
```bash
Authorization: Bearer <jwt_token>
```

**API Token** (programmatic access):
```bash
Authorization: Bearer at_abc12345_<secret>
```

API tokens provide scoped access for automation and integrations. Create tokens via the `/v1/api-tokens` endpoint using JWT authentication.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/accounts` | Create account |
| `GET` | `/v1/accounts` | List accounts |
| `GET` | `/v1/accounts/:id` | Get account |
| `GET` | `/v1/accounts/:id/balance` | Get balance |
| `POST` | `/v1/transfers` | Execute P2P transfer |
| `GET` | `/v1/transfers/:id` | Get transfer |
| `POST` | `/v1/deposits` | Initiate deposit |
| `GET` | `/v1/deposits/:id` | Get deposit status |
| `POST` | `/v1/withdrawals` | Initiate withdrawal |
| `GET` | `/v1/withdrawals/:id` | Get withdrawal status |
| `POST` | `/v1/api-tokens` | Create API token (JWT only) |
| `GET` | `/v1/api-tokens` | List user's API tokens |
| `GET` | `/v1/api-tokens/:id` | Get token details |
| `PATCH` | `/v1/api-tokens/:id` | Update token name |
| `DELETE` | `/v1/api-tokens/:id` | Revoke token |

### Idempotency

All mutating operations require an `Idempotency-Key` header:

```bash
curl -X POST https://api.example.com/v1/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"source_account_id": "...", "destination_account_id": "...", "amount": {"amount": "1000", "currency": "CREDIT"}}'
```

### Example: Create Account

```bash
curl -X POST http://localhost:3000/v1/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"type": "user", "metadata": {"name": "My Wallet"}}'
```

### Example: Transfer

```bash
curl -X POST http://localhost:3000/v1/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "source_account_id": "acc_123",
    "destination_account_id": "acc_456",
    "amount": {"amount": "1000", "currency": "CREDIT"},
    "description": "Payment for services"
  }'
```

### Example: Create API Token

```bash
# Create a token with specific scopes (requires JWT auth)
curl -X POST http://localhost:3000/v1/api-tokens \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI Pipeline",
    "scopes": ["accounts:read", "transactions:read"],
    "expires_in_days": 90
  }'

# Response includes the full token (shown only once!)
# {
#   "id": "550e8400-e29b-41d4-a716-446655440000",
#   "token": "at_abc12345_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
#   "name": "CI Pipeline",
#   "scopes": ["accounts:read", "transactions:read"],
#   "expires_at": "2026-05-08T10:00:00Z",
#   "warning": "Store this token securely. It will not be shown again."
# }
```

### Example: Use API Token

```bash
# Use API token for programmatic access
curl http://localhost:3000/v1/accounts \
  -H "Authorization: Bearer at_abc12345_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

## Architecture

```
src/
├── domain/           # Core business logic (entities, value objects)
├── application/      # Use cases and port interfaces
├── infrastructure/   # External adapters (DB, HTTP, payment providers)
└── main/            # Composition root and server
```

### Key Design Patterns

- **Hexagonal Architecture**: Core domain isolated from external concerns
- **Repository Pattern**: Abstract data access
- **Adapter Pattern**: Pluggable payment providers
- **Double-Entry Ledger**: Every transaction creates balanced entries

## Documentation

- [Architecture Design](./ARCHITECTURE.md) - Full system design document
- [API Endpoints](./API_ENDPOINTS.md) - Complete endpoint reference
- [Workflows](./WORKFLOWS.md) - Sequence diagrams for main flows
- [OpenAPI Spec](./openapi.yaml) - OpenAPI 3.1 specification

## Development

```bash
# Run tests
npm test

# Type check
npm run typecheck

# Lint
npm run lint

# Format
npm run format
```

## Project Structure

```
.
├── src/
│   ├── domain/
│   │   ├── entities/          # Account, Transaction, LedgerEntry
│   │   ├── value-objects/     # Money, Identifiers
│   │   └── errors/            # Domain errors
│   ├── application/
│   │   ├── ports/
│   │   │   ├── input/         # Service interfaces
│   │   │   └── output/        # Repository interfaces
│   │   └── use-cases/         # Business operations
│   ├── infrastructure/
│   │   ├── persistence/       # PostgreSQL repositories
│   │   ├── payment-providers/ # Stripe, PIX, Xendit adapters
│   │   ├── cache/             # Redis stores (idempotency, rate limiting)
│   │   └── http/
│   │       ├── controllers/   # Route handlers
│   │       └── middleware/    # Auth, idempotency, rate limiting
│   └── main/
│       ├── config.ts          # Configuration
│       ├── container.ts       # Dependency injection
│       └── server.ts          # Entry point
├── migrations/                # Database migrations
├── openapi.yaml              # API specification
├── ARCHITECTURE.md           # Design document
└── package.json
```

## License

Proprietary
