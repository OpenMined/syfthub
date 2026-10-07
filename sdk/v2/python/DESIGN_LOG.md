# SDK v2 design log

Running notes from the design sessions on 2026-09-29 and 2026-09-30. The mock in this directory is the current state of
the UX; this file records why it looks the way it does and what is still open. Update it as decisions change.

## Where we started

A survey of the three existing SDKs (`sdk/python`, `sdk/typescript`, `sdk/golang`) found:

- Three hand-written clients kept at parity by review; no code generation anywhere. Same resource layout, same
  Aggregator-centric chat flow: the client mints tokens, posts one request to the Aggregator, the Aggregator fans out to the
  Spaces, reranks, prompts the model and returns one answer.
- The SDKs were behind the backend. `client.accounting` in Python and Go called routes removed in March 2026 when MPP
  replaced the accounting service. No SDK sent `satellite_id`, which the multi-host work now expects. Whole backend groups
  (collectives, wallet subscriptions, satellites) had no SDK coverage. 45 of 98 backend routes were called by any SDK, 27 by all three.
- The existing guide docs were stale (version 0.1.1, wrong import path, wrong login signature).
- The Go SDK exists to serve the `syft` CLI and the desktop app; `syfthubapi` is a Space server framework, not a client.
  Decision: **skip Go for now, Python first.**

Written during the survey: `docs/guides/sdk-overview.md` (new), small fixes to `docs/guides/python-sdk.md` and
`docs/guides/typescript-sdk.md`, a link in `docs/index.md`. Uncommitted.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **Fan-out happens on the client.** The SDK calls each Space directly, one `POST /api/v1/endpoints/{slug}/query` per source, in parallel. | Transparency: the user sees each Space's raw result before anything is merged. Payment consent lands on the client where the user is. |
| 2 | **Aggregation is optional and additive.** `results.aggregate(model)` hands already-retrieved documents to an Aggregator. | Keeps the client usable with nothing but Spaces. The Aggregator route this needs does not exist yet; its request/response shape in `fake/aggregator.py` is a proposal. |
| 3 | **The Space owns the price.** The client decodes what the Space published to the Hub (`policies[]`: `type` = wallet type, `config.price/unit_type/currency/wallet_id/wallet_owner/bundles/payment_url/credits_url/invoices_url`). | Matches the Space's publish handler exactly. No new Space changes. |
| 4 | **Prepaid is the default rail.** stripe / xendit / cluster (managed wallet). MPP appears once, badged experimental. | MPP is experimental and little used; most paid endpoints are prepaid. |
| 5 | **Wallets are per owner × type × currency**, one wallet can back many endpoints, grouped by `wallet_id` else `credits_url` (as the frontend does). `hub.wallets()`, `hub.wallet(path).top_up(bundle)`. | Stated by the product owner; a top-up funds every endpoint on the wallet, so pending actions are per wallet. |
| 6 | **Compose, then execute.** `hub.search(...)` returns a pre-flight view, nothing sent; `search.execute()` sends. Same for `hub.ask(prompt, models=[...])`. | Anything the client can detect (cost, balances, access lists, budget) is shown and acted on before hitting a server. |
| 7 | **Pre-flight holds sources that will certainly fail** (no credits, access denied, over budget) and shows them as *predicted, not sent*. MPP and health warnings are flagged but sent. Rate limits cannot be predicted. | No wasted round trip or charge. |
| 8 | **Top-up happens in pre-flight**: `search.pending`, `search.top_up(path, bundle=)`, then `execute()` re-checks balances at send time. `results.top_up` + `results.retry()` remain for server-detected shortfalls only. | Corrected after review: the first version only offered top-up post-execute. |
| 9 | **After execute a source is one of three things**: returned, skipped (with a `SkipReason`), or payment required (MPP). | One vocabulary for notebooks and scripts; skipped is a normal end state. |
| 10 | **Results show the cost breakdown on execute**: every payment entry from the `policy_metadata` envelopes, totals per currency, the pre-flight estimate, budget remaining. `results.charges`, `results.cost`. | Requested; the envelope is the authoritative record of a charge. |
| 11 | **Browse is one table** of sources and models with a pricing column and a policies column. Shortlisting: Hub-side `browse(type=, owner=)` and `hub.find(text)` (semantic search route); client-side `.where(...)`, `.matching(text)` (fuzzy), `.pick(...)`, `+`. | Selecting sources was a hassle; the Hub only supports type/owner filters server-side. |
| 12 | **Endpoint detail lists every policy in words**, raw config behind a disclosure. | The raw dict was unreadable. |
| 13 | **One headless core, widgets as a skin.** `connect(url, interactive=True)` renders pending payments with buttons that call the same public methods. | Integrability into chatbots; nothing the widget can do that a script cannot. |
| 14 | **Exceptions only for things the caller cannot act on mid-flow.** Payment states are values on the results. | Same. |
| 15 | **No tunnelling / NATS in v2.** | Not used in SyftHub. |
| 16 | **No streaming.** Spaces accept `stream` but ignore it; the mock Aggregator returns one body. | Contract fact; revisit if the Space team implements it. |
| 17 | **Verbs**: `ask` (not summarize), `search` composes, `execute` sends, `retry`, `proceed`, `skip`, `top_up`, `aggregate`, `chat`. | Debated; `retry` vs `resume` still open. |
| 18 | Mock lives in `sdk/v2/python`; move to its own repo later. Recommendation on record: a separate `syft-sdk` repo with contract tests run in both servers' CI. | The SDK spans two servers; Space contract is the volatile one. syft-space also vendors its own 500-line Hub client that should become a consumer. |

