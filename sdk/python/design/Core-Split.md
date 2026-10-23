# SyftHub SDK Core Split

Design note, 2026-10-12. Which parts of the SDK would live in one Rust core, which parts stay per
language, how a call crosses that boundary, and how a binding talks to the core at all. Numbers come
from the Python first cut as it stood on this date (branch `feat/sdk-v2-first-cut`). Rendered copy with
diagrams: `Core-Split.html` beside this file, published at https://claude.ai/artifact/96KadQVui9nkCi2Ti4MD6C.

## Context

The Python SDK v2 first cut is being built by hand. The question raised on 2026-10-12: could the core
client be written once (Rust was the candidate) and each language get a thin binding? This note is the
estimate of what such a split would look like. The recommendation, stated up front:

- Finish the Python first cut as the reference implementation.
- Extract its rules into JSON conformance vectors (facts to preflight, response to row, failures to
  breaker state). TypeScript and Go ports must pass the same vectors.
- Revisit a Rust core when either the Go UniFFI generator catches up with upstream or WASI async
  bindings land for Python and JavaScript. The vectors become the core's acceptance tests on day one,
  so nothing is thrown away.

## The rule for sorting features

**Policy and protocol go inside. Surface and transport stay outside.** Anything that must behave
identically in every language (what the Hub and Spaces say on the wire, which rows send, what a 402
means, when a breaker opens) belongs in the core. Anything a user touches directly (method names,
native types, their own HTTP client, exceptions, async flavour) belongs to the language.

```
PER LANGUAGE ("skin")      Python            TypeScript        Go               Swift / Kotlin
                           pydantic wrappers  interfaces        structs          async throws / suspend
                           AsyncHub + Hub     Promise API       context API      URLSession / OkHttp
                           httpx transport    fetch transport   net/http
                                |                 |                |                 |
GENERATED BINDINGS         UniFFI · Python   wasm-bindgen/napi  uniffi-bindgen-go  UniFFI · Swift, Kotlin
                                |                 |                |                 |
                                v                 v                v                 v
ONE RUST CORE              syfthub-ffi   exported API: compose, preflight, execute, wallets, snapshots
                           syfthub-core  protocol | rules | resilience | state
                                   ^
                                   '---- dashed: Transport.send(request), clock, log lines
                                         (the core calls back into the skin, a foreign trait)
```

Core compartments:

| Compartment | Holds |
|---|---|
| protocol | Hub and Space routes, session renewal, satellite token cache, policy and pricing parsing |
| rules | pre-flight verdicts, response classifier, budget and wallet maths, MPP 402 pay and resend |
| resilience | retry with jitter, per-host breaker with one probe, concurrency limit, one 401 re-mint |
| state | plan, preflight, results records; snapshot JSON and version; spent; breaker state; 60s source cache |

## Feature allocation

Line counts are the Python module sizes on 2026-10-12 (4,745 lines in total under `src/syfthub`).

