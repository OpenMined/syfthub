# API Reference: Backend

> **Base URL (dev):** `http://localhost:8080/api/v1`
> **Base URL (prod):** `https://{domain}/api/v1`
> **Authentication:** Bearer token in `Authorization` header
> **Content-Type:** `application/json`
> **OpenAPI (dev):** `http://localhost:8080/docs`
> **Last updated:** 2026-03-27
> **Total endpoints:** 89

---

## Authentication

SyftHub uses a dual-token system. See [Authentication Explained](../explanation/authentication.md).

### Hub Token (for backend endpoints)
```http
Authorization: Bearer <hub-access-token>
```
Obtain via `POST /api/v1/auth/login`. Expires in 30 minutes.

### Satellite Token (for aggregator / external services)
```http
Authorization: Bearer <satellite-token>
```
Obtain via `GET /api/v1/token?aud={username}`. Expires in 60 seconds.

---

## Error Format

All errors return consistent JSON:

```json
{
  "detail": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Status | Meaning |
|---|---|
| 200 | Success |
| 201 | Created |
| 202 | Accepted (async processing) |
| 204 | No content (successful delete) |
| 400 | Bad request / validation error |
| 401 | Missing or invalid token |
| 403 | Token valid but insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate slug) |
| 422 | Unprocessable entity (Pydantic validation) |
| 500 | Internal server error |
| 503 | Service unavailable (e.g., RSA keys not configured) |

---

## Root Endpoints

### `GET /`

Root endpoint. Returns welcome message.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "message": "Welcome to SyftHub API",
  "version": "1.0.0",
  "docs": "/docs"
}
```

---

### `GET /health`

Health check.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `GET /.well-known/jwks.json`

Public JSON Web Key Set for verifying satellite tokens.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-id",
      "use": "sig",
      "alg": "RS256",
      "n": "<modulus>",
      "e": "AQAB"
    }
  ]
}
```

---

### `GET /{owner_slug}`

List an owner's (user or organization) accessible endpoints.

**Auth:** Optional (public endpoints visible without auth).

**Path parameters:**

| Parameter | Type | Description |
|---|---|---|
| `owner_slug` | string | Username or org slug |

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 20 | Items per page |

**Response `200 OK`:** Array of `EndpointPublicResponse`.

---

### `GET /{owner_slug}/{endpoint_slug}`

Get a specific endpoint by owner and slug. Returns HTML for browser requests, JSON for API clients.

**Auth:** Optional.

**Response `200 OK`:** `EndpointResponse` (if owner) or `EndpointPublicResponse` (otherwise).

---

### `POST /{owner_slug}/{endpoint_slug}`

Proxy/invoke a request to the endpoint's target URL. Includes SSRF protection.

**Auth:** Optional.

**Request body:** Any JSON (forwarded to target).

**Response:** Proxied response from target endpoint. Includes `X-Proxy-Latency-Ms` header.

**Errors:**

| Status | Condition |
|---|---|
| 404 | Endpoint not found or owner has no domain |
| 502 | Target endpoint returned an error |

---

## Auth (`/auth`)

### `POST /auth/register`

Register a new user account.

**Auth:** None.

**Request body:**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice Smith",
  "password": "strongpassword123",
  "accounting_service_url": "https://accounting.example.com",
  "accounting_password": "optional"
}
```

**Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `username` | string | Yes | Unique username |
| `email` | string | Yes | Unique email address |
| `full_name` | string | No | Display name |
| `password` | string | Yes | Password |
| `accounting_service_url` | string | No | External accounting service URL |
| `accounting_password` | string | No | Accounting service password |

