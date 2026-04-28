# SDK Simplify Backlog

Deferred findings from a simplify-skill review of `sdk/python/`, `sdk/typescript/`, and `sdk/golang/syfthub/`. Each entry is self-contained: paths, current state, target state, and gotchas. Hand any single entry (or a group) to a fresh simplify agent and it can execute without re-discovering context.

Conventions:
- All paths are relative to repo root `/home/junior/workspace/syfthub`.
- "Call sites" counts assume the current state of `main` (HEAD `52407c4`).
- Run `gitnexus_impact({target: "symbol", direction: "upstream"})` before modifying any exported symbol, per the repo's `CLAUDE.md`.

---

## Task 1 — Python: collapse `AccountingResource._request` / `_request_with_token`

**Files:** `sdk/python/src/syfthub_sdk/accounting.py`

**Current state:** Two private methods implement the same request lifecycle:
- `_request` (~L146-182): serializes JSON, uses the Basic-auth client from `_get_client()`, handles 204, runs `_handle_response_error`, wraps `httpx.RequestError` in `APIError`.
- `_request_with_token` (~L184-223): identical body except it opens a fresh `httpx.Client()` each call and sets `Authorization: Bearer <token>` in headers.

The only real differences are (a) auth mechanism and (b) the bearer path creates a new client per call.

**Target state:** A single `_request(method, path, *, json=None, token=None)` method. When `token` is `None`, use the cached Basic-auth client (`self._get_client()`); when `token` is provided, reuse the same cached client but pass `headers={"Authorization": f"Bearer {token}"}`. Delete `_request_with_token`; update its call sites (grep `_request_with_token(`).

**Gotchas:**
- Do not open a new `httpx.Client` in the bearer path — that is one of the efficiency bugs this consolidates away.
- `_get_client()` currently sets Basic auth on the client itself. Per-request `headers=` will override the `Authorization` header for that call — confirm with a unit test (tests live in `sdk/python/tests/`).
- Keep `_handle_response_error` and the 204 short-circuit identical in behavior.

---

## Task 2 — Python: dedupe `syftai.py` URL + error extraction + fetch scaffolding

**Files:** `sdk/python/src/syfthub_sdk/syftai.py`

**Current state:** The same three-part pattern appears three times (at L149, L238, L320 for URL build; L172-178, L263-270, L344-350 for error extraction; and the `httpx.RequestError` → `GenerationError`/`RetrievalError` wrap four times):
```python
url = f"{endpoint.url.rstrip('/')}/api/v1/endpoints/{endpoint.slug}/query"
# ...
error_message = error_data.get("detail", error_data.get("message", f"HTTP {status}"))
# ...
except httpx.RequestError as e:
    raise RetrievalError(...)  # or GenerationError
```

**Target state:** Three private helpers on `SyftAIResource`:
- `_endpoint_query_url(endpoint: EndpointPublic) -> str`
- `_extract_error_message(response: httpx.Response) -> str` — reads body, handles non-JSON, returns the detail/message/HTTP-status fallback.
- `_post_endpoint(endpoint, body, *, error_cls) -> httpx.Response` — wraps the POST + connect-error mapping; raises `error_cls` with the extracted message.

Replace the three call sites with these helpers.

**Gotchas:**
- `error_cls` must be one of `RetrievalError` / `GenerationError`; preserve the current argument signatures passed to those exceptions at each site (e.g. `source_path`, `model_slug`).
- Streaming call site (around L320 if present) uses a different response-handling path — keep the URL helper but do not force the fetch helper on it.

---

## Task 3 — Python: unclosed `httpx.Client` instances in `ChatResource` and `SyftAIResource`

**Files:** `sdk/python/src/syfthub_sdk/chat.py` (client created ~L243), `sdk/python/src/syfthub_sdk/syftai.py` (client created ~L99), `sdk/python/src/syfthub_sdk/client.py` (`SyftHubClient.close` at ~L339).

**Current state:** Both resources instantiate their own `httpx.Client(timeout=...)` in `__init__` and never register them with the parent `SyftHubClient.close()` — which currently only closes `self._http` and `self._accounting`. On client teardown, both connection pools leak.

**Target state:** Either (a) register both clients in `SyftHubClient.close()` so it closes them in addition to `_http` and `_accounting`, or (b) have both resources accept the main `HTTPClient`'s underlying `httpx.Client` via constructor and drop their own instances.

**Gotchas:**
- Timeouts differ: chat uses 120s, syftai uses 60s. If sharing a client, use `httpx.Client(timeout=None)` and pass per-request `timeout=` on each call.
- `SyftHubClient.close()` is the public teardown API; preserve its current idempotency behavior.