| Feature | Where | Why there | Python lines |
|---|---|---|---|
| **Session and auth** | | | |
| Login, refresh, whoami, token renewal under 401 storms | core | One correct renewal lock instead of four | 160 |
| Satellite token cache (80% TTL, one re-mint on 401) | core | Protocol detail every port got subtly wrong before | in auth |
| Reading `SYFTHUB_URL` and `SYFTHUB_TOKEN` | skin | Idiomatic per language; the core takes explicit values | 10 |
| **Sources** | | | |
| Hub routes, pagination to `max_items`, 60s cache | core | Wire format and paging rules | 279 |
| Policy parsing: pricing, rails, bundles, access globs, reachability, query URL, tenant | core | The Hub and Space contract in one place | 280 |
| `SourceList` views: `matching`, `filter`, `pick`, `+` | shared | Fuzzy scoring in core; the collection type is native | 120 |
| **Wallets and payments** | | | |
| Grouping by wallet id, balance, top-up, invoices, `wait_paid` polling | core | Money rules and Space routes | 433 |
| `Money` as Decimal, bundle suggestion | core | Rust decimal in core; skins expose their decimal type | 76 |
| **Search pipeline** | | | |
| Compose and validate a plan, `skip` | core | Validation messages identical everywhere | 229 |
| Pre-flight rules: skip, reachability, access, circuit, credits per wallet, budget | core | This is the product; one implementation | 682 |
| Response classifier: 2xx, 402 prepaid, 402 MPP, 403 variants, 404, 401, 5xx | core | Reads `policy_metadata` the same way for every port | 270 |
| Execute: fan-out, per-host probe, MPP pay through the Hub, spend recording | core | Concurrency and billing must not drift | in search |
| `Results` views: `only`, `drop`, `top`, `+`, document ordering | shared | Ordering rule in core; iteration and indexing native | 267 |
| **Resilience** | | | |
| Retry with full jitter, retryable statuses | core | Policy, not plumbing | 21 |
| Per-host circuit breaker with one probe after cooldown | core | State machine; identical across ports | 65 |
| The HTTP client: pool, TLS, proxies, timeouts, user agent | skin | Implements the core's `Transport` trait with httpx, fetch or net/http | 145 |
| Header redaction in debug logs | core | The core emits log lines already redacted; the skin routes them | in client |
| **Snapshots** | | | |
| `to_dict` / `from_dict` for plan, invoice, results; version check | core | One JSON schema, one `StaleSnapshot` rule | 83 |
| **Surface** | | | |
| Namespaces `hub.sources`, `hub.wallets`, method names, keyword arguments | skin | What users read in docs; must feel native | 186 |
| Model types: pydantic in Python, interfaces in TS, structs in Go | skin | Thin wrappers over the core's records | ~500 |
| Error hierarchy: `SyftHubError` and subclasses | skin | The core returns one error enum; the skin maps it | 83 |
| Async and sync twins | skin | The core exposes async; the sync twin blocks on it with no private loop | 221 |
| **Testing and packaging** | | | |
| Conformance vectors: facts to preflight, response to row, failures to breaker state | core | Shared JSON fixtures; the core's own test suite | new |
| `syfthub.testing` fakes (FakeHub, FakeSpace) | shared | Canned bodies in core; the mock transport is per language | 530 |
| Wheels, npm packages, Go modules, docs, examples | skin | One release matrix per language | n/a |
| **Later cuts** | | | |
| Chat room, `chat.context`, filters, client-side aggregator fan-out | core | Same shape as search: rules and protocol | future |

## What the numbers say

| | |
|---|---|
| Python lines in the first cut today | 4,745 |
| Logic that moves into the core | about 65% |
| Python skin left (models, namespaces, sync twin, transport) | about 1,500 lines |
| Rust core, written once | about 4 to 5 thousand lines |

The skin is smaller in the other languages. TypeScript and Go have no sync twin and no pydantic layer,
so each lands near 800 lines plus tests. Swift and Kotlin come almost for free from UniFFI, which is the
main reason mobile SDKs pick this path.

The 65% is logic, not effort. Writing the core is a rewrite of what exists, and the Rust side gains an
FFI crate, a trait for transport, and a release matrix of native wheels. Expect the first core to cost
about as much as the Python first cut did, before any skin is written.

## One call across the boundary

`await plan.execute()` with the transport-outside variant:

```
Python skin                      Rust core                              Hub and Spaces
-----------                      ---------                              --------------
await plan.execute()  --------> execute(plan record)
                                 pre-flight: resolve sources,
                                 pick wallets to read
httpx.AsyncClient     <- - - - - Transport.send(GET balance)
  GET credits_url     ------------------------------------------------> Space
  bytes, status, hdrs <------------------------------------------------
                      - - - - -> (reply buffer)
                                 rules: verdict per row, actions,
                                 budget check
semaphore in core,    <- - - - - Transport.send(POST query) x n
I/O here
  POST /endpoints/{slug}/query ---------------------------------------> Spaces
  200 | 402 | 403 | 5xx <----------------------------------------------
                      - - - - -> (reply buffers)
                                 classify each reply, pay MPP 402
                                 via the Hub, record spend
Results.model_validate <-------- Results record (rows, actions)
-> pydantic Results to the app
```

Every byte on the wire still leaves through the skin's own HTTP client, so respx mocks, proxies and
custom clients keep working. The core decides what to send and what the replies mean. One search with
three sources crosses the boundary about eight times, which is cheap next to the network round trips.

## The one decision inside the decision: where the HTTP client lives

### Transport outside the core (leaning towards this)

The core defines an async `Transport` trait and the skin implements it with its native client. UniFFI
supports foreign-implemented async traits for Python, Swift and Kotlin.

- Users keep `Options.http_client`, proxies, TLS settings and respx or nock mocks.
- The sync twin passes a blocking client; the core runs it on its own thread. No private event loop in
  Python.
- Cost: each request crosses the boundary twice, and the core cannot stream bodies without more trait
  surface.
- Go and TypeScript bindings need the same callback support; for wasm that means a JS `fetch` shim,
  which is routine.

### Transport inside the core

