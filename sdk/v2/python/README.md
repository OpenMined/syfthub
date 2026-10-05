# SyftHub SDK v2 — UX mock

A design prototype for the next Python SDK. **Nothing talks to a real server.** `syfthub/` is the proposed public API;
`syfthub/fake/` are in-memory stand-ins that return exactly the shapes the real Hub and Space APIs return. Endpoints,
prices, balances and documents are invented. Response bodies are not.

## The notebook

**`story.ipynb` (and `advanced.ipynb` for the parts beyond today's Space API)**: Alice browses, narrows with a fuzzy match, composes a search and sees the cost and her wallet balances
before anything is sent, tops up the one wallet that is short, executes, reads what each Space returned and what it
charged, then opens a chat with a metered model that goes through the same pre-flight. One story, start to finish.

```bash
cd sdk/v2/python
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -e ".[notebook]"
.venv/bin/python build_notebooks.py          # regenerates and executes story.ipynb
```

## Reference

`docs/index.html` is the SDK reference: every class, field, property and method, each with a plain-English
description, a parameter table and a short example. The text comes from the Google-style docstrings in the package
(summary, Args, Returns, Raises, Attributes), so `help(obj)` and the page say the same thing; only the examples live
in `build_docs.py`. Open it in a browser; regenerate after changing the code or a docstring:

```sh
.venv/bin/python build_docs.py
```

## The API

```python
hub = syfthub.connect(url, interactive=False)
hub.login(username=, password=)  |  hub.login.google()  |  hub.login.token(pat)
hub.browse()                      # sources and models in one table, pricing column
hub.browse(type=, owner=, free=, tag=, matching=)                 # four exact filters + a fuzzy match
hub.browse().matching("trial adverse events").filter(type="data_source") + hub.browse().pick("dave/notes")
hub.find("clinical notes")        # Hub-side semantic search over listings (POST /endpoints/search)
hub.get("owner/slug")             # detail card: every policy with its published config
hub.wallets()                     # your prepaid balances, one row per wallet (owner × type × currency), with the endpoints each backs
hub.wallet("owner/slug").top_up("starter")   # pre-fund the wallet behind an endpoint -> InvoiceResponse with checkout_url

search = hub.search(query, sources=[...], limit=5)     # any endpoint type; pre-flight: max cost, balances, access, budget. Nothing sent.
search.filter(published_gte="2024-01-01", author_contains="chitrakoot")  # metadata filters: sent to Spaces that advertise the field (before limit), applied here otherwise (after limit)
search.filters_for(row)           # (sent to the Space, applied here) per source; the pre-flight table shows it
results = search.execute()        # client-side fan-out; one POST per Space. Each row returns references, a summary, or both.
results.filter(...) / .only(*paths) / .drop(*paths) / .top(k)  # views over the returned documents; raw untouched
results.documents / results.answers / results.returns
results["owner/slug"]             # documents, summary, cost, policy_metadata; .raw is the exact body
results.pending                   # one TopUp per wallet (prepaid, 403 INSUFFICIENT_BALANCE)  or  Charge per source (MPP 402, experimental)
results.top_up(path, bundle=)     # invoice on the Space -> checkout_url; funds every waiting source on that wallet.  results.retry() after paying
results.approve(path)             # MPP only                                     results.skip(path)
results.proceed()                 # send sources pre-flight held for budget, ignoring the cap this once

results.charges / results.cost    # every payment entry from the policy envelopes, flattened; totals per currency
hub.search(prompt, sources=[models...]).execute().answers   # asking several models is just a search over model endpoints
results.aggregate(model)          # via an Aggregator (route to be built)
chat = results.chat(model_or_models, include="both")   # a room: shared questions, one transcript per model; pre-flight per model
chat.context                      # what the next message carries: earlier turns (per model) + passages, each half with ~tokens
chat.use(results.only("erin/trials").top(3))   # change the view for later turns; turns kept. Also chat.filter/only/drop/top
chat.use(chat.view + more)        # fold a later hub.search(...).execute() into the running chat (Results + Results)
replies = chat.send(prompt)       # one Reply per active model, indexable: replies["bob/llama-3"]; .text passes through when one model
replies[0].turn; chat.spent       # shared turn number; the room's total per currency, never converted (chat.spent_by(path) per model)
chat.add(model, brief=True)       # joins from the next turn; briefed with the lead model's transcript unless brief=False
chat.remove(model)                # stops being asked; its tab stays readable
chat.reset()                      # drop every model's earlier turns; the passages view and the pre-flights stay
hub.chat(model_or_models, sources=[...]).filter(...).top(k)  # search each turn; the filter travels with each turn's search
```

## Pre-flight: what the client decides before sending

From Hub metadata, one balance call per prepaid wallet, and the session budget:

| Detected | Action |
|---|---|
| Estimated max cost per source and total | shown |
| Prepaid wallet balance below the estimate | **held** as `insufficient_balance` with a `TopUp`; `retry()` after paying |
| Access allow/deny lists exclude your email | **held** as `access_denied` |
| Total estimate exceeds the session budget | **held** as `over_budget`; `proceed()` or raise the budget |
| MPP source | flagged "will ask to pay"; sent (only the Space issues the challenge) |
| Last health check failed | flagged; sent |
| Rate limits | shown; cannot be predicted (counters live on the server) |

## Fidelity

| Real thing | In the mock |
|---|---|
| Hub `EndpointPublicResponse` | `Endpoint`: name, slug, type, owner_username, description, version, tags, stars_count, policies[], connect[] |
| Published payment policy (`type` = wallet type, `config.price/unit_type/currency/wallet_id/wallet_owner/bundles/payment_url/credits_url/invoices_url`) | `Policy`; `Pricing` is read off it, nothing added |
| Wallets: unique per owner × type × currency; many endpoints per wallet; grouped by `wallet_id` else `credits_url` (as the frontend does) | `Wallet`, `hub.wallets()` |
| `GET /api/v1/token?owner_username=&resource=` | `FakeHub.satellite_token` |
| `POST {space}/api/v1/endpoints/{slug}/query` → `summary`, `references.documents[]`, `cost`, `currency`, `policy_metadata{outcome, entries[]}`; 402 + `WWW-Authenticate` (MPP); 403 + envelope (prepaid, access, rate limit) | `FakeSpace.query`, kept whole under `SourceResult.raw` |
| `POST .../wallets/{id}/invoices` → `InvoiceResponse` with `checkout_url`; `GET .../balance` | `FakeSpace.create_invoice`, `balance` (same suffixes for station-hosted wallets) |
| `POST /api/v1/wallet/pay` → `x_payment` | `FakeHub.wallet_pay` |
| Aggregator route taking pre-retrieved documents | **does not exist**; `FakeAggregator.aggregate` is the proposal |
| The user paying at checkout + provider webhook | `hub._simulate_checkout_paid(invoice_id)` |

Simplifications: synchronous core with a thread pool (real SDK should be async-first); no token streaming anywhere
(Spaces do not stream today); `ask()` uses a plain numbered-context prompt.

## Open

Verbs (`ask` chosen over `summarize`; `search` composes, `execute` sends; `retry` vs `resume`), whether `execute()` should
yield as sources land, budget scope, and the headless contract for prepaid top-ups (`checkout_url` returned, caller polls).
