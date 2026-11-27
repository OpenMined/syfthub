# API reference: backend

The backend serves its own reference. Every route, with its parameters, request and response
schemas and status codes, is generated from the running code:

| | Dev | Production |
|---|---|---|
| Swagger UI | `http://localhost:8080/docs` | `https://{domain}/docs` |
| ReDoc | `http://localhost:8080/redoc` | `https://{domain}/redoc` |
| OpenAPI schema | `http://localhost:8080/openapi.json` | `https://{domain}/openapi.json` |

Use those for per-route detail. This page covers what they do not show: how the API is laid
out, how to authenticate, and what errors look like.

- **Base URL (dev):** `http://localhost:8080`
- **Base URL (prod):** `https://{domain}`

Most routes sit under `/api/v1`; a few are at the root.

---

## Route groups

The groups below are the tags Swagger UI sorts routes under.

| Group | Path | What it covers |
|---|---|---|
| `authentication` | `/api/v1/auth` | Register (with email code), login, Google sign-in, refresh, logout, password change and reset, email verification, personal access tokens |
| `users` | `/api/v1/users` | The caller's profile, public profiles, username and email availability, admin user management |
| `user-aggregators` | `/api/v1/users/me/aggregators` | The aggregators a user has configured, and which one is the default |
| `endpoints` | `/api/v1/endpoints` | Create, list, search and update endpoints; `sync` and `health` for Spaces reporting what they serve; uptime; stars |
| `collectives` | `/api/v1/collectives` | Collectives, their members and invitations, shared endpoints, billing summaries |
| `satellites` | `/api/v1/satellites` | The hosts (Spaces and other services) an account runs |
| `identity-provider` | `/api/v1/token`, `/api/v1/verify` | Mint and verify [satellite tokens](#satellite-tokens) |
| `wallet` | `/api/v1/wallet` | The user's wallet, balance, transactions, payments and subscriptions |
| `nats-peer`, `nats` | `/api/v1/peer-token`, `/api/v1/nats` | Credentials and encryption keys for endpoints reached over NATS |
| `admin` | `/api/v1/admin` | User statistics and export, for admins |
| `feedback` | `/api/v1/feedback` | Feedback submitted from the web app |
| `observability` | `/api/v1/errors` | Error reports from the web app and from other services |

Routes at the root, outside `/api/v1`:

| Route | What it does |
|---|---|
| `GET /` | A welcome message with the version and a link to `/docs` |
| `GET /health` | Liveness: `{"status": "healthy", "version": "..."}` |
| `GET /.well-known/jwks.json` | The public keys that verify satellite tokens |
| `GET /{owner}` | An owner's public endpoints |
| `GET /{owner}/{slug}` | One endpoint by owner and slug |
| `POST /{owner}/{slug}` | Invoke that endpoint; the Hub forwards the call to the Space that serves it |

List routes page with `skip` and `limit` query parameters.

---

## Authentication

Send a bearer token in the `Authorization` header:

```http
Authorization: Bearer <token>
```

Two kinds of token work wherever a route needs a signed-in user:

| Token | How to get it | Lifetime |
|---|---|---|
| Hub access token | `POST /api/v1/auth/login` | 30 minutes; renew with `POST /api/v1/auth/refresh` (the refresh token lasts 7 days) |
| Personal access token | `POST /api/v1/auth/tokens`; starts with `syft_pat_` | Until revoked or expired |

Swagger UI shows a padlock on any route that reads a token. That includes routes where the
token is optional: several public listing routes work without one and show more to a
signed-in caller. Admin-only and owner-only rules are enforced inside the handlers, so the
route descriptions are where they are stated.

### Satellite tokens

A satellite token is not a login to the Hub. It is a 60-second RS256 JWT the Hub mints for a
user to present to another service, such as a Space.

- **Mint:** `GET /api/v1/token?owner_username=<owner>&resource=<url>`, where `resource` is the
  URL the token is about to be sent to. The Hub resolves the pair to one of the owner's
  registered satellites and binds the token to it, so a token for one host is not accepted at
  another. `GET /api/v1/token/guest` does the same without a login. The older `aud=<username>`
  parameter is deprecated and works only while the owner runs exactly one satellite.
- **Verify:** fetch the public keys from `GET /.well-known/jwks.json` and check the token
  locally, or send it to `POST /api/v1/verify`, which accepts tokens addressed to the caller's
  own satellites.

See [Authentication explained](../explanation/authentication.md) for the wider picture.

---

## Errors

Errors are JSON with a `detail` member. It is a string for most errors:

```json
{"detail": "Endpoint not found"}
```

and an object with a `code` and `message` where a client needs to tell cases apart:

```json
{"detail": {"code": "VALIDATION_ERROR", "message": "..."}}
```

| Status | Meaning |
|---|---|
| `400` | The request is well-formed but cannot be carried out |
| `401` | No token, or the token is invalid or expired |
| `403` | The token is valid but the caller may not do this |
| `404` | No such resource |
| `409` | Conflict, for example a slug or email already in use |
| `422` | The input does not match the schema; `detail` is a list of field errors |
| `429` | Rate limited. The sign-in, registration, token refresh, password reset and email code routes are limited |
| `503` | A dependency is not configured or not reachable, for example the signing keys |

---

## Related

- [Aggregator API reference](aggregator.md)
- [MCP API reference](mcp.md)
- [Authentication explained](../explanation/authentication.md)
