# SyftHub API Reference

> Complete documentation of all REST API endpoints in SyftHub.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Error Handling](#error-handling)
- [Endpoints](#endpoints)
  - [Authentication API](#authentication-api)
  - [Users API](#users-api)
  - [Endpoints API](#endpoints-api-1)
  - [Organizations API](#organizations-api)
  - [Identity Provider API](#identity-provider-api)
  - [Accounting API](#accounting-api)
  - [Observability API](#observability-api)
  - [Content Delivery API](#content-delivery-api)
- [Aggregator API](#aggregator-api)

---

## Overview

### Base URL

```
Production: https://api.syfthub.com
Development: http://localhost:8080
```

### API Versioning

All API endpoints are prefixed with `/api/v1/`. Future versions will use `/api/v2/`, etc.

### Content Type

All requests and responses use `application/json` unless otherwise specified.

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Conditional | `Bearer <token>` for protected endpoints |
| `Content-Type` | Yes (POST/PUT/PATCH) | `application/json` |
| `X-Correlation-ID` | No | Request tracing ID (auto-generated if not provided) |
| `Accept` | No | `application/json` or `text/html` for content delivery |

---

## Authentication

### Bearer Token Authentication

Protected endpoints require a valid JWT access token in the `Authorization` header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Types

| Token Type | Algorithm | Expiration | Use Case |
|------------|-----------|------------|----------|
| Access Token | HS256 | 30 minutes | API authentication |
| Refresh Token | HS256 | 7 days | Obtaining new access tokens |
| Satellite Token | RS256 | 60 seconds | Federated service authentication |

### Authentication States

| State | Description | Behavior |
|-------|-------------|----------|
| `Required` | Must provide valid token | 401 if missing/invalid |
| `Optional` | Token enhances response | Public data if no token |
| `None` | No authentication needed | Always accessible |

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message or error object"
}
```

### Validation Error Response (422)

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Error description",
      "type": "value_error"
    }
  ]
}
```

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET, PUT, PATCH |
| 201 | Created | Successful POST creating a resource |
| 204 | No Content | Successful DELETE or action with no response body |
| 400 | Bad Request | Invalid request format or parameters |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate resource (e.g., username taken) |
| 422 | Unprocessable Entity | Validation errors |
| 500 | Internal Server Error | Unexpected server error |
| 502 | Bad Gateway | Upstream service connection failed |
| 503 | Service Unavailable | Service not configured or unavailable |
| 504 | Gateway Timeout | Upstream service timeout |

### Domain-Specific Error Codes

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| `USER_ALREADY_EXISTS` | 409 | Username or email taken |
| `ACCOUNTING_ACCOUNT_EXISTS` | 424 | Email exists in accounting service |
| `INVALID_ACCOUNTING_PASSWORD` | 401 | Wrong accounting password |
| `ACCOUNTING_SERVICE_UNAVAILABLE` | 503 | Accounting service down |
| `AUDIENCE_NOT_FOUND` | 400 | Satellite token audience not found |
| `AUDIENCE_INACTIVE` | 400 | Satellite token audience inactive |
| `KEY_NOT_CONFIGURED` | 503 | RSA keys not configured for IdP |

---

## Endpoints

## Authentication API

### POST /api/v1/auth/register

Register a new user account.

**Authentication:** None

**Request Body:**

```json
{
  "username": "johndoe",
  "email": "john@example.com",
  "password": "secureP@ss123",
  "full_name": "John Doe",
  "accounting_service_url": "https://accounting.example.com",
  "accounting_password": "optional_existing_password"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `username` | string | Yes | 3-50 chars, alphanumeric + _ - |
| `email` | string | Yes | Valid email format |
| `password` | string | Yes | Min 8 chars, 1 digit, 1 letter |
| `full_name` | string | Yes | 1-100 chars |
| `accounting_service_url` | string | No | Valid URL |
| `accounting_password` | string | No | For linking existing account |

**Response (201 Created):**

```json
{
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "avatar_url": null,
    "role": "user",
    "is_active": true,
    "created_at": "2024-01-20T10:00:00Z",
    "updated_at": "2024-01-20T10:00:00Z"
  },
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 409 | Username or email already exists |
| 424 | Email exists in accounting (requires `accounting_password`) |
| 401 | Invalid accounting password |
| 503 | Accounting service unavailable |

---

### POST /api/v1/auth/login

Authenticate and obtain tokens.

**Authentication:** None

**Request Body (form-urlencoded):**

```
username=johndoe&password=secureP@ss123
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Username or email |
| `password` | string | Yes | Account password |

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

### POST /api/v1/auth/refresh

Refresh access token using refresh token.

**Authentication:** None

**Request Body:**

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response (200 OK):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

### POST /api/v1/auth/logout

Logout and blacklist current access token.

**Authentication:** Required

**Response (204 No Content)**

---

### GET /api/v1/auth/me

Get current authenticated user's profile.

**Authentication:** Required

**Response (200 OK):**

```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "avatar_url": "https://example.com/avatar.jpg",
  "role": "user",
  "is_active": true,
  "domain": "johndoe.syfthub.io",
  "accounting_service_url": "https://accounting.example.com",
  "created_at": "2024-01-20T10:00:00Z",
  "updated_at": "2024-01-20T10:00:00Z"
}
```

---

### PUT /api/v1/auth/me/password

Change current user's password.

**Authentication:** Required

**Request Body:**

```json
{
  "current_password": "oldP@ss123",
  "new_password": "newSecureP@ss456"
}
```

**Response (204 No Content)**

---

## Users API

### GET /api/v1/users

List all users (admin only).

**Authentication:** Required (admin)

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "role": "user",
    "is_active": true,
    "created_at": "2024-01-20T10:00:00Z"
  }
]
```

---

### GET /api/v1/users/check-username/{username}

Check if username is available (public).

**Authentication:** None

**Response (200 OK):**

```json
{
  "available": true,
  "username": "newuser"
}
```

---

### GET /api/v1/users/check-email/{email}

Check if email is available (public).

**Authentication:** None

**Response (200 OK):**

```json
{
  "available": false,
  "email": "existing@example.com"
}
```

---

### GET /api/v1/users/{user_id}

Get user by ID (admin or self only).

**Authentication:** Required

**Response (200 OK):** User object

---

### PUT /api/v1/users/me

Update current user's profile.

**Authentication:** Required

**Request Body:**

```json
{
  "full_name": "John D. Doe",
  "avatar_url": "https://example.com/new-avatar.jpg",
  "accounting_service_url": "https://new-accounting.example.com",
  "accounting_password": "new_password",
  "domain": "custom.domain.com"
}
```

**Response (200 OK):** Updated user object

---

### GET /api/v1/users/me/accounting

Get accounting credentials for current user.

**Authentication:** Required

**Response (200 OK):**

```json
{
  "url": "https://accounting.example.com",
  "email": "john@example.com",
  "password": "accounting_password"
}
```

---

### PATCH /api/v1/users/{user_id}/deactivate

Deactivate a user account (admin only).

**Authentication:** Required (admin)

**Response (200 OK):** Updated user with `is_active: false`

---

### PATCH /api/v1/users/{user_id}/activate

Activate a user account (admin only).

**Authentication:** Required (admin)

**Response (200 OK):** Updated user with `is_active: true`

---

### DELETE /api/v1/users/{user_id}

Delete a user account (admin or self).

**Authentication:** Required

**Response (204 No Content)**

---

## Endpoints API

### POST /api/v1/endpoints

Create a new endpoint.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `organization_id` | integer | No | Create for organization instead of self |

**Request Body:**

```json
{
  "name": "My GPT Model",
  "slug": "my-gpt-model",
  "description": "A fine-tuned GPT model for customer service",
  "type": "model",
  "visibility": "public",
  "version": "1.0.0",
  "readme": "# My GPT Model\n\nDocumentation here...",
  "tags": ["nlp", "gpt", "customer-service"],
  "policies": [
    {
      "type": "rate-limit",
      "version": "1.0",
      "enabled": true,
      "description": "Rate limiting",
      "config": {"requests_per_minute": 60}
    }
  ],
  "connect": [
    {
      "type": "rest_api",
      "enabled": true,
      "description": "REST endpoint",
      "config": {"path": "/api/v1/inference", "method": "POST"}
    }
  ],
  "contributors": [2, 3, 5]
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | Yes | 1-100 chars |
| `slug` | string | No | 3-63 chars, auto-generated if not provided |
| `description` | string | No | Max 500 chars |
| `type` | string | Yes | `model` or `data_source` |
| `visibility` | string | No | `public`, `private`, `internal` (default: public) |
| `version` | string | No | Semantic version (default: 0.1.0) |
| `readme` | string | No | Max 50,000 chars, Markdown |
| `tags` | array | No | Max 10 tags, each 1-30 chars |
| `policies` | array | No | Policy configurations |
| `connect` | array | No | Connection configurations |
| `contributors` | array | No | User IDs |

**Response (201 Created):**

```json
{
  "id": 1,
  "user_id": 1,
  "organization_id": null,
  "name": "My GPT Model",
  "slug": "my-gpt-model",
  "description": "A fine-tuned GPT model for customer service",
  "type": "model",
  "visibility": "public",
  "is_active": true,
  "version": "1.0.0",
  "readme": "# My GPT Model\n\nDocumentation here...",
  "tags": ["nlp", "gpt", "customer-service"],
  "stars_count": 0,
  "policies": [...],
  "connect": [...],
  "created_at": "2024-01-20T10:00:00Z",
  "updated_at": "2024-01-20T10:00:00Z"
}
```

---

### GET /api/v1/endpoints

List current user's endpoints.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |
| `visibility` | string | - | Filter by visibility |
| `search` | string | - | Search in name/description |

**Response (200 OK):** Array of endpoint objects

---

### GET /api/v1/endpoints/public

List all public endpoints.

**Authentication:** None

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |
| `endpoint_type` | string | - | Filter by type |

**Response (200 OK):**

```json
[
  {
    "name": "My GPT Model",
    "slug": "my-gpt-model",
    "description": "A fine-tuned GPT model",
    "type": "model",
    "version": "1.0.0",
    "readme": "...",
    "tags": ["nlp", "gpt"],
    "owner_username": "johndoe",
    "contributors_count": 3,
    "stars_count": 42,
    "policies": [...],
    "connect": [...],
    "created_at": "2024-01-20T10:00:00Z",
    "updated_at": "2024-01-20T10:00:00Z"
  }
]
```

---

### GET /api/v1/endpoints/trending

List trending endpoints by star count.

**Authentication:** None

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |
| `min_stars` | integer | 0 | Minimum star count |
| `endpoint_type` | string | - | Filter by type |

**Response (200 OK):** Array of public endpoint objects

---

### GET /api/v1/endpoints/{endpoint_id}

Get endpoint by ID.

**Authentication:** Required

**Response (200 OK):** Endpoint object

---

### GET /api/v1/endpoints/{endpoint_slug}/exists

Check if endpoint slug exists for current user.

**Authentication:** Required

**Response (200 OK):**

```json
true
```

---

### PATCH /api/v1/endpoints/{endpoint_id}

Update an endpoint.

**Authentication:** Required (owner/admin)

**Request Body:** Partial endpoint update fields

**Response (200 OK):** Updated endpoint object

---

### PATCH /api/v1/endpoints/slug/{endpoint_slug}

Update endpoint by slug.

**Authentication:** Required (owner)

**Response (200 OK):** Updated endpoint object

---

### DELETE /api/v1/endpoints/{endpoint_id}

Delete (soft delete) an endpoint.

**Authentication:** Required (owner/admin)

**Response (204 No Content)**

---

### POST /api/v1/endpoints/{endpoint_id}/star

Star an endpoint.

**Authentication:** Required

**Response (201 Created):**

```json
{
  "starred": true
}
```

---

### DELETE /api/v1/endpoints/{endpoint_id}/star

Unstar an endpoint.

**Authentication:** Required

**Response (204 No Content)**

---

### GET /api/v1/endpoints/{endpoint_id}/starred

Check if current user starred an endpoint.

**Authentication:** Required

**Response (200 OK):**

```json
{
  "starred": true
}
```

---

## Organizations API

### GET /api/v1/organizations

List current user's organizations.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |
| `role` | string | - | Filter by role (OWNER/ADMIN/MEMBER) |

**Response (200 OK):** Array of organization objects

---

### POST /api/v1/organizations

Create a new organization.

**Authentication:** Required

**Request Body:**

```json
{
  "name": "Acme AI Labs",
  "slug": "acme-ai",
  "description": "Building the future of AI",
  "domain": "acme-ai.syfthub.io"
}
```

**Response (201 Created):**

```json
{
  "id": 1,
  "name": "Acme AI Labs",
  "slug": "acme-ai",
  "description": "Building the future of AI",
  "avatar_url": null,
  "is_active": true,
  "domain": "acme-ai.syfthub.io",
  "created_at": "2024-01-20T10:00:00Z",
  "updated_at": "2024-01-20T10:00:00Z"
}
```

---

### GET /api/v1/organizations/{org_id}

Get organization details.

**Authentication:** Required (member or admin)

**Response (200 OK):** Organization object

---

### PUT /api/v1/organizations/{org_id}

Update organization.

**Authentication:** Required (admin/owner)

**Request Body:** Partial organization update fields

**Response (200 OK):** Updated organization object

---

### DELETE /api/v1/organizations/{org_id}

Delete organization (soft delete).

**Authentication:** Required (owner)

**Response (204 No Content)**

---

### GET /api/v1/organizations/{org_id}/members

List organization members.

**Authentication:** Required (member or admin)

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |
| `role` | string | - | Filter by role |

**Response (200 OK):**

```json
[
  {
    "id": 1,
    "organization_id": 1,
    "user_id": 1,
    "role": "owner",
    "is_active": true,
    "joined_at": "2024-01-20T10:00:00Z"
  }
]
```

---

### POST /api/v1/organizations/{org_id}/members

Add member to organization.

**Authentication:** Required (admin/owner)

**Request Body:**

```json
{
  "user_id": 2,
  "role": "member"
}
```

**Response (201 Created):** Organization member object

---

### PUT /api/v1/organizations/{org_id}/members/{user_id}

Update organization member role.

**Authentication:** Required (admin/owner)

**Request Body:**

```json
{
  "role": "admin"
}
```

**Response (200 OK):** Updated member object

**Error:** 400 if attempting to remove last owner

---

### DELETE /api/v1/organizations/{org_id}/members/{user_id}

Remove member from organization.

**Authentication:** Required (admin/owner or self)

**Response (204 No Content)**

**Error:** 400 if attempting to remove last owner

---

## Identity Provider API

### GET /api/v1/token

Exchange Hub session for satellite token.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `aud` | string | Yes | Target service (username) |

**Response (200 OK):**

```json
{
  "target_token": "eyJhbGciOiJSUzI1NiIs...",
  "expires_in": 60
}
```

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Missing `aud` parameter |
| 400 | Audience not found (invalid username) |
| 400 | Audience inactive (user deactivated) |
| 503 | Identity Provider not configured |

---

### GET /api/v1/token/audiences

List allowed satellite audiences.

**Authentication:** Required

**Response (200 OK):**

```json
{
  "allowed_audiences": ["syftai-space", "data-service", "model-hub"],
  "idp_configured": true
}
```

---

### POST /api/v1/verify

Verify satellite token (server-side).

**Authentication:** Required (service token)

**Request Body:**

```json
{
  "token": "eyJhbGciOiJSUzI1NiIs..."
}
```

**Success Response (200 OK):**

```json
{
  "valid": true,
  "sub": "123",
  "email": "user@example.com",
  "username": "johndoe",
  "role": "user",
  "aud": "syftai-space",
  "exp": 1705745400,
  "iat": 1705745340
}
```

**Failure Response (200 OK):**

```json
{
  "valid": false,
  "error": "token_expired",
  "message": "The satellite token has expired"
}
```

**Error Codes:**
- `invalid_signature`
- `token_expired`
- `invalid_audience`
- `invalid_issuer`
- `user_inactive`
- `decode_error`
- `missing_kid`
- `unknown_key`

---

### GET /.well-known/jwks.json

Get JSON Web Key Set for token verification.

**Authentication:** None

**Response (200 OK):**

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "hub-key-1",
      "alg": "RS256",
      "n": "0vx7agoebGcQSuuPiLJXZpt...",
      "e": "AQAB"
    }
  ]
}
```

**Cache-Control:** `public, max-age=3600`

---

## Accounting API

### GET /api/v1/accounting/user

Get current user's accounting info.

**Authentication:** Required

**Prerequisite:** User must have accounting configured

**Response (200 OK):**

```json
{
  "id": "acc_123456",
  "email": "john@example.com",
  "balance": 150.50,
  "organization": "Acme Corp"
}
```

---

### GET /api/v1/accounting/transactions

Get transaction history.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 20 | Items per page (1-100) |

**Response (200 OK):**

```json
[
  {
    "id": "tx_abc123",
    "sender_email": "john@example.com",
    "recipient_email": "service@ai.com",
    "amount": 10.00,
    "status": "completed",
    "created_by": "sender",
    "resolved_by": "recipient",
    "created_at": "2024-01-20T10:00:00Z",
    "resolved_at": "2024-01-20T10:00:05Z",
    "app_name": "GPT Model",
    "app_ep_path": "johndoe/my-gpt-model"
  }
]
```

---

### POST /api/v1/accounting/transactions

Create a new transaction.

**Authentication:** Required

**Request Body:**

```json
{
  "recipient_email": "service@ai.com",
  "amount": 10.00,
  "app_name": "GPT Model",
  "app_ep_path": "johndoe/my-gpt-model"
}
```

**Response (201 Created):** Transaction object

---

### POST /api/v1/accounting/transactions/{transaction_id}/confirm

Confirm a pending transaction.

**Authentication:** Required

**Response (200 OK):** Updated transaction with `status: "completed"`

---

### POST /api/v1/accounting/transactions/{transaction_id}/cancel

Cancel a pending transaction.

**Authentication:** Required

**Response (200 OK):** Updated transaction with `status: "cancelled"`

---

### POST /api/v1/accounting/transaction-tokens

Create transaction tokens for multiple endpoint owners.

**Authentication:** Required

**Request Body:**

```json
{
  "owner_usernames": ["alice", "bob", "carol"]
}
```

**Response (200 OK):**

```json
{
  "tokens": {
    "alice": "tx_token_abc...",
    "bob": "tx_token_def..."
  },
  "errors": {
    "carol": "User not found or no accounting configured"
  }
}
```

---

## Observability API

### POST /api/v1/errors/report

Report a frontend error.

**Authentication:** Optional

**Request Body:**

```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-20T10:00:00Z",
  "event": "frontend.error.unhandled",
  "message": "Cannot read property 'x' of undefined",
  "error": {
    "type": "TypeError",
    "message": "Cannot read property 'x' of undefined",
    "stack_trace": "TypeError: Cannot read property...\n    at Component...",
    "component_stack": "    at MyComponent\n    at App"
  },
  "context": {
    "url": "https://app.syfthub.com/endpoints",
    "user_agent": "Mozilla/5.0...",
    "app_state": {
      "route": "/endpoints",
      "authenticated": true
    }
  }
}
```

**Response (202 Accepted):**

```json
{
  "received": true,
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Content Delivery API

### GET /{owner_slug}

List owner's public endpoints (GitHub-style URL).

**Authentication:** Optional

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 10 | Items per page (1-100) |

**Response (200 OK):** Array of public endpoint objects

---

### GET /{owner_slug}/{endpoint_slug}

Get endpoint details.

**Authentication:** Optional

**Accept Header Behavior:**

| Accept | Response |
|--------|----------|
| `text/html` | Rendered HTML page |
| `application/json` | JSON endpoint object |

**Response (200 OK):** Endpoint object or HTML

---

### POST /{owner_slug}/{endpoint_slug}

Invoke endpoint (proxy to target service).

**Authentication:** Optional (depends on endpoint visibility)

**Request Body:** Any JSON payload

**Response Headers:**

| Header | Description |
|--------|-------------|
| `X-Proxy-Latency-Ms` | Request latency in milliseconds |

**Response:** Proxied response from target service

**Timeouts:**
- Data source endpoints: 30 seconds
- Model endpoints: 120 seconds

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 400 | Missing owner domain or no connections |
| 403 | Access denied by target endpoint |
| 502 | Cannot connect to target service |
| 504 | Target service timeout |

---

## Aggregator API

The Aggregator service runs on a separate port (8001) and handles RAG/chat functionality.

### POST /api/v1/chat

Non-streaming chat request.

**Request Body:**

```json
{
  "prompt": "What is machine learning?",
  "model": {
    "url": "https://model.example.com",
    "slug": "gpt-model",
    "tenant_name": "alice",
    "owner_username": "alice"
  },
  "data_sources": [
    {
      "url": "https://data.example.com",
      "slug": "ml-docs",
      "tenant_name": "bob",
      "owner_username": "bob"
    }
  ],
  "endpoint_tokens": {
    "alice": "satellite_token_for_alice",
    "bob": "satellite_token_for_bob"
  },
  "transaction_tokens": {
    "alice": "tx_token_for_alice",
    "bob": "tx_token_for_bob"
  },
  "top_k": 5,
  "max_tokens": 1024,
  "temperature": 0.7,
  "similarity_threshold": 0.5
}
```

**Response (200 OK):**

```json
{
  "response": "Machine learning is a branch of artificial intelligence...",
  "sources": {
    "Introduction to ML": {
      "slug": "ml-docs",
      "content": "Machine learning enables computers..."
    }
  },
  "retrieval_info": [
    {
      "path": "bob/ml-docs",
      "status": "success",
      "documents_retrieved": 5,
      "error_message": null
    }
  ],
  "metadata": {
    "retrieval_time_ms": 150,
    "generation_time_ms": 2500,
    "total_time_ms": 2650
  },
  "usage": {
    "prompt_tokens": 1245,
    "completion_tokens": 456,
    "total_tokens": 1701
  }
}
```

---

### POST /api/v1/chat/stream

Streaming chat request via Server-Sent Events.

**Request Body:** Same as `/api/v1/chat`

**Response:** `text/event-stream`

**Event Types:**

```
event: retrieval_start
data: {"sources": 2}

event: source_complete
data: {"path": "bob/ml-docs", "status": "success", "documents": 5}

event: retrieval_complete
data: {"total_documents": 8, "time_ms": 150}

event: generation_start
data: {}

event: token
data: {"content": "Machine "}

event: token
data: {"content": "learning "}

event: done
data: {"sources": {...}, "retrieval_info": [...], "metadata": {...}, "usage": {...}}

event: error
data: {"message": "Model generation failed"}
```

---

### GET /health

Health check endpoint.

**Response (200 OK):**

```json
{
  "status": "healthy",
  "service": "syfthub-aggregator"
}
```

---

### GET /ready

Readiness check endpoint.

**Response (200 OK):**

```json
{
  "status": "ready",
  "checks": {}
}
```

---

## Related Documentation

- [01-system-architecture.md](./01-system-architecture.md) - System overview
- [02-data-models.md](./02-data-models.md) - Data schemas
- [04-authentication-security.md](./04-authentication-security.md) - Auth details
- [08-aggregator-rag.md](./08-aggregator-rag.md) - Aggregator deep dive
- [09-sdks-integration.md](./09-sdks-integration.md) - SDK usage