**Response `201 Created`:**
```json
{
  "user": {
    "id": "uuid",
    "username": "alice",
    "email": "alice@example.com",
    "full_name": "Alice Smith",
    "role": "user",
    "is_active": true,
    "created_at": "2026-01-01T00:00:00Z"
  },
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:**

| Status | Condition |
|---|---|
| 409 | Email or username already registered |
| 422 | Validation error |

---

### `POST /auth/login`

Authenticate and receive tokens. Uses OAuth2 password form.

**Auth:** None.

**Request body:** `application/x-www-form-urlencoded`

| Field | Type | Required |
|---|---|---|
| `username` | string | Yes |
| `password` | string | Yes |

**Response `200 OK`:**
```json
{
  "user": { "id": "uuid", "username": "alice", "..." : "..." },
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

**Errors:**

| Status | Condition |
|---|---|
| 401 | Invalid credentials |

---

### `POST /auth/google`

Google OAuth login/registration. Auto-creates or links accounts.

**Auth:** None.

**Request body:**
```json
{
  "credential": "<google-id-token>"
}
```

**Response `200 OK`:** Same as login.

---

### `POST /auth/refresh`

Exchange a refresh token for a new access token.

**Auth:** None.

**Request body:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response `200 OK`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

### `POST /auth/logout`

Logout user by blacklisting their access token.

**Auth:** Hub token required.

**Response `204 No Content`**

---

### `GET /auth/me`

Get current authenticated user profile.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "id": "uuid",
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice Smith",
  "avatar_url": null,
  "role": "user",
  "is_active": true,
  "auth_provider": "local",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "accounting_service_url": null,
  "domain": null,
  "aggregator_url": null,
  "last_heartbeat_at": null,
  "heartbeat_expires_at": null,
  "encryption_public_key": null
}
```

---

### `PUT /auth/me/password`

Change current user's password.

**Auth:** Hub token required.

**Request body:**
```json
{
  "current_password": "oldpassword",
  "new_password": "newstrongpassword"
}
```

**Response `204 No Content`**

---

### `POST /auth/tokens`

Create a new Personal Access Token (PAT). The full token value is returned only once.

**Auth:** Hub token required.

**Request body:**
```json
{
  "name": "CI Token",
  "scopes": ["read", "write"],
  "expires_at": "2027-01-01T00:00:00Z"
}
```

**Response `201 Created`:**
```json
{
  "id": "uuid",
  "name": "CI Token",
  "token_prefix": "syft_pat_",
  "scopes": ["read", "write"],
  "expires_at": "2027-01-01T00:00:00Z",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "token": "syft_pat_xxxxxxxxxxxxxxxxxxxx"
}
```

---

### `GET /auth/tokens`

List all API tokens for the current user.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `include_inactive` | boolean | false | Include revoked tokens |
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 50 | Items per page |

**Response `200 OK`:**
```json
{
  "tokens": [ { "id": "uuid", "name": "CI Token", "..." : "..." } ],
  "total": 3
}
```

---

### `GET /auth/tokens/{token_id}`

Get details of a specific API token.

**Auth:** Hub token required.

---

### `PATCH /auth/tokens/{token_id}`

Update an API token's name.

**Auth:** Hub token required.

**Request body:**
```json
{
  "name": "Updated Name"
}
```

---

### `DELETE /auth/tokens/{token_id}`

Revoke an API token permanently (kept for audit trail).

**Auth:** Hub token required.

**Response `204 No Content`**

---

## Users (`/users`)

### `GET /users/`

List all users. Admin only.

**Auth:** Hub token required (admin role).

**Response `200 OK`:** Array of `UserResponse`.

---

### `GET /users/me`

Get current user's profile.

**Auth:** Hub token required.

**Response `200 OK`:** `UserResponse` (same as `GET /auth/me`).

---

### `GET /users/me/accounting`

Get current user's accounting service credentials.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "url": "https://accounting.example.com",
  "email": "alice@example.com",
  "password": "plaintext-password"
}
```

---

### `GET /users/me/tunnel-credentials`

Get tunnel credentials for the user's domain.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "auth_token": "ngrok-token",
  "domain": "alice.example.com"
}
```

---

### `POST /users/me/heartbeat` _(deprecated)_

Send heartbeat indicating the user's domain is online. **Use `POST /endpoints/health` instead.**

**Auth:** Hub token required.

**Request body:**
```json
{
  "url": "https://alice.example.com",
  "ttl_seconds": 300
}
```

**Response `200 OK`:**
```json
{
  "status": "ok",
  "received_at": "2026-01-01T00:00:00Z",
  "expires_at": "2026-01-01T00:05:00Z",
  "domain": "alice.example.com",
  "ttl_seconds": 300
}
```

---

### `GET /users/check-username/{username}`

Check if a username is available.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "available": true,
  "username": "alice"
}
```

---

### `GET /users/check-email/{email}`

Check if an email is available.

**Auth:** None.

---

### `GET /users/{user_id}`

Get a user by ID.

**Auth:** Hub token required (self or admin).

---

### `PUT /users/me`

Update current user's profile.

**Auth:** Hub token required.

