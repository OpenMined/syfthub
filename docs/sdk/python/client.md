# Client

[← Python SDK guide](README.md)

## Setup

```python
import syfthub

hub = syfthub.AsyncHub(
    "https://syfthub.openmined.org",  # or SYFTHUB_URL; this public Hub is the default
    token="syft_pat_...",       # or SYFTHUB_TOKEN
    budget=1.00,                # optional; a session cap per currency (see Money)
    options=syfthub.Options(),  # timeouts, retries, circuit breaker, concurrency
)
```

Use `async with syfthub.AsyncHub(...) as hub:` or call `await hub.aclose()` to release the HTTP
client. No request is made until the first call.

| Variable | Description |
|----------|-------------|
| `SYFTHUB_URL` | Hub URL. Defaults to the public Hub. |
| `SYFTHUB_TOKEN` | Bearer token: a personal access token or a login access token. |

## Sync twin

`syfthub.Hub` is the same API without `await`. It runs an `AsyncHub` on a private thread and blocks
the caller, so it works in plain scripts and inside a notebook that already has a running loop.

```python
with syfthub.Hub(token="...") as hub:
    results = hub.search("adverse events in phase 3", ["erin/trials"]).execute()
```

Every object it hands out behaves like its async counterpart: `isinstance` and `match` see the real
classes, and `wallet.refresh()` updates the wallet in place. Only `type(obj)` reveals the proxy, so
prefer `obj.kind` or `isinstance` when you need the class. Two guards: a sync call from the
private loop's own thread raises `RuntimeError` instead of deadlocking, and so does any call after
`close()`. `hub.async_hub` exposes the underlying `AsyncHub` for mixed code.

Type checkers and IDEs see the sync API with full types: `hub.search(...).preflight()` is a
`Preflight`, not a coroutine, and completions work. To annotate your own sync code, take the
names from `syfthub.sync`; at runtime they are the real classes, under a type checker they are
the sync faces.

```python
from syfthub import sync

def review(pre: sync.Preflight) -> sync.SearchPlan: ...
```

A class method that takes the hub, such as `SearchPlan.from_dict(hub, d)`, is `hub.load(SearchPlan, d)`
on the sync twin (see [Saving and resuming](search.md#saving-and-resuming)).

## Authentication

```python
await hub.login("username", "password")       # password login
await hub.login(token="syft_pat_...")          # or swap the token in later

hub.authenticated                              # True once a token is held
hub.me                                         # Identity | None, cached from the last login
identity = await hub.auth.whoami()             # GET /auth/me
```

Access tokens obtained by password login are refreshed automatically on a 401. Personal access
tokens are used as given. The SDK never stores credentials on disk.

## Options

```python
syfthub.Options(
    timeout=syfthub.Timeout(connect=5.0, read=30.0, total=60.0, lookup=5.0),
    retry=syfthub.Retry(attempts=3, server_errors=1, backoff=0.5, max_backoff=8.0),
    http2=False,                # opt in with `pip install 'syfthub-sdk[http2]'`: see below
    circuit_breaker=syfthub.CircuitBreaker(failures=5, cooldown=30.0),
    concurrency=8,          # parallel requests across Spaces
    max_items=1000,         # catalogue pages are read up to this many sources
    user_agent=None,
    http_client=None,       # your own httpx.AsyncClient, for proxies or tests
)
```

`Timeout.lookup` is the read timeout for the balance reads behind `wallets.list` and pre-flight,
which wait on many wallet hosts at once; one slow host then delays them by at most that, and shows
as `balance=None`. Everything you ask of one host, `refresh`, a top-up, an invoice poll, the query,
keeps `read`. Idle connections stay in the pool for a minute, so a Hub call that follows a slow
fan-out does not pay a new handshake.

The circuit breaker is per Space host. A connection failure, which is a timeout, a refused
connection or a DNS error, opens it at once, since the host is down; a 5xx counts toward
`failures`. An open host is held for `cooldown` seconds, and the next execute sends one probe first
and holds the rest if it fails. Rows held this way are `retryable`, so `results.retry()` after the
cooldown re-sends them.

`http2=True` asks every host for HTTP/2, so concurrent requests to one host share a connection
instead of each opening its own, which from far away costs two round trips of TCP and TLS. It
needs `pip install 'syfthub-sdk[http2]'`, and it is decided per host: the Hub and the station
negotiate it, a Space served by bare uvicorn or over plain HTTP stays on HTTP/1.1, and nothing
breaks either way. It helps when the SDK fans out to one host, such as the Space tokens behind
`wallets.list` or several sources on one Space; a single query gains nothing.

## Logging

The SDK logs to `logging.getLogger("syfthub")`: one INFO line per execute and one DEBUG line per
request with secrets redacted. A `NullHandler` is installed, so a quiet app sees nothing.