## Session 3 (2026-10-01)

- One **story notebook** replaces the four functional ones: `story.ipynb`, Alice's walkthrough from browse to chat.
- Filters simplified to four fields on the Hub record (`type`, `owner`, `free`, `tag`) plus `matching(text)` and `pick(paths)`.
  `rail` and `min_stars` dropped as confusing.
- **Chat has the same pre-flight as search.** `results.chat(model)` renders price per message, balance, verdict; `chat.pending`,
  `chat.top_up(bundle=)`; `chat.send()` returns a `Reply` that is either an answer with citations and charges or a skipped
  model with the TopUp attached, never an exception. A model is a Space endpoint, so one code path.
- **Payment is checked on both sides**: the client predicts from Hub metadata and wallet balances and holds what it knows
  will fail; the Space's 402/403 is the authority and is handled by the identical path. Decided over client-only or server-only.
- Estimates and totals are per currency (a Rp300 source no longer adds to a USD total).

### Later the same day

- **One search over any endpoint type.** An endpoint's `response_type` decides what a row carries: data sources return
  `references`, models a `summary`, `model_data_source` both. The results table has a *returns* column; `results.documents`
  and `results.answers` are the two buckets. `hub.ask(models=)` removed: asking models is a search over model endpoints.
- **"Both" in chat:** documents become `[n]` context and each other endpoint's summary becomes a further numbered item
  labelled as that endpoint's answer, so the chat model can cite either. `results.chat(model, include="references"|"summaries"|"both")`.
- **Metadata filters** `search.where(...)` / `results.where(...)`: `key`, `key_gte/_gt/_lte/_lt`, `key_contains` over
  document metadata. Client-side, because the Space query body has no metadata filter; applies after `limit`, which the
  notebook calls out. Returns a new view; raw responses untouched.

### Context control (2026-10-01, later)

- **Principle:** what a chat sends is a view of results the user can see and reshape with the same verbs as results.
- `Results.only(*paths)`, `.drop(*paths)`, `.top(k)` added beside `.where(**metadata)`; all return views, raw untouched.
- `chat.context` renders exactly what the next message carries (items in citation order, source, score, kind, ~tokens).
  The chat card shows a one-line version next to the payment pre-flight, since context tokens are paid every turn.
- `chat.use(view)` changes the context for later turns; history kept. `chat.where/only/drop/top` are shortcuts.
  For search-each-turn chats the same filters apply to each turn's results and `chat.context` shows the last turn's.
- Decided: **no default cap** on context size; the token estimate is shown instead. No per-message context override and
  no selection by document id yet.

## Session 4 (2026-10-05)