**Request body (all fields optional):**
```json
{
  "username": "new_username",
  "email": "new@example.com",
  "full_name": "New Name",
  "avatar_url": "https://...",
  "accounting_service_url": "https://...",
  "accounting_password": "...",
  "domain": "alice.example.com",
  "aggregator_url": "https://..."
}
```

---

### `PUT /users/{user_id}`

Update a user by ID.

**Auth:** Hub token required (self or admin).

---

### `PATCH /users/{user_id}/deactivate`

Deactivate a user.

**Auth:** Hub token required (admin only).

---

### `PATCH /users/{user_id}/activate`

Activate a user.

**Auth:** Hub token required (admin only).

---

### `DELETE /users/{user_id}`

Delete a user.

**Auth:** Hub token required (self or admin).

**Response `204 No Content`**

---

## User Aggregators (`/users/me/aggregators`)

### `GET /users/me/aggregators`

List all aggregator configurations for the current user.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "aggregators": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "name": "My Aggregator",
      "url": "https://agg.example.com",
      "is_default": true,
      "created_at": "2026-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z"
    }
  ],
  "default_aggregator_id": "uuid"
}
```

---

### `POST /users/me/aggregators`

Create a new aggregator configuration. First one is auto-set as default.

**Auth:** Hub token required.

**Request body:**
```json
{
  "name": "My Aggregator",
  "url": "https://agg.example.com",
  "is_default": false
}
```

---

### `GET /users/me/aggregators/{aggregator_id}`

Get a specific aggregator config.

**Auth:** Hub token required.

---

### `PUT /users/me/aggregators/{aggregator_id}`

Update an aggregator config.

**Auth:** Hub token required.

---

### `DELETE /users/me/aggregators/{aggregator_id}`

Delete an aggregator config. Reassigns default if needed.

**Auth:** Hub token required.

**Response `204 No Content`**

---

### `PATCH /users/me/aggregators/{aggregator_id}/default`

Set an aggregator as the default.

**Auth:** Hub token required.

---

## Endpoints (`/endpoints`)

### `POST /endpoints`

Create a new endpoint.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `organization_id` | UUID | Optional — create under an organization |

**Request body:**
```json
{
  "name": "My Language Model",
  "slug": "my-language-model",
  "type": "model",
  "visibility": "public",
  "description": "A fine-tuned language model",
  "version": "1.0.0",
  "readme": "# My Model\n\nMarkdown documentation...",
  "tags": ["nlp", "generation"],
  "policies": {},
  "connect": [
    { "url": "https://my-service.example.com/infer" }
  ],
  "contributors": ["bob", "charlie"]
}
```

**Fields:**

| Field | Type | Required | Values | Description |
|---|---|---|---|---|
| `name` | string | Yes | — | Display name |
| `slug` | string | No | URL-safe | Auto-generated from name if omitted |
| `type` | string | Yes | `model`, `data_source`, `model_data_source` | Endpoint type |
| `visibility` | string | No | `public`, `internal`, `private` | Default: `private` |
| `description` | string | No | — | Short description |
| `version` | string | No | Semver | e.g., `1.0.0` |
| `readme` | string | No | Markdown | Full documentation |
| `tags` | string[] | No | — | Searchable tags |
| `policies` | object | No | — | Access policy config (JSON) |
| `connect` | object[] | No | — | Connection configurations |
| `contributors` | string[] | No | — | Contributor usernames |

**Response `201 Created`:** Full `EndpointResponse`.

**Errors:**

| Status | Condition |
|---|---|
| 409 | Slug already taken by this owner |
| 422 | Validation error |

---

### `GET /endpoints`

List current user's endpoints.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 20 | Items per page |
| `visibility` | string | — | Filter by visibility |
| `search` | string | — | Search term |

---

### `GET /endpoints/public`

List all public endpoints. No authentication required.

**Auth:** None.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Pagination offset |
| `limit` | integer | 20 | Items per page |
| `endpoint_type` | string | — | Filter: `model`, `data_source` |
| `search` | string | — | Full-text search |

---

### `GET /endpoints/public/grouped`

List public endpoints grouped by owner (for Global Directory view).

**Auth:** None.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_per_owner` | integer | 5 | Max endpoints per owner group |

---

### `GET /endpoints/public/owners`

List owners with public endpoints and counts (lightweight, for CLI `ls`).

**Auth:** None.

---

### `GET /endpoints/public/by-owner/{owner_slug}`