The core ships reqwest and tokio and talks to the network itself. This is what Matrix and Bitwarden do.

- Fewer boundary crossings and streaming comes naturally later.
- Users lose their own client. Mocking means a core-level fake server, so the testing package moves
  into Rust too.
- TLS roots, proxies and corporate certificates become a Rust configuration problem reported through
  Python.
- The wasm build cannot use reqwest's native stack and needs a fetch backend anyway, so the "one
  transport" promise only holds off the web.

## How a binding talks to the core

No server, no sockets, no JSON over a wire. The binding and the core run in the same process, and a
call into the core is an ordinary machine-level function call into a shared library. Latency is
nanoseconds.

### What the core compiles to

Cargo builds the Rust core into a native shared library: `libsyfthub.so` on Linux, `.dylib` on macOS,
`.dll` on Windows. The library exports plain C functions, because C's calling convention is the one
thing every language already knows how to call. Rust stays hidden behind that surface. For the browser
the same crate compiles to a `.wasm` module that the JavaScript engine runs in its own linear memory.

### How each language loads it

- **Python** opens the library with `ctypes` at import time. The library ships inside the wheel, so
  `pip install` is all the user does.
- **Node** loads it as a native addon through N-API, the way `better-sqlite3` or `esbuild` do.
- **Go** links it at build time through cgo, so the Go binary contains the core.
- **Swift and Kotlin** link it as a static library in the app bundle, Kotlin through JNA.

### One call, start to finish

```
Python, your code          generated binding                   libsyfthub.so (Rust)
-----------------          -----------------                   --------------------
pre = hub.preflight(plan)  -> lower(plan) -> bytes
                              C call, same thread:
                              fn_hub_preflight(handle, buf)  -> unpack SearchPlan
                                                                 run the rules
                                                                 pack Preflight -> bytes
                              check status -> raise?         <- status: ok | error code
pre.rows, pre.actions      <- lift(bytes) -> Preflight

A Hub object never crosses: Python holds an integer handle to Rust memory and passes it back on every call.
```

The byte buffer is a compact binary layout generated from the same interface description on both
sides, so the two cannot disagree about field order.

### What crosses the boundary

C understands integers, floats and pointers, so the generator writes the glue for everything else.

- **Scalars** pass as themselves.
- **Strings and records** such as a `SearchPlan` are packed into a length-prefixed byte buffer by the
  binding, unpacked in Rust, and the reply comes back the same way. UniFFI calls this a `RustBuffer`.
  It is binary, not JSON.
- **Objects with behaviour** such as a `Hub` session never cross. The binding gets an opaque handle, an
  integer pointing at Rust memory, and every method passes that handle back in. The Python class is a
  thin shell around the handle with a finalizer that tells Rust to free it.
- **Errors** come back in a status struct beside the return value. The generated Python turns a
  non-zero status into the matching exception class.

The generated glue for one method, simplified, next to the Rust that produces it:

```python
# generated by UniFFI
def preflight(hub: Hub, plan: SearchPlan) -> Preflight:
    buf = _lower_SearchPlan(plan)  # pack fields into bytes
    status = RustCallStatus()
    out = _lib.uniffi_syfthub_fn_method_hub_preflight(hub._handle, buf, byref(status))
    _check(status)  # raise the SyftHubError subclass if set
    return _lift_Preflight(out)  # unpack bytes into the Python record
```

```rust
// what you actually write
#[uniffi::export]
impl Hub {
    pub async fn preflight(&self, plan: SearchPlan) -> Result<Preflight, SyftHubError> { ... }
}
```

### Async without a server

The Rust function returns a future. The binding hands Rust a completion callback and immediately
returns a Python awaitable. Rust's runtime drives the future on its own threads, and when it finishes
it calls the callback, which resolves the Python future on the caller's event loop. In Swift and Kotlin
the same mechanism surfaces as `async throws` and `suspend`. The sync twin is the same export called
through a blocking wrapper.

### The core calling back into the skin

This is what the transport-outside variant relies on. The binding builds a small table of C function
pointers that trampoline into Python methods and registers it with Rust once. When the core needs an
HTTP request it calls `send` through that table, Python runs httpx, and the response bytes go back
through a buffer. Python's GIL is released while Rust runs and reacquired for the callback, so other
Python threads keep going.

### Memory rule

Two allocators coexist, so whoever allocated a buffer frees it. Rust allocates its reply buffers and
exports a free function that the binding calls after unpacking. Handles are freed when the Python object
is garbage collected. The generator writes all of this, which is the main reason to use one rather than
hand-rolling ctypes.