Three gaps named at the start of the session, taken one at a time: (1) the chat never had a real back-and-forth,
(2) filters should also be able to travel *to* the Space, not only shape results afterwards, (3) search after chat,
not only chat after search. This section covers (1).

**Back-and-forth.** The story now has four answered turns on the same chat: a summary, a follow-up that only makes
sense with the first turn ("Were any of them fatal?"), a context swap followed by a question about the new view, then
"Put that in two bullets" which the model answers from its own previous reply rather than from context. What changed:

- `Reply.turn` numbers the answered turns (a skipped, not-sent turn does not count); each reply card says
  "turn n · conversation so far $x".
- `Chat.spent` is the per-currency total over the thread. Search-each-turn chats include that turn's source charges;
  fixed-results chats do not re-count the search they were built on (a `searched` flag on the reply, not identity
  comparison, decides this; identity broke the moment `chat.use(view)` changed the view).
- The chat card's "next message carries" line shows both halves: context tokens and history tokens with the number of
  earlier turns. The thread lists skipped turns too, muted, so a held message is visible in the transcript.
- `Chat.reset()` drops the earlier turns while keeping the view and the pre-flight. Not used in the story, mentioned.
  (`forget` was the first name; `reset` chosen on review.)
- `chat.context` covers both halves of what the next message carries: the earlier turns, then the passages, each with
  its own token count. On review the user's mental model was "history + sources are the context", so the card and the
  `Context` object follow that; the story shows `chat.context` right after `chat.use(view)`.
- The fake model is now scripted over the context it is given: it parses the `[n]` passages from the system message,
  answers the last user message by keyword, cites only passages that exist in the current view, and condenses its own
  previous answer for "shorter/bullets" prompts. The story coda question changed to one the filtered view can answer,
  because the honest model now says "no passage in context reports …" when a filter removed the evidence.

Not changed: no per-message price change (the Space charges per request; history only grows the tokens); no context
cap; no automatic trimming of history.

**Filters that travel to the Space (item 2).** Verb renamed `where` → `filter` everywhere (`Selection`, `Search`,
`Results`, `Chat`); one verb, two homes:

- `search.filter(published_gte=…, author=…)` before `execute()`. For each source the SDK splits the keys: a field the
  Space advertises as filterable goes in the request body and is applied *before* `limit` (only matching documents
  come back and, on a per-document price, only those are billed); anything else is applied here, *after* `limit`.
  The pre-flight table gets a `filters` column saying which home each key gets per source, and warns when a
  per-document source is filtered client-side ("pays for every returned document, matching or not").
- `results.filter(...)` stays a client-side view. `chat.filter(...)` on a search-each-turn chat passes the filter to
  every turn's search, so it travels to the Space where it can.
- Row/`SourceResult` carries `space_filters` (what was sent), `filters` (what stayed here) and `request` (the body
  that went out, kept by the mock for inspection). Cards say "filtered at the Space" vs "N more returned (and
  billed), hidden here".
