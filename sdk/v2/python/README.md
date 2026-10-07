# SyftHub SDK v2 — UX mock

A design prototype for the next Python SDK. **Nothing talks to a real server.** `syfthub/` is the proposed public API,
implemented against `syfthub/testing/`: in-memory fakes that return exactly the shapes the real Hub and Space APIs
return. Endpoints, prices, balances and documents are invented. Response bodies are not.

The API follows `LOW_LEVEL_DESIGN.md`; `DESIGN_LOG.md` records why it looks the way it does.

## The notebooks

- **`flows.ipynb`**: one section per user flow. Hello world, sign in, discovery, wallets, compose → pre-flight → execute,
  failures and retries, the circuit breaker, budgets, headless use with `wait_paid()`, the chat room, several models,
  search-per-turn, MPP, both Aggregator forms, errors, the sync twin.
- **`story.ipynb`**: Alice's walkthrough, start to finish.
- **`advanced.ipynb`**: the parts beyond today's Space API (filters that travel to the Space; a room of models).

```bash
cd sdk/v2/python
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[notebook]"
.venv/bin/python build_notebooks.py          # regenerates and executes all three (or: flows / story / advanced)
```

## Reference

`docs/index.html` is the SDK reference: every class, field, property and method, each with a plain-English description, a
parameter table and a short example. The text comes from the Google-style docstrings in the package, so `help(obj)` and
the page say the same thing; only the examples live in `build_docs.py`. Async methods are shown with `await`.

```sh
.venv/bin/python build_docs.py
```

## The API

```python
import syfthub
async with syfthub.AsyncHub() as hub:                         # SYFTHUB_URL, SYFTHUB_TOKEN; Options(...) tunes the whole client
    await hub.login(username=, password=)  |  await hub.login(token=)  |  hub.auth.login_with_google()
    hub.me ; await hub.auth.whoami() ; hub.set_budget(2.00)

    eps = await hub.endpoints.list(type=, owner=, free=, tag=, matching=)   # pages followed; EndpointList
    eps.matching("trial adverse events").filter(type="data_source") + eps.pick("dave/notes")
    await hub.endpoints.search("clinical notes") ; await hub.endpoints.get("owner/slug") ; hub.endpoints.pages()

    await hub.wallets.list() ; await hub.wallets.for_endpoint("owner/slug") ; await wallet.top_up("starter") -> Invoice

    plan = hub.search(query, sources=[...], limit=5)          # sync, free; sources=None -> free data sources
    plan = plan.filter(published_gte="2024-01-01")            # to the Space where it advertises the field, else local
    await plan.preflight()                                    # estimates, balances, holds; nothing sent
    invoice = await plan.top_up("dave/notes", "starter") ; await invoice.wait_paid()
    results = await plan.execute(ignore_budget=False)         # one POST per Space, in parallel

    results["owner/slug"] .documents .summary .cost .charges .rate_limit .raw
    results.filter(...) / .only(...) / .drop(...) / .top(k) / results + more      # views: new Results, raw untouched
    results.pending ; await results.top_up(path, "starter") ; await results.retry(*paths, ignore_budget=)
    await results.approve(*paths) ; results.skip(*paths) ; results.to_dict() ; Results.from_dict(hub, d)

    chat = results.chat(models, include=) ; live = hub.chat(models, sources=[...], via=)
    await chat.preflight() ; chat.context ; replies = await chat.send(prompt) ; replies["bob/llama-3"].text
    await chat.add(model) ; await chat.remove(model) ; chat.fork() ; chat.use(view) ; chat.reset() ; chat.spent

    await results.ask(model) ; await results.aggregate(model) ; await hub.aggregate(query, sources=, model=)

with syfthub.Hub() as hub: ...                                # the synchronous twin, same methods, no await
```

## Pre-flight: what the client decides before sending

From Hub metadata, one balance call per prepaid wallet (summed per wallet), the circuit breakers and the session budget:

| Detected | Action |
|---|---|
| Estimated max cost per source and total | shown |
| Prepaid wallet balance below the estimates on it | **held** `needs_credits` with a `TopUp`; buy, pay, `execute()` or `retry()` |
| Access allow/deny lists exclude your email | **held** `access_denied` |
| Total estimate exceeds the session budget | **held** `over_budget`; `execute(ignore_budget=True)` or raise the budget |
| The Space's circuit breaker is open | **held** `circuit_open` |
| MPP source | flagged *will ask to pay*; sent (only the Space issues the challenge) |
| Last health check failed | flagged; sent |
| Rate limits | shown; cannot be predicted. Short resets are waited out inside the call (`Retry.rate_limit_wait`) |

## Outcomes

| Outcome | Who stopped it | Reasons |
|---|---|---|
| `returned` | nobody | |
| `held` | pre-flight, nothing spent | `no_credits`, `over_budget`, `access_denied`, `circuit_open`, `by_user` |
| `rejected` | the Space's policy (403) | `no_credits`, `rate_limited`, `access_denied`, `no_pricing_tier`, `blocked` |
| `failed` | transport or server, after retries | `unreachable`, `timeout`, `server_error`, `not_found`, `auth` |
| `payment_required` | an MPP Space (402) | `Charge` attached; `approve()` |

## Fidelity

| Real thing | In the mock |
|---|---|
| Hub `EndpointPublicResponse` | `Endpoint`: name, slug, type, owner_username, description, version, tags, stars_count, policies[], connect[], health |
| Published payment policy (`type` = wallet type, `config.price/unit_type/currency/wallet_id/wallet_owner/bundles/payment_url/credits_url/invoices_url`) | `Policy`; `Pricing` is read off it, nothing added |
| Wallets: unique per owner × type × currency; many endpoints per wallet; grouped by `wallet_id` else `credits_url` | `Wallet`, `hub.wallets` |
| `GET /api/v1/token?owner_username=&resource=` | `FakeHub.satellite_token`; cached and refreshed by `TokenCache` |
| Paged `GET /api/v1/endpoints`, `POST /endpoints/search` | `FakeHub.list` (paged), `FakeHub.search` |
| `POST {space}/api/v1/endpoints/{slug}/query` → `summary`, `references.documents[]`, `cost`, `currency`, `policy_metadata{outcome, entries[]}`; 402 + `WWW-Authenticate` (MPP); 403 + envelope (prepaid, access, rate limit) | `FakeSpace.query`, kept whole under `SourceResult.raw` |
| `POST .../wallets/{id}/invoices` → `InvoiceResponse` with `checkout_url`; `GET .../balance` | `FakeSpace.create_invoice`, `balance` (same suffixes for station-hosted wallets) |
| `POST /api/v1/wallet/pay` → `x_payment` | `FakeHub.wallet_pay` |
| Aggregator route | **does not exist**; `FakeAggregator` is the proposal, in both forms (documents supplied / sources supplied with payment forwarding) |
| The user paying at checkout + provider webhook | `world.pay(invoice)` |
| A Space going offline | `world.space_down(path)` / `world.space_up(path)` |
| Time | `world.now`, advanced by the SDK's sleeps at 100× (rate-limit windows, breaker cooldowns, `wait_paid` polling) |

Simplifications: the synchronous `Hub` is a runtime proxy here and a generated package in the real SDK; the generated
low-level clients (`syfthub._api`) do not exist in the mock, `MockTransport` sits where they would; no token streaming
(out of scope for v2); `ask()` uses a plain numbered-context prompt; `Via.AGGREGATOR` on a chat is accepted but routes direct.

## Open

Which side the Aggregator fans out on (`LOW_LEVEL_DESIGN.md`, open decision A). Everything else in the design is decided.