---

## Task 4 — Python: parallelize `auth.get_satellite_tokens` / `get_guest_satellite_tokens`

**Files:** `sdk/python/src/syfthub_sdk/auth.py`

**Current state:** Two methods (~L407-505) have nearly identical ThreadPoolExecutor plumbing, differing only in whether they call `get_satellite_token` or `get_guest_satellite_token` per audience. ~50 lines duplicated.

**Target state:** A private `_parallel_fetch(audiences: list[str], fetch_fn: Callable[[str], str]) -> dict[str, str]` that owns the executor, dedup, and error aggregation. Both public methods become one-liners that pass `self.get_satellite_token` or `self.get_guest_satellite_token`.

**Gotchas:**
- Preserve the current return shape (dict of audience → token, errors surface in existing style).
- Keep `max_workers` and any existing timeouts unchanged.

---

## Task 5 — TypeScript: shared SSE reader

**Files:** `sdk/typescript/src/resources/chat.ts` (~L570-615), `sdk/typescript/src/resources/syftai.ts` (~L256-305); new file `sdk/typescript/src/utils/sse.ts` (or extend existing `utils.ts`).

**Current state:** Both files contain the same loop: `body.getReader()`, `TextDecoder`, `buffer.split('\n')`, `buffer.pop()`, test for `event:` / `data:` prefixes, slice `5` / `6` chars.

**Target state:** Export an async generator:
```ts
export async function* readSSEEvents(response: Response): AsyncGenerator<{ event: string; data: string }>
```
Both call sites consume it with `for await (const { event, data } of readSSEEvents(response))` and only supply their event-specific switch.

**Gotchas:**
- The current parsers tolerate missing `event:` lines (fall back to `"message"`); preserve that.
- Trailing buffer flush on stream end must be preserved — both sites currently process any residual line after `reader` is done.
- Don't eagerly JSON.parse inside the generator; leave parsing to the consumer (each site parses a different schema).

---

## Task 6 — TypeScript: memoize case-conversion regex work

**Files:** `sdk/typescript/src/utils.ts` (~L43-80 for `toCamelCase`/`toSnakeCase`, ~L106 for `buildSearchParams`), used by `sdk/typescript/src/http.ts` (~L222, L299).

**Current state:** Every request and response runs `toCamelCase`/`toSnakeCase` over the whole payload recursively; each key triggers a regex replacement. `buildSearchParams` re-runs `camelToSnake` for every param on every GET. For large list responses (e.g., hub browse, API tokens) this dominates CPU.

**Target state:** Wrap the inner `snakeToCamel(key)` / `camelToSnake(key)` helpers with a module-level `Map<string, string>` cache. Keys repeat across requests — a single cache entry is paid once per distinct key name for the process lifetime.

**Gotchas:**
- Do not cache the whole-object conversion result, only the per-key regex output.
- Keep the ISO date detection path untouched — it applies to values, not keys.
- Cache bound: these key-sets are small (tens, maybe low hundreds); unbounded `Map` is acceptable, but feel free to add a comment explaining why.

---

## Task 7 — TypeScript: fix bottom-of-file import with misleading comment

**Files:** `sdk/typescript/src/http.ts` (~L476).

**Current state:** `import { SyftHubError } from './errors.js';` sits after the class declaration with a comment implying a circular-import workaround. `errors.ts` does not import `http.ts`, so there is no cycle.

**Target state:** Move the import to the top of the file with the others; remove the comment.

**Gotchas:**
- Verify by grep: `grep -n "from '.*http" sdk/typescript/src/errors.ts` should return nothing. If it does, the cycle is real and the fix changes.

---

## Task 8 — Go: `buildRequestBody` parameter sprawl

**Files:** `sdk/golang/syfthub/chat.go` (~L521-534, declaration; ~L191, call site).

**Current state:** 13 positional parameters — mix of `*ChatCompleteRequest` fields and token bundles. Call site is unreadable.

**Target state:** Accept `(req *ChatCompleteRequest, prepared *chatPrepared)` or introduce a `type tokensBundle struct { satellite map[string]string; transaction map[string]string; peer string }` and pass `(req, tokens, stream)`. Move any default-injection (`TopK == 0` → 5, etc.) out of the body-builder and into `prepareRequest`, leaving `buildRequestBody` as a pure serializer.

**Gotchas:**
- `prepareRequest` currently mutates `req.TopK` etc. when zero (see Task 12 — fix concurrently). Centralize defaults in one place; don't mutate the caller's struct.
- Keep `stream bool` as an explicit argument since the same body shape serves both Complete and Stream.

---

