# API Endpoints Reference

Complete reference for all API endpoints in the Unified Global Ledger.

---

## Base URL

```
Production:  https://api.ledger.example.com/v1
Staging:     https://api.staging.ledger.example.com/v1
Development: http://localhost:3000/v1
```

## Authentication

All `/v1/*` endpoints require JWT Bearer authentication:

```http
Authorization: Bearer <jwt_token>
```

Webhook endpoints (`/webhooks/*`) do not require JWT authentication but verify provider-specific signatures.

---

## Quick Reference

| Category | Method | Endpoint | Description |
|----------|--------|----------|-------------|
| **Health** | `GET` | `/health` | Health check (no auth) |
| **Accounts** | `POST` | `/v1/accounts` | Create account |
| | `GET` | `/v1/accounts` | List accounts |
| | `GET` | `/v1/accounts/:id` | Get account |
| | `GET` | `/v1/accounts/:id/balance` | Get balance |
| | `GET` | `/v1/accounts/:id/transactions` | List account transactions |
| **Transfers** | `POST` | `/v1/transfers` | Create P2P transfer |
| | `GET` | `/v1/transfers/:id` | Get transfer |
| | `POST` | `/v1/transfers/confirm` | Confirm pending transfer |
| | `POST` | `/v1/transfers/:id/cancel` | Cancel pending transfer |
| **Deposits** | `POST` | `/v1/deposits` | Initiate deposit |
| | `GET` | `/v1/deposits/:id` | Get deposit status |
| **Withdrawals** | `POST` | `/v1/withdrawals` | Initiate withdrawal |
| | `GET` | `/v1/withdrawals/:id` | Get withdrawal status |
| | `POST` | `/v1/withdrawals/:id/cancel` | Cancel pending withdrawal |
| **Payment Methods** | `POST` | `/v1/payment-methods` | Link payment method |
| | `GET` | `/v1/payment-methods` | List payment methods |
| | `GET` | `/v1/payment-methods/:id` | Get payment method |
| | `DELETE` | `/v1/payment-methods/:id` | Unlink payment method |
| | `POST` | `/v1/payment-methods/:id/verify` | Verify payment method |
| **PIX (Brazil)** | `POST` | `/v1/pix/keys/lookup` | Look up PIX key |
| | `POST` | `/v1/pix/qr-codes/static` | Generate static QR |
| | `POST` | `/v1/pix/qr-codes/dynamic` | Generate dynamic QR |
| | `POST` | `/v1/pix/charges` | Create PIX charge |
| | `GET` | `/v1/pix/charges/:txid` | Get charge status |
| | `POST` | `/v1/pix/validate-key` | Validate PIX key format |
| **Xendit (SE Asia)** | `POST` | `/v1/xendit/invoices` | Create invoice |
| | `GET` | `/v1/xendit/invoices/:id` | Get invoice |
| | `POST` | `/v1/xendit/invoices/:id/expire` | Expire invoice |
| | `POST` | `/v1/xendit/virtual-accounts` | Create virtual account |
| | `GET` | `/v1/xendit/virtual-accounts/:id` | Get virtual account |
| | `GET` | `/v1/xendit/channels` | List payment channels |
| | `GET` | `/v1/xendit/config` | Get Xendit config |
| **Webhooks** | `POST` | `/webhooks/stripe` | Stripe webhook |
| | `POST` | `/webhooks/pix` | PIX webhook |
| | `POST` | `/webhooks/xendit` | Xendit webhook |
| | `POST` | `/webhooks/:provider` | Generic provider webhook |

---

## Health Check

### `GET /health`

No authentication required. Returns server health status.