- **Platform proposal, none of it exists today:** `filterable: [str]` published with the endpoint and exposed on the
  Hub's public record; `filters: {field: {op: value}}` in the query body with ops `eq | gte | gt | lte | lt |
  contains`; `filters_applied` echoed in the response. With no `filterable` advertised the SDK behaves exactly as
  before (client-side). Fakes: carol/papers advertises published/author/journal, erin/trials only published.
- A second notebook, `advanced.ipynb` ("Advanced use cases"), holds this section; the story keeps the client-side
  filter and points at it. Future items that go beyond today's API land there too.

**Search after chat, and a chat as a room (item 3).** Discussed before writing. `chat.search` was dropped: a second
place to search that silently shares the conversation is the kind of hidden difference that confuses; the existing
two verbs already compose (`hub.search(...).execute()` then `chat.use(chat.view + more)`), and sharing the thread
with Spaces stays explicit via `hub.search(..., history=chat.history)`. `switch`, `fork` and `ask(models=[...])`
were considered and dropped once the chat became a room. What was built:

- **A chat is a room.** The pattern every comparison product converges on (Arena side-by-side, OpenRouter rooms,
  AI Studio compare) and that the provider SDKs make trivial because the model is a per-request parameter: user
  turns are shared, assistant turns are per model, each model sees only its own earlier answers.
  `results.chat(model_or_models)` and `hub.chat(model_or_models, sources=…)`; the pre-flight is one row per model.
- `chat.add(model, brief=True)`: joins from the next turn; by default briefed with the lead tab's transcript
  (questions so far + that model's answers, labelled as such in a system line), `brief=False` gives only passages.
  `chat.remove(model)`: stops being asked, tab stays readable with "left at turn n". A held model (no credits) gets
  a skipped reply with its top-up; the others answer. No `switch`: it is remove + add.
- `send` returns `Replies`: indexable by model path or position, `.text/.citations` pass through when there is one
  model and raise naming the tabs otherwise, `.ok` = any answered, `.cost` = this turn (models + that turn's search
  if any). `chat.spent` is the room total; `chat.spent_by(path)` per tab.
- Rendering: CSS-only tabs (radio trick, no JS, same in headless HTML). Chat card = shared header (context line,
  spend) + one tab per model (price, balance, verdict, joined/left/briefed, transcript, top-up). Replies card =
  the question once, answers in tabs. Context card = passages shared, transcripts in tabs.
- `Results + Results` (union of rows, later wins on a shared source; filters and estimates merged) and `chat.view`.
- Story: after the slide bullets Alice adds Bob (free) for a second opinion, removes Ivan, pulls in the consortium
  corpus with a plain `hub.search`, folds it in with `chat.use(chat.view + more)` and asks again. Advanced §2: a
  two-model room from the start with one model held, then the top-up so both answer, `add` of a third model billed in IDR
  (lena/sahabat-ai, added to the fakes, same wallet as her registry), `remove`, and `spent` / `spent_by`. Spend is
  always per currency: models sit behind different wallets and the SDK never converts.

## The API as it stands

Defined in `LOW_LEVEL_DESIGN.md` (section 4) and implemented by the mock. In one screen:

```python
async with syfthub.AsyncHub() as hub:                 # async-first; syfthub.Hub is the generated sync twin
    await hub.login(token=...)                        # the one top-level alias; hub.auth has the full set
    eps = await hub.endpoints.list()                  # hub.endpoints.search / get / pages
    plan = hub.search(q, sources=eps.pick(...))       # sync, free; await plan.preflight(); await plan.execute()
    invoice = await plan.top_up("dave/notes", "starter"); await invoice.wait_paid()
    results = await plan.execute()                    # immutable; filter/only/drop/top/+ are views, retry/approve/skip return new
    chat = results.chat(model); await chat.send(...)  # the one mutable object; fork() branches
    await results.aggregate(model) / await hub.aggregate(q, sources=, model=)   # both Aggregator forms