## Task 9 — Go: remove double options loop in `NewClient`

**Files:** `sdk/golang/syfthub/client.go` (~L110-117 first loop, ~L162-166 second loop).

**Current state:** The `ClientOption` slice is applied twice to the client. The second pass re-applies `WithAPIToken` because that option needs `c.http` to exist, which is only true after first-pass construction. A comment acknowledges the hack.

**Target state:** Make options pure data: `WithAPIToken` just stores the token in a field (e.g. `c.apiToken string`). After all options are applied and `c.http` is constructed, call `c.http.SetAPIToken(c.apiToken)` (or similar) once. Delete the second loop and the comment.

**Gotchas:**
- Any future option that needs `c.http` must follow the same "store now, apply after http init" pattern. Document this in a comment on the `Client` struct.
- `WithAPIToken` is part of the public API — preserve its signature; only its internal behavior changes.

---

## Task 10 — Go: collapse `accounting.go request` / `requestWithToken`

**Files:** `sdk/golang/syfthub/accounting.go` (~L77-118 `request`, ~L120-161 `requestWithToken`).

**Current state:** Line-for-line duplicates except `req.SetBasicAuth(...)` vs `req.Header.Set("Authorization", "Bearer "+token)`.

**Target state:** Single method `do(ctx context.Context, method, path string, applyAuth func(*http.Request), body, result interface{}) error`. Callers pass a closure:
- Basic: `func(r *http.Request) { r.SetBasicAuth(a.username, a.password) }`
- Bearer: `func(r *http.Request) { r.Header.Set("Authorization", "Bearer "+token) }`

**Gotchas:**
- Consider deferring this to Task 11 — that task eliminates the problem at a higher level. If Task 11 is done, Task 10 disappears.
- JSON encode/decode, 204 short-circuit, and error-response handling must remain identical.

---

## Task 11 — Go: unify `httpClient` and `basicAuthHTTPClient` via auth strategy

**Files:** `sdk/golang/syfthub/http.go` (~L55-372 `httpClient`; ~L500-612 `basicAuthHTTPClient`), `sdk/golang/syfthub/accounting.go` (whole file uses `basicAuthHTTPClient`).

**Current state:** ~110 lines of `Request`/`Get`/`Post`/`Patch` are duplicated between the two clients, differing only in the auth application step. `accounting.go` then has a third parallel implementation.

**Target state:** Define
```go
type authStrategy interface {
    apply(req *http.Request)
}
type bearerAuth struct{ tokenProvider func() string }
type basicAuth struct{ username, password string }
type noAuth struct{}
```
`httpClient` accepts an `authStrategy` field; `Request()` calls `c.auth.apply(req)` before `c.client.Do(req)`. Delete `basicAuthHTTPClient` entirely; `AccountingResource` uses `httpClient` with `basicAuth{}`.

**Gotchas:**
- The current bearer path uses a `tokenProvider` function because tokens refresh; preserve that, don't pass a static string.
- Error handling in `basicAuthHTTPClient` (the `handleError` variant) is slightly different from `httpClient.handleError` — unify them, preserving the richer message extraction (the one that reads `detail.code` from nested JSON).
- This is a significant refactor; run `gitnexus_impact({target: "basicAuthHTTPClient", direction: "upstream"})` before starting and expect to update all `accounting.go` call sites.

---

## Task 12 — Go: `prepareRequest` mutates caller's `*ChatCompleteRequest`

**Files:** `sdk/golang/syfthub/chat.go` (~L91-102).

**Current state:** When `req.TopK == 0` (and similar zero-value fields), `prepareRequest` writes the default back onto `req`. A caller who reuses the same pointer across calls will see their zero-value second call silently take the defaulted value from the first.

**Target state:** Compute locals: `topK := req.TopK; if topK == 0 { topK = 5 }`. Pass `topK` to the downstream body builder. Do not mutate `*req`.

**Gotchas:**
- Check every zero-value default in `prepareRequest` (there are several — TopK, temperature, etc.) and convert each to a local.
- Update `buildRequestBody` signature to accept the resolved values (overlaps with Task 8).

---

## Execution notes for the agents

- The simplify skill expects each agent to make fixes directly; don't write additional planning documents.
- Run `make check` (Python lint/types), `npm run lint` (TS), and `go build ./...` (Go) after each task.
- Per `CLAUDE.md`, run `gitnexus_impact` before touching any exported symbol; the `Task 1`, `Task 2`, `Task 4`, `Task 8`, `Task 11`, and `Task 12` items touch exported or widely-used code.
- After landing changes: `npx gitnexus analyze` to refresh the index (or `--embeddings` if previously enabled).