### The other model, for contrast

Tailscale's `tailscaled`, Docker's daemon and language servers run a separate process and talk over a
socket. That buys isolation and crash containment at the cost of a process to manage, a protocol to
version, and real latency per call. For an SDK that a notebook imports, in-process linking is the right
shape.

## What stays open

- **Pydantic is a wrapper, not the source of truth.** UniFFI emits dataclasses. Keeping the pydantic
  rule means a generated-to-pydantic layer with a conformance test that both agree.
- **Go binding currency.** The community Go generator (NordSecurity `uniffi-bindgen-go`) targets
  UniFFI 0.25 while upstream is at 0.32, so the Go skin either pins the core's UniFFI version or waits.
- **Debuggability.** A hung search becomes a Rust trace for a Python user. The core needs structured,
  per-row timing in the `Results` record to compensate.
- **Sequencing.** Finish the Python first cut and extract its rules into JSON conformance vectors
  first. Those vectors are the core's acceptance tests on day one, so nothing in the Python work is
  thrown away.

## Landscape surveyed on 2026-10-12

| Approach | Who does it | Fit |
|---|---|---|
| Rust core, UniFFI for Python/Swift/Kotlin, wasm-bindgen for JS, third-party generator for Go | Mozilla, Bitwarden, Matrix, Nym | Mature for mobile and Python; Go generator lags; JS needs a second binding layer |
| Rust core, WASM component model with WIT bindings | Bytecode Alliance ecosystem | Async bindings for Python and JS still in progress per the WASI 0.3 announcement |
| Go core, cgo c-shared library | Tailscale | Go already in the repo, but every host embeds the Go runtime and packaging is worse than maturin |
| Spec plus generated thin clients, hand-written policy per language | Stripe, AWS Smithy | Generates the `_api` layer only; rules still written per language against one conformance suite |
| Python as reference implementation plus JSON test vectors | Common for protocol SDKs | Zero FFI cost; keeps the door open; catches drift between ports |

Sources: UniFFI changelog (github.com/mozilla/uniffi-rs), NordSecurity uniffi-bindgen-go,
Nym FFI docs, Bitwarden SDK architecture docs (contributing.bitwarden.com), WASI 0.3 announcement
(bytecodealliance.org), AGNTCY post on Rust and Go with UniFFI.

## Effort estimate for a Rust core with Python bindings (2026-10-13)

Measured on d491b05: 5,169 source lines, 3,107 test lines, 144 unit tests, dependencies httpx and
pydantic only. Assumes the transport-outside design above and UniFFI for Python.

| # | Package | Covers | Rust lines | Days |
|---|---|---|---|---|
| 1 | Workspace and build | cargo workspace (`syfthub-core`, `syfthub-ffi`), maturin, wheel matrix (Linux x86_64 + aarch64, macOS, Windows) | 0 | 3–4 |
| 2 | Domain types | enums, Money on rust_decimal, policy and pricing parsing, wallets, plan, rows, actions, results, per-currency budget | 900 | 4–5 |
| 3 | Transport trait | async foreign trait, request/response records with per-request timeout, retry and breaker around it, redaction | 400 | 3–4 |
| 4 | Protocol clients | Hub and Space routes, session renewal lock, satellite token cache, MPP pay route | 500 | 3 |
| 5 | Search pipeline | pre-flight rules, classifier, execute with semaphore and half-open probe, MPP resend, spend | 1,200 | 5–6 |
| 6 | Sources and wallets | pagination, 60s cache, wallet grouping, parallel fresh reads | 300 | 2 |
| 7 | Snapshots | serde JSON matching today's `to_dict` layout exactly, version check | 200 | 1–2 |
| 8 | Python skin | pydantic wrappers both ways, same namespaces and signatures, error mapping, logging bridge, httpx transport (async + sync), testing fakes as a transport | 1,500 (Python) | 5–6 |
| 9 | Tests | Rust unit tests, JSON conformance vectors for rules and classifier, port of the 144 tests through the FFI | 2,500 mixed | 4–5 |
| 10 | Release and verification | live run with the profiler, notebook re-run, docs, PyPI pipeline | 0 | 3 |

Total: 33–40 engineer-days for someone fluent in Rust and UniFFI; add a third to a half for a first
UniFFI project. At the assisted pace of the Python first cut (about four working days of wall time)
expect two to three weeks. The core is roughly 2.5x the Python first cut.

