# nats-auth — SyftHub NATS auth-callout service

`nats-auth` is the authorization decision point for **every** NATS connection.
The NATS server is configured with `authorization { auth_callout { ... } }`; on
each connect it sends a signed request on `$SYS.REQ.USER.AUTH`. This service
validates the presented token against Redis and replies with a signed user JWT
scoped to exactly the subjects that connection may use.

## Token classes

| Presented token | Source | Granted |
|---|---|---|
| **service token** | `NATS_AUTH_SERVICE_TOKEN` (backend, aggregator) | full `>` pub/sub |
| **host token** `ht_…` | hub `GET /api/v1/nats/credentials` → Redis `nats:host:{tok}` | sub `syfthub.spaces.{user}`, `syfthub.inbox.{user}.review`, pub `syfthub.peer.>`, `syfthub.inbox.>`, JetStream |
| **peer token** `pt_…` | hub `POST /api/v1/peer-token` → Redis `nats:peer:{tok}` | pub `syfthub.spaces.{target}`, sub `syfthub.peer.{channel}`, JetStream |
| anything else | — | rejected |

## Configuration (environment)

| Var | Required | Meaning |
|---|---|---|
| `NATS_URL` | no (`nats://nats:4222`) | NATS server |
| `NATS_AUTH_SERVICE_USER` / `NATS_AUTH_SERVICE_PASSWORD` | password yes | the `AUTH`-account user this service connects as (exempt from callout) |
| `NATS_CALLOUT_ACCOUNT_SEED` | yes | `SA…` seed of the signing account; its public key is the server's `auth_callout.issuer` |
| `NATS_CALLOUT_ACCOUNT` | no (`SYFTHUB`) | the config account issued users are placed in |
| `REDIS_URL` | no (`redis://redis:6379/0`) | token store |
| `NATS_AUTH_SERVICE_TOKEN` | yes | shared token recognised as a trusted server component |

## Generating the signing keypair

```sh
nats-auth genkey
# → NATS_CALLOUT_ACCOUNT_SEED=SA...
#   NATS_CALLOUT_ISSUER=A...
```

`NATS_CALLOUT_ACCOUNT_SEED` goes to this service; `NATS_CALLOUT_ISSUER` (public
key) goes to the NATS server's `nats.conf`. The seed is a deployment secret —
generate a fresh one per environment; never commit a production seed.

## Status

Implemented as part of Phase 5 of the direct-P2P-agent refactor. **Not yet
integration-tested** — verifying it requires the full Docker stack (NATS in
auth-callout mode + Redis + the hub backend minting `ht_`/`pt_` tokens). Roll
out staged: bring up `nats-auth`, switch `nats.conf` to auth-callout, then move
connectors onto scoped credentials.