List all public endpoints for a specific owner.

**Auth:** None.

---

### `GET /endpoints/public/{owner_username}/{slug}`

Get a single public endpoint by owner and slug.

**Auth:** None.

---

### `GET /endpoints/trending`

List trending public endpoints sorted by stars.

**Auth:** None.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Offset |
| `limit` | integer | 20 | Items per page |
| `min_stars` | integer | 0 | Minimum star count |
| `endpoint_type` | string | — | Filter by type |

---

### `GET /endpoints/guest-accessible`

List public, active, policy-free endpoints accessible to guest users.

**Auth:** None.

---

### `POST /endpoints/search`

Semantic search endpoints using Meilisearch.

**Auth:** None.

**Request body:**
```json
{
  "query": "language model for code",
  "top_k": 10,
  "type": "model"
}
```

**Response `200 OK`:**
```json
{
  "results": [
    {
      "name": "CodeLLM",
      "slug": "codellm",
      "relevance_score": 0.95,
      "...": "..."
    }
  ],
  "total": 42,
  "query": "language model for code"
}
```

---

### `POST /endpoints/sync`

**Destructive** atomic sync — deletes all user endpoints and recreates from the provided list.

**Auth:** Hub token required.

**Request body:**
```json
{
  "endpoints": [
    { "name": "Model A", "type": "model", "..." : "..." },
    { "name": "Data Source B", "type": "data_source", "..." : "..." }
  ]
}
```

**Response `200 OK`:**
```json
{
  "synced": 2,
  "deleted": 5,
  "endpoints": [ "..." ]
}
```

---

### `POST /endpoints/health`

Report per-endpoint health status. **Preferred over deprecated heartbeat endpoints.** Also registers the owner's domain.

**Auth:** Hub token required.

**Request body:**
```json
{
  "endpoints": [
    { "slug": "my-model", "status": "online", "checked_at": "2026-01-01T00:00:00Z" },
    { "slug": "my-data", "status": "offline", "checked_at": "2026-01-01T00:00:00Z" }
  ],
  "ttl_seconds": 300,
  "url": "https://alice.example.com"
}
```

**Response `200 OK`:**
```json
{
  "updated": 2,
  "ignored": 0
}
```

---

### `GET /endpoints/{endpoint_id}`

Get a specific endpoint by ID.

**Auth:** Hub token required.

---

### `PATCH /endpoints/{endpoint_id}`

Update an endpoint.

**Auth:** Hub token required (must be owner).

**Request body (all fields optional):**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "visibility": "public",
  "version": "2.0.0",
  "readme": "# Updated\n...",
  "tags": ["updated"],
  "policies": {},
  "connect": [],
  "contributors": ["bob"]
}
```

---

### `GET /endpoints/{endpoint_slug}/exists`

Check if an endpoint slug exists for the current user.

**Auth:** Hub token required.

**Response `200 OK`:** `true` or `false`

---

### `PATCH /endpoints/slug/{endpoint_slug}`

Update an endpoint by slug.

**Auth:** Hub token required.

---

### `DELETE /endpoints/slug/{endpoint_slug}`

Delete an endpoint by slug.

**Auth:** Hub token required.

**Response `204 No Content`**

---

### `DELETE /endpoints/{endpoint_id}`

Delete an endpoint by ID.

**Auth:** Hub token required.

**Response `204 No Content`**

---

### `PATCH /endpoints/{endpoint_id}/admin`

Admin-only endpoint updates (is_active, stars_count override).

**Auth:** Hub token required (admin role).

---

### `POST /endpoints/{endpoint_id}/star`

Star an endpoint.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "starred": true
}
```

---

### `DELETE /endpoints/{endpoint_id}/star`

Unstar an endpoint.

**Auth:** Hub token required.

**Response `204 No Content`**

---

### `GET /endpoints/{endpoint_id}/starred`