Transfers untouched: respx-style end-to-end tests, testing fakes, examples and notebook, guide text,
profiler. Transfers as vectors: the pure rule tests and classifier tests. Disappears: the sync stub
generator and the private-loop sync twin (UniFFI generates both faces). Stays in Python: HTTP/2,
keep-alive, proxies, TLS.

The Python user gains nothing visible (same API; the profiler showed the client at 0% of wall time).
The payoff arrives with the second language: TypeScript via wasm-bindgen is another 8–10 days, Go via
the community generator 6–8 days plus the version-lag risk.

Cheaper first step: a **rules-only core** (pre-flight rules, classifier, breaker state machine, money
and pricing parsing) called synchronously from Python. About 1,500 Rust lines, 10–12 days, almost no
FFI risk, and it already gives TypeScript and Go the parts that must not drift.

Risks setting the range: foreign async trait cancellation is by convention in UniFFI; decimal fidelity
between rust_decimal and Python's Decimal in snapshots and budget maths; pydantic wrappers double every
model and need a drift test like `gen_sync_stub.py`; the wheel matrix is a new CI surface.

### Same estimate as complexity, assuming an agent writes and a person reviews

The cost moves from typing to iterations and to review that no test can replace. Each package rated
on both, with the oracle that decides which it is.

| Package | Agent work | Human review | Oracle |
|---|---|---|---|
| Workspace and wheel matrix | Medium | High | CI green on every platform |
| Domain types | Low | Low | serde round-trips, existing fixtures |
| Transport trait | High | High | none built in (cancellation, timeouts, GIL, who frees what) |
| Protocol clients | Low | Medium | respx tests; renewal lock under 401 storms needs a reader |
| Search pipeline | Medium | Low | conformance vectors plus the 144 tests |
| Sources and wallets | Low | Low | existing tests |
| Snapshots | Low | Medium | byte-identical dumps from the Python SDK |
| Python skin | Medium | High | type checker plus a drift test like `gen_sync_stub.py` |
| Tests and vectors | Medium | Medium | the Python suite itself |
| Release and live verification | Low | Medium | profiler baseline, notebook |

Most human attention goes to three places: the transport trait, the wheel matrix, and the skin's
ergonomics. Everything else has an oracle. Order that minimizes review: vectors first (while the
Python rules are fresh), then types and the search pipeline against them, then the transport trait as
its own small reviewed design, then protocol clients, sources, wallets and snapshots against the
existing tests, then the skin with its drift test, packaging last. The rules-only core skips the two
hardest review items, which is why it remains the cheap first step.

### Later bindings: TypeScript and Go (2026-10-13)

Assumes the core exists with transport outside. Reference sizes of the hand-written SDKs today: about
6,800 lines of TypeScript and 20,900 of Go (mostly generated client code).

**TypeScript via wasm-bindgen**, the only path that covers Node 18+ and the browser with one build.

| Package | Agent work | Human review | Oracle |
|---|---|---|---|
| wasm build target and JS glue | Low | Medium | core tests under Node via wasm |
| Transport as a `fetch` shim | Low | Medium | respx-style tests ported to nock or msw |
| Async surface (Promises from Rust futures) | Low | Low | wasm-bindgen-futures |
| Types and skin over generated records | Medium | Medium | generated `.d.ts` plus a drift test |
| Money without a native decimal | Low | High | none; strings across, JS number type is a review decision |
| Packaging: wasm inlined or as asset, Vite and Next | Medium | High | one sample app per bundler |
| Tests and docs | Medium | Low | conformance vectors |

About three quarters of the Python skin's work. High review: bundle handling, decimals.

**Go via NordSecurity uniffi-bindgen-go.**

| Package | Agent work | Human review | Oracle |
|---|---|---|---|
| Generator pinning (targets UniFFI 0.25; upstream 0.32) | Medium | High | none; pin the core or fork the generator |
| cgo linkage, prebuilt static libs per OS/arch; consumers need CGO_ENABLED=1 | Medium | High | one build per platform |
| Transport as a Go callback | High | High | callback interfaces exist; foreign ASYNC traits unconfirmed for Go |
| context cancellation to Rust futures | Medium | High | none built in |
| Structs and skin | Low | Low | generated types |
| Tests and docs | Medium | Low | conformance vectors |

About one and a half times the Python skin before the transport question. If foreign async traits are
not reachable from Go, Go needs transport INSIDE the core (reqwest linked in), which is a design fork
for the whole core. Verify with a throwaway crate before committing to the core. Pure-Go alternative:
run the core as wasm inside wazero (no cgo, no generator, hand-written ABI on the Go side).

TypeScript is the binding that makes the core pay for itself; Go is where the core's assumptions get
tested.