```

## Space and Hub contract facts the design relies on

- Space query: single route, one JSON body, `Authorization: Bearer <satellite token>` bound to the Space URL, optional
  `X-Payment`, `X-Tenant-Name` only with multi-tenancy. Body: `messages`, `limit`, `similarity_threshold`, `max_tokens`, …
  Response: `summary`, `references.documents[]{document_id, content, similarity_score, metadata}`, `cost`, `currency`,
  `policy_metadata{outcome, entries[]}`.
- 402 + `WWW-Authenticate` only for MPP; retry with `X-Payment`. Everything else a policy blocks is 403 with the envelope:
  branch on `reason_code` (`INSUFFICIENT_BALANCE`, `RATE_LIMITED`, `ACCESS_DENIED`, `NO_PRICING_TIER`). Rate limit is 403,
  no `Retry-After`; `reset_seconds` is in `details`. MPP with no matching tier returns 403 with no entry (unclassifiable).
- Prepaid credits: `POST .../wallets/{id}/invoices {bundle_name}` → `InvoiceResponse` with `checkout_url`;
  `GET .../wallets/{id}/balance`. Same suffixes on a station for managed wallets. Balance is credited by the provider webhook.
- Space has no public discovery/manifest route; pricing is only in what it publishes to the Hub.
- Space CORS does not expose `WWW-Authenticate`: browser MPP is impossible until changed (irrelevant for Python).
- Space docs vs code drift: `score` → `similarity_score`; insufficient balance is 403 not 402; cluster rail undocumented; `stream` unused.
- Hub: `GET /api/v1/token?owner_username=&resource=` mints a satellite token; `POST /api/v1/wallet/pay` settles an MPP challenge.
  Public listing supports `endpoint_type` and by-owner filters; `POST /endpoints/search` is semantic search.

## Open questions

1. `retry` vs `resume`; any other verb changes after using the notebooks.
2. Should `execute()` yield results as sources land instead of returning once?
3. Budget scope: per `hub` session (current), per run, or persisted on the Hub?
4. Headless contract for prepaid top-ups: today the SDK returns `checkout_url` and stops; should it poll the balance?
5. `results.ask()` prompt format: mirror the Aggregator's citation prompt, or keep the plain numbered context?
6. The Aggregator route: who owns it, and does it take billing receipts along with documents?
7. MPP-with-no-tier returns an unclassifiable 403: fix on the Space, or accept a generic `blocked`.
8. Where the real SDK lives (`syft-sdk` repo recommended), and replacing syft-space's vendored Hub client with it.
9. Async-first core and JSON-serialisable results for chatbot integrations (both noted, not in the mock).

## Session 5 (2026-10-07)

- Reviewed the mock against three SDK-design references (the Stripe/Twilio time-to-hello-world piece, Pragmatic
  Engineer's *Building great SDKs*, sdks.io best practices). Findings: naming (four look-up verbs, three go-ahead verbs,
  a monolithic `Hub`), strings where enums belong, no transport contract, a thin error hierarchy, UI imported by the core.
- **Async-first decided** (both servers are async). Wrote `LOW_LEVEL_DESIGN.md`: eleven decisions taken, one open
  (Aggregator fan-out location).
- **Rebuilt the mock to the design.** `AsyncHub` with `hub.auth` / `hub.endpoints` / `hub.wallets`; `SearchPlan` composed
  synchronously, `preflight()` and `execute()` awaited; immutable `Results`; mutable `Chat` with `fork()`, serialised sends
  and snapshot `Replies`; `Outcome` split into returned / held / rejected / failed / payment_required with one `Reason`
  enum; `Money` (Decimal + currency); pydantic v2 models; one `Options` object (timeouts, `Retry` with jitter and a
  rate-limit wait, per-Space `CircuitBreaker`, concurrency, injectable transport); `TokenCache`; auto-pagination;
  `logging` under `syfthub`; `to_dict()`; the error hierarchy; `syfthub.testing.MockTransport` + `World` as the
  offline doubles; `syfthub.notebook` as the optional skin; a runtime proxy standing in for the `unasync` twin.
- Pre-flight now sums estimates **per wallet**, so two sources on one wallet cannot both pass on a balance that covers one.
- The Aggregator fake implements **both** forms: documents supplied, and sources supplied with payment forwarding
  (`Answer.pending`, `job_id`, `resume()`, `approve()` for forwarded MPP charges).
- `flows.ipynb` added: one section per user flow. `story.ipynb` and `advanced.ipynb` translated to the new API. The
  reference regenerated by namespace with `await` shown on async members.

## Files

- `LOW_LEVEL_DESIGN.md`: every functionality, its name and syntax; the decisions table; the one open question.
- `syfthub/` the proposed API (hub, auth, endpoints, wallets, search, results, chat, aggregator, models, errors,
  `_transport`, `_sync`), `syfthub/notebook/` the optional skin, `syfthub/testing/` the fakes behind `MockTransport`.
- `flows.ipynb` (one section per user flow), `story.ipynb` (Alice's walkthrough) and `advanced.ipynb` (beyond today's
  API), all executed; `build_notebooks.py` regenerates them.
- `README.md` maps every fake to the real route and lists simplifications.
- `docs/index.html`, the generated SDK reference. Text comes from Google-style docstrings (summary, Args, Returns, Raises, Attributes) so `help()` and the page agree; every public member has an example; `build_docs.py` regenerates it and lists any member without one.