Check if current user has starred an endpoint.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "starred": false
}
```

---

## Organizations (`/organizations`)

### `POST /organizations`

Create a new organization. Creator becomes owner.

**Auth:** Hub token required.

**Request body:**
```json
{
  "name": "My Team",
  "slug": "my-team",
  "description": "Our ML team",
  "avatar_url": "https://...",
  "domain": "team.example.com"
}
```

**Response `201 Created`:**
```json
{
  "id": "uuid",
  "name": "My Team",
  "slug": "my-team",
  "description": "Our ML team",
  "avatar_url": "https://...",
  "is_active": true,
  "domain": "team.example.com",
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### `GET /organizations`

List organizations the current user belongs to.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Offset |
| `limit` | integer | 20 | Items per page |
| `role` | string | — | Filter by role: `owner`, `admin`, `member` |

---

### `GET /organizations/{org_id}`

Get organization details.

**Auth:** Hub token required (must be member).

---

### `PUT /organizations/{org_id}`

Update organization.

**Auth:** Hub token required (org admin/owner or site admin).

---

### `DELETE /organizations/{org_id}`

Delete organization (soft delete).

**Auth:** Hub token required (org owner or site admin).

**Response `204 No Content`**

---

### `GET /organizations/{org_id}/members`

List organization members.

**Auth:** Hub token required (must be member).

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `skip` | integer | 0 | Offset |
| `limit` | integer | 20 | Items per page |
| `role` | string | — | Filter by role |

---

### `POST /organizations/{org_id}/members`

Add a member to the organization.

**Auth:** Hub token required (org admin/owner).

**Request body:**
```json
{
  "user_id": "uuid",
  "role": "member"
}
```

**Roles:** `owner`, `admin`, `member`

---

### `PUT /organizations/{org_id}/members/{user_id}`

Update a member's role.

**Auth:** Hub token required (org admin/owner).

---

### `DELETE /organizations/{org_id}/members/{user_id}`

Remove a member. Prevents removing the last owner.

**Auth:** Hub token required (org admin/owner, or self-removal).

**Response `204 No Content`**

---

### `POST /organizations/{org_id}/heartbeat` _(deprecated)_

Send heartbeat for org domain. **Use `POST /endpoints/health` instead.**

**Auth:** Hub token required (org admin/owner).

---

### `PATCH /organizations/{org_id}/admin`

Admin-only org update (is_active override).

**Auth:** Hub token required (site admin).

---

### `PATCH /organizations/{org_id}/members/{user_id}/admin`

Admin-only member update (is_active override).

**Auth:** Hub token required (site admin).

---

## Identity Provider (`/token`, `/.well-known`)

### `GET /token`

Exchange hub token for an audience-bound RS256 satellite token.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `aud` | Yes | Target service audience — must be an active username |

**Response `200 OK`:**
```json
{
  "target_token": "eyJ...",
  "expires_in": 60
}
```

**Errors:**

| Status | Condition |
|---|---|
| 400 | Invalid or inactive audience |
| 503 | RSA keys not configured |

---

### `GET /token/guest`

Get a guest satellite token (no auth required). For policy-free public endpoints.

**Auth:** None.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `aud` | Yes | Target service audience |

---

### `GET /token/audiences`

List valid audience identifiers and IdP configuration status.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "allowed_audiences": ["alice", "bob", "my-team"],
  "idp_configured": true
}
```

---

### `POST /verify`

Server-side satellite token verification. Services can only verify tokens intended for their own audience.

**Auth:** Hub token required.

**Request body:**
```json
{
  "token": "eyJ..."
}
```

**Response `200 OK`:**
```json
{
  "valid": true,
  "sub": "uuid",
  "email": "alice@example.com",
  "username": "alice",
  "role": "user",
  "aud": "bob",
  "exp": 1735689600,
  "iat": 1735689540
}
```

---

## NATS (`/nats`, `/peer-token`)

### `POST /peer-token`

Generate a temporary NATS peer token for aggregator-to-space communication.

**Auth:** Hub token required.

**Request body:**
```json
{
  "target_usernames": ["alice", "bob"]
}
```

**Response `200 OK`:**
```json
{
  "peer_token": "opaque-token",
  "peer_channel": "channel-id",
  "expires_in": 120,
  "nats_url": "wss://hub.syft.com/nats"
}
```

---

### `GET /nats/credentials`

Get NATS auth token for WebSocket connections.

**Auth:** Hub token required.

**Response `200 OK`:**
```json
{
  "nats_auth_token": "token"
}
```

---

### `PUT /nats/encryption-key`

Register an X25519 public key for tunnel encryption.

**Auth:** Hub token required.

**Request body:**
```json
{
  "encryption_public_key": "base64url-encoded-32-byte-key"
}
```

---

### `GET /nats/encryption-key/{username}`

Look up a user's X25519 public key.

**Auth:** None.

**Response `200 OK`:**
```json
{
  "encryption_public_key": "base64url-encoded-key-or-null"
}
```

---

## Accounting (`/accounting`)

These endpoints proxy to an external accounting service.

### `GET /accounting/user`

Get current user's accounting info/balance.

**Auth:** Hub token required.

---

### `GET /accounting/transactions`

Get transaction history.

**Auth:** Hub token required.

**Query parameters:**

| Parameter | Type | Default |
|---|---|---|
| `skip` | integer | 0 |
| `limit` | integer | 20 |

---

### `POST /accounting/transactions`

Create a new transaction.

**Auth:** Hub token required.

**Request body:**
```json
{
  "recipientEmail": "bob@example.com",
  "amount": 100,
  "appName": "My App",
  "appEpPath": "alice/my-model"
}
```

---

### `POST /accounting/transactions/{transaction_id}/confirm`

Confirm a pending transaction.

**Auth:** Hub token required.

---

### `POST /accounting/transactions/{transaction_id}/cancel`

Cancel a pending transaction.

**Auth:** Hub token required.

---

### `POST /accounting/transaction-tokens`

Create transaction tokens for multiple endpoint owners (pre-authorize payments for chat flow).

**Auth:** Hub token required.

**Request body:**
```json
{
  "owner_usernames": ["alice", "bob"]
}
```

**Response `200 OK`:**
```json
{
  "tokens": {
    "alice": "token-a",
    "bob": "token-b"
  },
  "errors": {}
}
```

---

## Feedback (`/feedback`)

### `POST /feedback`

Submit feedback or bug report. Creates a Linear issue. Supports screenshot upload.

**Auth:** Hub token required.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `category` | string | No | Feedback category |
| `description` | string | Yes | Feedback text |
| `page_url` | string | No | Page where feedback originated |
| `app_version` | string | No | App version |
| `browser_info` | string | No | Browser info |
| `screenshot` | file | No | Screenshot attachment |

**Response `200 OK`:**
```json
{
  "success": true,
  "message": "Feedback submitted",
  "ticket_id": "LIN-123"
}
```

---

## Observability (`/errors`)

### `POST /errors/report`

Report a frontend error for centralized logging.

**Auth:** Optional.

**Request body:**
```json
{
  "correlation_id": "uuid",
  "timestamp": "2026-01-01T00:00:00Z",
  "event": "unhandled_error",
  "message": "Cannot read property 'x' of undefined",
  "error": {
    "type": "TypeError",
    "message": "Cannot read property 'x' of undefined",
    "stack_trace": "...",
    "component_stack": "..."
  },
  "context": {
    "url": "https://hub.syft.com/browse",
    "user_agent": "Mozilla/5.0 ...",
    "app_state": {}
  }
}
```

**Response `202 Accepted`:**
```json
{
  "received": true,
  "correlation_id": "uuid"
}
```

---

### `POST /errors/service-report`

Report a service-level error (aggregator, MCP, etc.).

**Auth:** None.

**Response `202 Accepted`**

---

## Response Models Reference

### EndpointResponse (full, for owners)

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "organization_id": "uuid | null",
  "name": "My Model",
  "slug": "my-model",
  "description": "Description",
  "type": "model",
  "visibility": "public",
  "is_active": true,
  "contributors": ["bob"],
  "version": "1.0.0",
  "readme": "# My Model\n...",
  "tags": ["nlp"],
  "stars_count": 42,
  "policies": {},
  "connect": [{"url": "https://..."}],
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "health_status": "online",
  "health_checked_at": "2026-01-01T00:00:00Z",
  "health_ttl_seconds": 300
}
```

### EndpointPublicResponse (for non-owners)

Same as above but includes `owner_username` and omits internal fields.

### UserResponse

```json
{
  "id": "uuid",
  "username": "alice",
  "email": "alice@example.com",
  "full_name": "Alice Smith",
  "avatar_url": null,
  "role": "user",
  "is_active": true,
  "auth_provider": "local",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z",
  "accounting_service_url": null,
  "domain": null,
  "aggregator_url": null,
  "last_heartbeat_at": null,
  "heartbeat_expires_at": null,
  "encryption_public_key": null
}
```

---

## Related

- [Authentication Explained](../explanation/authentication.md) — token architecture
- [PKI Workflow](../explanation/pki-workflow.md) — satellite token deep dive
- [Aggregator API](aggregator.md) — RAG chat endpoints
- [MCP API](mcp.md) — MCP protocol endpoints