**Response: 200 OK**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": { "status": "healthy" }
  }
}
```

**Response: 503 Service Unavailable**
```json
{
  "status": "unhealthy",
  "checks": {
    "database": { "status": "unhealthy", "message": "Connection refused" }
  }
}
```

---

## Accounts

### `POST /v1/accounts`

Create a new account.

**Headers**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token |
| `Idempotency-Key` | Yes | UUID for idempotent request |

**Request Body**
```json
{
  "type": "user",
  "metadata": {
    "display_name": "Main Wallet"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Account type: `user`, `system`, `escrow` |
| `metadata` | object | No | Custom metadata |

**Response: 201 Created**
```json
{
  "id": "acc_abc123",
  "type": "user",
  "status": "active",
  "balance": { "amount": "0", "currency": "CREDIT" },
  "available_balance": { "amount": "0", "currency": "CREDIT" },
  "created_at": "2026-02-07T10:00:00Z",
  "metadata": { "display_name": "Main Wallet" }
}
```

---

### `GET /v1/accounts`

List authenticated user's accounts.

**Query Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status: `active`, `frozen`, `closed` |
| `limit` | integer | Max results (default: 20, max: 100) |
| `cursor` | string | Pagination cursor |

**Response: 200 OK**
```json
{
  "data": [
    {
      "id": "acc_abc123",
      "type": "user",
      "status": "active",
      "balance": { "amount": "10000", "currency": "CREDIT" },
      "available_balance": { "amount": "9500", "currency": "CREDIT" },
      "created_at": "2026-02-07T10:00:00Z"
    }
  ],
  "pagination": {
    "has_more": false,
    "next_cursor": null
  }
}
```

---

### `GET /v1/accounts/:id`

Get account details.

**Response: 200 OK**
```json
{
  "id": "acc_abc123",
  "type": "user",
  "status": "active",
  "balance": { "amount": "10000", "currency": "CREDIT" },
  "available_balance": { "amount": "9500", "currency": "CREDIT" },
  "created_at": "2026-02-07T10:00:00Z",
  "updated_at": "2026-02-07T11:30:00Z",
  "metadata": { "display_name": "Main Wallet" }
}
```

---

### `GET /v1/accounts/:id/balance`

Get account balance with pending amounts breakdown.

**Response: 200 OK**
```json
{
  "account_id": "acc_abc123",
  "balance": { "amount": "10000", "currency": "CREDIT" },
  "available_balance": { "amount": "9500", "currency": "CREDIT" },
  "pending_deposits": { "amount": "0", "currency": "CREDIT" },
  "pending_withdrawals": { "amount": "500", "currency": "CREDIT" },
  "as_of": "2026-02-07T11:30:00Z"
}
```

---

### `GET /v1/accounts/:id/transactions`

List transactions for an account.

**Query Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `type` | string | Filter: `transfer`, `deposit`, `withdrawal`, `refund` |
| `status` | string | Filter: `pending`, `completed`, `failed`, `reversed` |
| `created_after` | ISO 8601 | Filter by date |
| `created_before` | ISO 8601 | Filter by date |
| `limit` | integer | Max results |
| `cursor` | string | Pagination cursor |

---

## Transfers

### `POST /v1/transfers`

Create a P2P transfer between accounts.

**Headers**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token |
| `Idempotency-Key` | Yes | UUID for idempotent request |

**Request Body**
```json
{
  "source_account_id": "acc_abc123",
  "destination_account_id": "acc_def456",
  "amount": { "amount": "1000", "currency": "CREDIT" },
  "description": "Payment for services",
  "metadata": { "invoice_id": "inv_789" }
}
```

**Response: 202 Accepted** (pending confirmation)
```json
{
  "id": "txn_xyz789",
  "type": "transfer",
  "status": "pending",
  "source_account_id": "acc_abc123",
  "destination_account_id": "acc_def456",
  "amount": { "amount": "1000", "currency": "CREDIT" },
  "confirmation_token": "txn_confirm_abc123xyz456",
  "created_at": "2026-02-07T10:35:00Z"
}
```

**Response: 201 Created** (instant transfers if configured)
```json
{
  "id": "txn_xyz789",
  "type": "transfer",
  "status": "completed",
  "source_account_id": "acc_abc123",
  "destination_account_id": "acc_def456",
  "amount": { "amount": "1000", "currency": "CREDIT" },
  "fee": { "amount": "0", "currency": "CREDIT" },
  "completed_at": "2026-02-07T10:35:00Z"
}
```

---

### `POST /v1/transfers/confirm`

Confirm a pending transfer (called by recipient).

**Request Body**
```json
{
  "confirmation_token": "txn_confirm_abc123xyz456"
}
```

**Response: 200 OK**
```json
{
  "id": "txn_xyz789",
  "type": "transfer",
  "status": "completed",
  "completed_at": "2026-02-07T10:36:00Z"
}
```

---

### `POST /v1/transfers/:id/cancel`

Cancel a pending transfer (called by sender).

**Response: 200 OK**
```json
{
  "id": "txn_xyz789",
  "type": "transfer",
  "status": "cancelled",
  "cancelled_at": "2026-02-07T10:36:00Z"
}
```

---

## Deposits

### `POST /v1/deposits`

Initiate a deposit from an external payment source.

**Request Body**
```json
{
  "account_id": "acc_abc123",
  "amount": { "amount": "5000", "currency": "USD" },
  "payment_method_id": "pm_stripe_xyz",
  "metadata": { "source": "mobile_app" }
}
```

**Response: 202 Accepted**
```json
{
  "id": "dep_qrs789",
  "status": "pending",
  "account_id": "acc_abc123",
  "amount": { "amount": "5000", "currency": "USD" },
  "credits_amount": { "amount": "5000", "currency": "CREDIT" },
  "provider_code": "stripe",
  "provider_status": "processing",
  "created_at": "2026-02-07T10:40:00Z",
  "estimated_completion": "2026-02-07T10:45:00Z"
}
```

---

### `GET /v1/deposits/:id`

Get deposit status.

**Response: 200 OK** (completed)
```json
{
  "id": "dep_qrs789",
  "status": "completed",
  "account_id": "acc_abc123",
  "amount": { "amount": "5000", "currency": "USD" },
  "credits_amount": { "amount": "5000", "currency": "CREDIT" },
  "fee": { "amount": "50", "currency": "CREDIT" },
  "net_credits": { "amount": "4950", "currency": "CREDIT" },
  "provider_code": "stripe",
  "external_reference": "pi_abc123xyz",
  "created_at": "2026-02-07T10:40:00Z",
  "completed_at": "2026-02-07T10:42:30Z"
}
```

---

## Withdrawals

### `POST /v1/withdrawals`

Initiate a withdrawal to an external destination.

**Request Body**
```json
{
  "account_id": "acc_abc123",
  "amount": { "amount": "2000", "currency": "CREDIT" },
  "payment_method_id": "pm_bank_456",
  "description": "Withdrawal to bank account"
}
```

**Response: 202 Accepted**
```json
{
  "id": "wth_lmn456",
  "status": "pending",
  "account_id": "acc_abc123",
  "amount": { "amount": "2000", "currency": "CREDIT" },
  "destination_amount": { "amount": "1980", "currency": "USD" },
  "fee": { "amount": "20", "currency": "CREDIT" },
  "provider_code": "stripe",
  "payment_method_id": "pm_bank_456",
  "created_at": "2026-02-07T11:00:00Z",
  "estimated_completion": "2026-02-09T11:00:00Z"
}
```

---

### `POST /v1/withdrawals/:id/cancel`

Cancel a pending withdrawal.

**Response: 200 OK**
```json
{
  "id": "wth_lmn456",
  "status": "cancelled",
  "cancelled_at": "2026-02-07T11:05:00Z"
}
```

---

## Payment Methods

### `POST /v1/payment-methods`

Link a new payment method.

**Request Body**
```json
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
  "created_at": "2026-02-07T11:30:00Z"
}
```

---

### `DELETE /v1/payment-methods/:id`

Unlink a payment method.

**Response: 204 No Content**

---

### `POST /v1/payment-methods/:id/verify`

Verify a payment method (e.g., micro-deposit verification).

**Request Body**
```json
{
  "amounts": [32, 45]
}
```

**Response: 200 OK**
```json
{
  "id": "pm_bank_456",
  "status": "verified"
}
```

---

## PIX (Brazil)

Brazilian instant payment endpoints. Requires PIX provider configuration.

### `POST /v1/pix/keys/lookup`

Look up a PIX key in the DICT (Directory of Transaction Identifiers).

**Request Body**
```json
{
  "key_type": "cpf",
  "key_value": "12345678901"
}
```

| Key Type | Format |
|----------|--------|
| `cpf` | 11 digits |
| `cnpj` | 14 digits |
| `email` | Valid email |
| `phone` | +55XXXXXXXXXXX |
| `evp` | UUID (random key) |

**Response: 200 OK**
```json
{
  "key": { "type": "cpf", "value": "12345678901" },
  "holder": {
    "name": "João Silva",
    "document_type": "CPF",
    "document": "***456789**"
  },
  "bank": { "ispb": "00000000", "name": "Banco do Brasil" },
  "account": { "agency": "0001", "number": "12345-6", "type": "checking" },
  "created_at": "2025-01-15T10:00:00Z"
}
```

---

### `POST /v1/pix/qr-codes/static`

Generate a static QR code (reusable, optional amount).

**Request Body**
```json
{
  "amount": 10000,
  "description": "Donation"
}
```

**Response: 201 Created**
```json
{
  "id": "qr_static_123",
  "type": "static",
  "payload": "00020126580014br.gov.bcb.pix...",
  "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "qr_code_url": "https://api.efi.com.br/qrcode/...",
  "pix_key": "your-pix-key@email.com",
  "merchant_name": "YOUR COMPANY",
  "merchant_city": "SAO PAULO",
  "amount": 10000,
  "created_at": "2026-02-07T12:00:00Z"
}
```

---

### `POST /v1/pix/qr-codes/dynamic`

Generate a dynamic QR code (single-use, with expiration).

**Request Body**
```json
{
  "amount": 15000,
  "expires_in_seconds": 3600,
  "description": "Order #12345",
  "payer_document": "12345678901",
  "payer_name": "João Silva"
}
```

**Response: 201 Created**
```json
{
  "id": "qr_dynamic_456",
  "type": "dynamic",
  "txid": "abc123def456ghi789",
  "payload": "00020126580014br.gov.bcb.pix...",
  "qr_code_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "amount": 15000,
  "expires_at": "2026-02-07T13:00:00Z",
  "created_at": "2026-02-07T12:00:00Z"
}
```

---

### `POST /v1/pix/charges`

Create a PIX charge (cobrança).

**Request Body**
```json
{
  "amount": 25000,
  "expires_in_seconds": 86400,
  "description": "Invoice #INV-001",
  "payer_document": "12345678901",
  "payer_name": "Maria Santos"
}
```

**Response: 201 Created**
```json
{
  "id": "charge_789",
  "txid": "xyz789abc123",
  "status": "ATIVA",
  "pix_key": "your-pix-key@email.com",
  "amount": 25000,
  "qr_code": {
    "payload": "00020126580014br.gov.bcb.pix...",
    "base64": "iVBORw0KGgoAAAANSUhEUgAA..."
  },
  "expires_at": "2026-02-08T12:00:00Z",
  "created_at": "2026-02-07T12:00:00Z"
}
```

---

### `GET /v1/pix/charges/:txid`

Get PIX charge status.

**Response: 200 OK**
```json
{
  "id": "charge_789",
  "txid": "xyz789abc123",
  "status": "CONCLUIDA",
  "amount": 25000,
  "end_to_end_id": "E00000000202602071234...",
  "paid_at": "2026-02-07T12:15:00Z",
  "created_at": "2026-02-07T12:00:00Z"
}
```

---

## Xendit (Southeast Asia)

Payment endpoints for Indonesia, Philippines, Thailand, Vietnam, and Malaysia.

### `POST /v1/xendit/invoices`

Create a payment invoice (payment link).

**Request Body**
```json
{
  "external_id": "order_12345",
  "amount": 150000,
  "currency": "IDR",
  "payer_email": "customer@example.com",
  "description": "Order #12345",
  "duration_seconds": 86400,
  "payment_methods": ["BCA", "OVO", "DANA"]
}
```

**Response: 201 Created**
```json
{
  "id": "inv_abc123",
  "external_id": "order_12345",
  "status": "PENDING",
  "amount": 150000,
  "currency": "IDR",
  "invoice_url": "https://checkout.xendit.co/web/inv_abc123",
  "available_banks": [
    { "bank_code": "BCA", "collection_type": "POOL", "account_holder_name": "PT COMPANY" }
  ],
  "available_ewallets": [
    { "ewallet_type": "OVO" },
    { "ewallet_type": "DANA" }
  ],
  "created": "2026-02-07T12:00:00Z"
}
```

---

### `POST /v1/xendit/invoices/:id/expire`

Expire an invoice.

**Response: 200 OK**
```json
{
  "id": "inv_abc123",
  "external_id": "order_12345",
  "status": "EXPIRED",
  "message": "Invoice expired successfully"
}
```

---

### `POST /v1/xendit/virtual-accounts`

Create a virtual account for bank transfer collection.

**Request Body**
```json
{
  "external_id": "va_order_123",
  "bank_code": "BCA",
  "name": "John Doe",
  "expected_amount": 150000,
  "is_closed": true,
  "is_single_use": true
}
```

**Response: 201 Created**
```json
{
  "id": "va_abc123",
  "external_id": "va_order_123",
  "bank_code": "BCA",
  "merchant_code": "12345",
  "name": "John Doe",
  "account_number": "1234512345678901",
  "is_closed": true,
  "is_single_use": true,
  "expected_amount": 150000,
  "status": "PENDING",
  "currency": "IDR",
  "country": "ID"
}
```

---

### `GET /v1/xendit/channels`

List available payment channels.

**Query Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| `country` | string | Filter by country: `ID`, `PH`, `VN`, `TH`, `MY` |

**Response: 200 OK**
```json
{
  "country": "ID",
  "currency": "IDR",
  "channels": {
    "cards": ["CARDS"],
    "virtual_accounts": ["BCA", "BNI", "BRI", "MANDIRI", "PERMATA"],
    "ewallets": ["OVO", "DANA", "LINKAJA", "SHOPEEPAY", "GOPAY"],
    "qr_codes": ["QRIS"],
    "retail_outlets": ["ALFAMART", "INDOMARET"]
  }
}
```

---

### `GET /v1/xendit/config`

Get current Xendit configuration.

**Response: 200 OK**
```json
{
  "default_country": "ID",
  "default_currency": "IDR",
  "success_redirect_url": "https://yoursite.com/payment/success",
  "failure_redirect_url": "https://yoursite.com/payment/failure",
  "supported_countries": ["ID", "PH", "VN", "TH", "MY"],
  "supported_currencies": ["IDR", "PHP", "VND", "THB", "MYR", "USD"]
}
```

---

## Webhooks

Webhook endpoints for payment provider callbacks. No JWT authentication required; providers use signature verification.

### `POST /webhooks/stripe`

Stripe webhook endpoint.

**Headers**
| Header | Description |
|--------|-------------|
| `Stripe-Signature` | HMAC signature for verification |

---

### `POST /webhooks/pix`

PIX (Efí/Gerencianet) webhook endpoint.

**Headers**
| Header | Description |
|--------|-------------|
| `X-Webhook-Signature` | HMAC signature |
| `X-Webhook-Timestamp` | Request timestamp |

---

### `POST /webhooks/xendit`

Xendit webhook endpoint.

**Headers**
| Header | Description |
|--------|-------------|
| `X-Callback-Token` | Xendit webhook verification token |

---

## Error Responses

All errors follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) Problem Details format.

```json
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

### Common Error Types

| Type | Status | Description |
|------|--------|-------------|
| `validation-error` | 422 | Request validation failed |
| `insufficient-funds` | 422 | Account balance too low |
| `account-not-found` | 404 | Account does not exist |
| `unauthorized` | 401 | Missing or invalid authentication |
| `forbidden` | 403 | Not authorized for this resource |
| `rate-limited` | 429 | Too many requests |
| `provider-unavailable` | 503 | Payment provider not configured |

---

## Rate Limits

| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Standard (accounts, payment methods) | 1000/min | Per user |
| Transfers | 100/min | Per user |
| Deposits | 20/hour | Per user |
| Withdrawals | 10/hour | Per user |
| Webhooks | 10/sec | Per endpoint |

**Rate limit headers:**
```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1707220800
```

---

## Idempotency

All mutating endpoints (`POST`, `DELETE`) require an `Idempotency-Key` header:

```http
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
```

- Keys must be UUIDs
- Keys expire after 24 hours
- Replaying with same key returns cached response
- Replaying with same key but different body returns 422 error
