"""Generate and execute the notebooks. Run: .venv/bin/python build_notebooks.py [flows|story|advanced ...]

- flows.ipynb     one section per user flow, in the order a new user meets them
- story.ipynb     Alice's walkthrough, start to finish
- advanced.ipynb  the parts that go beyond today's Space API
"""
import sys
import nbformat as nbf
from nbclient import NotebookClient

md = lambda s: ("md", s)
code = lambda s: ("code", s)

SETUP = """
import syfthub
from syfthub import AsyncHub, Options
from syfthub.testing import World, MockTransport

world = World()                                     # the mock's stand-in for the outside world
hub = AsyncHub(options=Options(http_client=MockTransport(world)))
await hub.login(username="alice", password="secret")
"""

# =============================================================================================== FLOWS
FLOWS = [
md("""
# User flows

*One section per thing a user does with the SyftHub Python SDK, in the order a new user meets them. Everything runs
against in-memory fakes that return exactly the shapes the real Hub and Space APIs return; names, prices and
documents are invented. The API is the one in `LOW_LEVEL_DESIGN.md`.*

The SDK is **async-first**: composing a search or a chat is free and synchronous, anything that touches the network
is awaited. A generated synchronous twin exists for scripts; it appears at the end.
"""),

md("""
## 1. Hello world

Install, construct, search. The Hub URL and a token come from `SYFTHUB_URL` and `SYFTHUB_TOKEN` when they are set.
Without `sources`, the search runs over **free data sources** the Hub ranks for the query, so a first call never costs
anything. Paid endpoints are never included implicitly.
"""),
code("""
import syfthub

hub = syfthub.AsyncHub()                                   # mock: in-memory fakes behind the scenes
results = await hub.search("adverse events in phase 3 trials").execute()
results
"""),
md("Each row is one Space's answer. Rows are typed objects, so the IDE knows what is on them."),
code("""
for path, doc in results.documents[:3]:
    print(f"{path:<16} {doc.similarity_score:.2f}  {doc.content[:70]}")
"""),

md("""
## 2. Sign in

Three ways, all under `hub.auth`. The one top-level alias is `hub.login`, because it is the first thing a new user
types. For the rest of this notebook we use an explicit `World` so we can stand in for the outside world: a payment
provider's webhook, a Space going offline.
"""),
code(SETUP),
code("""
hub.me
"""),
code("""
await hub.auth.whoami()                                   # refreshes the Hub wallet balance; raises NotLoggedIn when anonymous
"""),

md("""
## 3. Find sources

Discovery lives on `hub.endpoints`. `list()` follows the Hub's pages for you; `type` and `owner` are applied by the
Hub, everything else locally. The result is an `EndpointList` you can keep narrowing without a round trip.
"""),
code("""
eps = await hub.endpoints.list()
eps
"""),
code("""
picked = (eps.matching("trial adverse events").filter(type="data_source")
          + eps.pick("dave/notes", "olga/trials-assistant"))
picked.paths
"""),
md("On a Hub too large to list, ask it to search its listings semantically, or walk the pages yourself."),
code("""
(await hub.endpoints.search("clinical notes")).paths
"""),
code("""
async for page in hub.endpoints.pages(page_size=6):
    print(f"offset {page.offset}: {len(page.items)} of {page.total}")
"""),
md("One endpoint's record: every policy in words, pricing decoded from the payment policy, nothing invented."),
code("""
await hub.endpoints.get("dave/notes")
"""),

md("""
## 4. Wallets

Prepaid balances live on `hub.wallets`. One wallet per owner, rail and currency; several endpoints can bill the same
wallet, so one top-up funds all of them. Amounts are `Money`: a `Decimal` with a currency, and two currencies never
add up by accident.
"""),
code("""
await hub.wallets.list()
"""),
code("""
w = await hub.wallets.for_endpoint("dave/notes")
w.balance, w.endpoints, [b.id for b in w.bundles]
"""),

md("""
## 5. Search: compose, pre-flight, execute

`hub.search(...)` composes a `SearchPlan`. Nothing is sent and nothing is awaited. Advanced users keep the plan around
and inspect it; everyone else chains straight to `execute()`.
"""),
code("""
plan = hub.search("What adverse events were reported in phase 3 trials?", sources=picked)
plan
"""),
md("""
`await plan.preflight()` fills the table from Hub metadata, one balance call per prepaid wallet, and the session budget.
Dave's notes are **held**: the wallet is empty. The card says what to do.
"""),
code("""
await plan.preflight()
"""),
md("""
Credits are bought from Dave's Space. `top_up` returns an `Invoice` with the checkout link; the provider's webhook
credits the wallet. Here `world.pay` plays the user and the webhook.
"""),
code("""
invoice = await plan.top_up("dave/notes", "starter")
invoice
"""),
code("""
world.pay(invoice)                                        # mock: paid at the link, webhook fired
await plan.refresh()
"""),
md("""
`execute()` re-runs pre-flight (fresh balances count), then asks every source that passes, in parallel, bounded by
`Options.concurrency`. Frank's feed is rate limited; that cannot be predicted, so it was sent and came back
**rejected**, with what the Space said about its limit surfaced on the row. The charges table is assembled from the
Spaces' own receipts.
"""),
code("""
results = await plan.execute()
results
"""),
code("""
results["erin/trials"]
"""),
md("""
Results are **immutable**. Views return a new `Results` and leave the raw responses alone; combine them with `+`.
`to_dict()` gives stable JSON for a chatbot or a cache.
"""),
code("""
recent = results.filter(published_gte="2024-01-01")
len(results.documents), len(recent.documents), len(recent.top(3).documents)
"""),
code("""
recent.only("carol/papers", "erin/trials").top(3)
"""),
code("""
import json
snapshot = results.to_dict()
print(json.dumps(snapshot)[:200], "…")
syfthub.Results.from_dict(hub, snapshot).ok_count
"""),

md("""
## 6. When a Space says no

A Space's answer is never an exception: it is a row with an outcome that says **who** stopped the call. `HELD` is
pre-flight (nothing spent), `REJECTED` is the Space's policy (403), `FAILED` is transport or server trouble after
retries, `PAYMENT_REQUIRED` is an MPP 402. `retry()` re-sends whatever can change.
"""),
code("""
row = results["frank/registry"]
row.outcome, row.reason, row.retryable, row.rate_limit
"""),
md("""
The transport owns the retry policy. Network errors and 5xx get exponential backoff with jitter. A rate limit whose
reset is short enough is waited out inside the call; the default ceiling is 10 seconds, so Frank's 60-second window
was surfaced instead. Raise the ceiling and the same call waits and succeeds (the mock's clock runs at 100×).
"""),
code("""
from syfthub import Retry, CircuitBreaker

patient = AsyncHub(options=Options(http_client=MockTransport(world), retries=Retry(rate_limit_wait=90)))
await patient.login(username="alice", password="secret")
r = await patient.search("interstitial lung disease signal", sources=["frank/registry"]).execute()
r["frank/registry"].note, r["frank/registry"].attempts, r.ok_count
"""),
md("""
Grace's archive is offline. Three attempts, then a `FAILED` row. After `CircuitBreaker.failures` consecutive
failures the SDK stops sending to that Space for the cooldown: the next plan holds it as `circuit_open` without a
request. Here the breaker is set to trip on the first failure so you can see it.
"""),
code("""
fragile = AsyncHub(options=Options(http_client=MockTransport(world), circuit_breaker=CircuitBreaker(failures=1, cooldown=60)))
first = await fragile.search("anything", sources=["grace/archive", "carol/papers"]).execute()
first
"""),
code("""
second = await fragile.search("anything", sources=["grace/archive", "carol/papers"]).execute()
second["grace/archive"]
"""),
md("Give up on a source and `retry()` leaves it alone."),
code("""
done = results.skip("frank/registry")
[(r.endpoint.path, r.outcome.value, r.reason.value if r.reason else None) for r in done if not r.ok]
"""),

md("""
## 7. A spending cap

`set_budget` caps the session. Pre-flight holds any source whose estimate would cross it; nothing is sent and nothing
raises. `ignore_budget=True` sends the held rows this once.
"""),
code("""
hub.set_budget(0.05)
capped = await hub.search("infection-related adverse events", sources=["erin/trials", "heidi/shared-corpus"]).preflight()
capped
"""),
code("""
r = await capped.execute()
r2 = await r.retry(ignore_budget=True)
[(x.endpoint.path, x.outcome.value) for x in r2], hub.budget
"""),
code("""
hub.budget = None                                         # lift it for the rest of the notebook
"""),

md("""
## 8. Headless: a script or a CI job

No notebook, no buttons. Sign in with a token, let the SDK log one line per fan-out, and when a wallet is short
create the invoice and **wait for the payment** by polling the balance route. Here a background task plays the
person who pays after a while.
"""),
code("""
import asyncio, logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ci_world = World()
ci = AsyncHub(token="syft_pat_alice", options=Options(http_client=MockTransport(ci_world)))
async with ci:
    plan = await ci.search("phase 3 adverse events", sources=["dave/notes", "carol/papers"], limit=3).preflight()
    if plan.pending:
        invoice = await plan.top_up(plan.pending[0].wallet.key, "starter")
        print("pay at", invoice.checkout_url)

        async def someone_pays():                           # mock: the finance team clicks the link later
            await asyncio.sleep(0.3)
            ci_world.pay(invoice)
        asyncio.create_task(someone_pays())

        invoice = await invoice.wait_paid(timeout=600, poll=5)   # polls the balance; the mock clock runs fast
        print("invoice", invoice.id, invoice.status.value)

    results = await plan.execute()
    print(json.dumps({"ok": results.ok_count, "cost": {k: str(v.amount) for k, v in results.cost.items()},
                      "documents": len(results.documents)}))
logging.getLogger().setLevel(logging.WARNING)
"""),

md("""
## 9. Talk it through: the chat room

A model is a Space endpoint, so a chat has the same pre-flight as a search. `results.chat(model)` opens a room over
a results view; pre-flight runs on the first await. Ivan's model is metered and the wallet is empty, so the first
message is held with the top-up attached, never an exception.
"""),
code("""
chat = recent.chat("ivan/gpt-mini")
await chat.preflight()
"""),
code("""
chat.context                                              # exactly what the next message will carry, with token counts
"""),
code("""
await chat.send("Summarise the serious adverse events across these sources.")
"""),
code("""
invoice = await chat.top_up(bundle="starter")
world.pay(invoice)
await chat.send("Summarise the serious adverse events across these sources.")
"""),
md("Follow-ups ride on the transcript. `use(view)` swaps the passages and keeps the turns."),
code("""
await chat.send("Were any of them fatal?")
"""),
code("""
chat.use(recent.only("erin/trials", "olga/trials-assistant").top(3))
await chat.send("And in the registry data alone, what stood out?")
"""),
md("""
A room holds several models. `add` brings one in from the next turn, briefed with the transcript so far; `send` then
returns one `Reply` per model, indexable by path. `remove` stops asking one; its tab stays readable.
"""),
code("""
await chat.add("bob/llama-3")
replies = await chat.send("Do you agree, and what would you add?")
replies
"""),
code("""
replies["bob/llama-3"].text
"""),
code("""
await chat.remove("ivan/gpt-mini")
chat
"""),
md("""
The room **mutates in place**; it is the one stateful object in the SDK. To compare two views over one conversation,
`fork()` first. Replies are frozen snapshots, so an earlier turn's `context` never changes under you.
"""),
code("""
branch = chat.fork().only("erin/trials")
len(chat.view), len(branch.view), chat.turn == branch.turn
"""),
code("""
chat.spent, chat.spent_by("ivan/gpt-mini"), replies.to_dict()["replies"][0]["cost"]
"""),

md("""
## 10. Several models, one question

Asking several models is just a search over model endpoints: same pre-flight, same rows, `answers` keyed by model.
Lena bills in rupiah; totals stay per currency.
"""),
code("""
opinions = await hub.search("What are the main adverse events in phase 3 oncology trials?",
                            sources=["bob/llama-3", "lena/sahabat-ai"]).execute()
opinions.answers
"""),
code("""
opinions.cost
"""),

md("""
## 11. Search on every turn

When the question changes faster than the sources, `hub.chat(model, sources=...)` searches before each message. The
same `filter` travels with every turn's search: to the Space where it advertises the field, into this client
otherwise.
"""),
code("""
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"]).filter(published_gte="2024-01-01").top(4)
await live.send("How many deaths were reported, and were they related to treatment?")
"""),
code("""
live.last.results
"""),

md("""
## 12. Pay per query (MPP, experimental)

An MPP Space answers 402 first. Pre-flight flags it as *will ask to pay* and sends it; the row comes back
`PAYMENT_REQUIRED` with a `Charge`. `approve()` settles it from the Hub wallet and re-sends with the credential.
"""),
code("""
ledger = await hub.search("settlement events for trial data", sources=["kim/ledger"]).execute()
ledger
"""),
code("""
await ledger.approve()
"""),

md("""
## 13. The Aggregator (route proposed)

Two forms, so the SDK is settled whichever way the platform decides. **Documents supplied**: the client already
fanned out; `results.aggregate(model)` sends the view's passages and gets one reranked, cited answer.
"""),
code("""
await recent.aggregate("bob/llama-3")
"""),
md("""
**Sources supplied**: one request, the Aggregator fans out with the client's satellite tokens. Pre-flight still runs
here first, so held sources are never sent. When a Space wants paying anyway, such as an MPP Space answering 402, the
Aggregator cannot pay on your behalf: it returns the per-Space envelopes plus a `job_id`. The same `Charge` and
`TopUp` objects appear on `answer.pending`; pay, then the job resumes with the credentials attached.
"""),
code("""
answer = await hub.aggregate("settlement events and adverse events", sources=["carol/papers", "kim/ledger"], model="bob/llama-3")
answer
"""),
code("""
await answer.approve()                                    # pays the MPP charge from the Hub wallet, resumes the job
"""),

md("""
## 14. Errors

Exceptions are for misuse and for failures with no remedy inside the flow. Every one is a `SyftHubError`, the message
says what to do, and 401 is never conflated with 403.
"""),
code("""
from syfthub import SyftHubError, ValidationError, NotFound, InvalidState, NotLoggedIn

for attempt in (lambda: hub.endpoints.get("not-a-path"),
                lambda: hub.endpoints.get("nobody/here"),
                lambda: chat.remove("lena/sahabat-ai"),
                lambda: AsyncHub(options=Options(http_client=MockTransport(World()))).auth.whoami()):
    try:
        await attempt()
    except SyftHubError as e:
        print(f"{type(e).__name__:<16} {e}")
"""),
code("""
def tree(cls, depth=0):
    print("  " * depth + cls.__name__)
    for sub in cls.__subclasses__():
        tree(sub, depth + 1)
tree(SyftHubError)
"""),

md("""
## 15. The synchronous twin

Scripts and REPLs without an event loop use `syfthub.Hub`: same methods, no `await`. In the real SDK it is generated
from the async package with `unasync`; the mock stands it in with a proxy.
"""),
code("""
with syfthub.Hub(options=Options(http_client=MockTransport(World()))) as sync_hub:
    sync_hub.login(username="alice", password="secret")
    r = sync_hub.search("adverse events", sources=["carol/papers", "erin/trials"]).execute()
    print(r.ok_count, r.cost)
"""),

md("""
## Where this leaves us

- **Three lines to a first result**, free by default; credentials from the environment.
- **Compose is sync and free; network is awaited.** `SearchPlan` is there for whoever wants to look before sending.
- **Namespaces** for growth (`auth`, `endpoints`, `wallets`), two domain verbs at the top (`search`, `chat`), one alias (`login`).
- **Rows, not exceptions**, and the outcome says who stopped the call. Exceptions form one small hierarchy.
- **Immutable results, one mutable room**, with `fork()` to branch it.
- **The transport owns** retries with jitter, the per-Space circuit breaker, token caching, pagination and logging; one `Options` object tunes all of it.
- **Typed everywhere**: enums for closed sets, `Money` for amounts, models for every dict, `to_dict()` for the way out.
- **Headless works**: token login, `wait_paid()`, JSON out.
- **The Aggregator surface is settled** in both forms the platform discussion leaves open.
"""),
]

# =============================================================================================== STORY
STORY = [
md("""
# Alice asks the hub a question

*A walkthrough of the SyftHub Python SDK, v2, as a mock. Everything below runs against in-memory fakes that return
exactly what the real Hub and Space APIs return. Names, prices and documents are invented.*

Alice is an oncology researcher. She wants to know what adverse events were reported in recent phase 3 trials, across
data other people hold, and then talk it through with a model. She has never used SyftHub before.
"""),
code(SETUP),
md("""
## What is out there?

She starts by looking. Sources and models are listed together; the pricing column tells her what each one costs before
she touches it, and the policies column flags anything else that might get in the way.
"""),
code("""
eps = await hub.endpoints.list()
eps
"""),
md("""
Too many. She describes what she is after, roughly, and narrows to data sources. Then she adds two by name: Dave's
clinician notes, and Olga's assistant, an endpoint that answers in its own words *and* returns the passages it used.
An endpoint decides what it returns: references, a summary, or both. A search accepts any of them.
"""),
code("""
picked = eps.matching("trial adverse events").filter(type="data_source") + eps.pick("dave/notes", "olga/trials-assistant")
picked
"""),
md("One of them is paid per document. She looks closer."),
code('await hub.endpoints.get("dave/notes")'),
md("""
## What would this cost?

She writes the question and composes a search over the four sources. **Nothing is sent yet.** Pre-flight shows what
each call would cost at most, her balance on every wallet involved, and a verdict per source. Dave's notes are held:
she has no credits on his wallet.
"""),
code("""
plan = hub.search("What adverse events were reported in phase 3 trials?", sources=picked)
await plan.preflight()
"""),
md("""
The card tells her what to do. Credits are bought from Dave's Space; `top_up` returns the invoice with its checkout
link. She pays in the browser, the provider tells Dave's Space, and the balance is there.
"""),
code("""
invoice = await plan.top_up("dave/notes", "starter")
invoice
"""),
code("""
world.pay(invoice)                                        # mock: Alice pays at the link and the webhook fires
await plan.refresh()
"""),
md("""
## Run it

`execute()` re-checks pre-flight, then asks every endpoint that passes, in parallel. Each row is what that Space
returned: the **returns** column says whether it was references, a summary, or both. Frank's feed is rate limited
today; that could not be known in advance, so it was sent and came back rejected. The charges table at the bottom is
assembled from the Spaces' own receipts.
"""),
code("""
results = await plan.execute()
results
"""),
md("She reads what Erin's registry returned, and what it cost."),
code('results["erin/trials"]'),
md("""
## Only recent work

Documents carry whatever metadata their Space attached. She keeps the ones published since 2024. This happens on her
side, over what came back, so it narrows the `limit` she already asked for; if she filtered hard she would raise it.
(The same verb on a plan, before executing, can send the filter to the Space instead: see *Advanced use cases*.)
"""),
code("""
recent = results.filter(published_gte="2024-01-01")
recent
"""),
md("""
## Talk it through

She picks a model to discuss the results with. A model is a Space endpoint too, so the chat opens with the same
pre-flight: price per message, her balance, a verdict. Ivan's model is metered and she has no credits there yet.
The card also says how much **context** every message will carry, because she pays for those tokens each turn.
"""),
code("""
chat = recent.chat("ivan/gpt-mini")
await chat.preflight()
"""),
md("""
Before spending anything she looks at exactly what the model will see. No turns yet, so only the passages: in citation
order, with Olga's own answer labelled as hers, so the model can cite a passage or another endpoint's conclusion.
"""),
code("chat.context"),
md("If she sends anyway, nothing goes to Ivan's Space. The reply is the same card, with the same action."),
code("""
await chat.send("Summarise the serious adverse events across these sources.")
"""),
code("""
invoice = await chat.top_up(bundle="starter")
world.pay(invoice)                                        # mock: paid at the link
await chat.send("Summarise the serious adverse events across these sources.")
"""),
md("""
Citations point back to the context above. Now she follows up. The question only makes sense together with the
first turn, so the earlier turns ride along with every message; the reply says which turn this is and what the
conversation has cost so far.
"""),
code("""
await chat.send("Were any of them fatal?")
"""),
md("""
For the next question she only wants the registry and Olga's view, and fewer passages. `chat.use(view)` swaps the
passages; the conversation keeps its turns. `chat.context` shows both halves of what the next message will carry:
the earlier turns, then the passages in citation order, each with its token count.
"""),
code("""
chat.use(recent.only("erin/trials", "olga/trials-assistant").top(3))
chat.context
"""),
code("""
await chat.send("And in the registry data alone, what stood out?")
"""),
md("The model condenses its own previous answer: history, not context, is doing the work here."),
code("""
await chat.send("Put that in two bullets for a slide.")
"""),
md("""
## A second opinion

Ivan is metered and she has paid for every message. Bob's model is free. A chat is a room: she adds Bob, who is
briefed with the questions so far and Ivan's answers, and from here every question goes to both. The card grows a
tab per model, each with its own pre-flight and transcript; the context line and the spend stay shared.
"""),
code("""
await chat.add("bob/llama-3")
chat
"""),
code("""
replies = await chat.send("Do you agree with those two bullets, and what would you add?")
replies
"""),
md("""
One reply per model, as tabs; `replies["bob/llama-3"]` picks one out. Bob is free and good enough, so she lets Ivan
go. His tab stays readable, he is just not asked again.
"""),
code("""
replies["bob/llama-3"].text
"""),
code("""
await chat.remove("ivan/gpt-mini")
"""),
md("""
## More evidence, mid-conversation

The consortium corpus was not in her search. A search is the same wherever she is: same pre-flight, same cost card.
She adds its results to what the chat already carries and checks the context before asking.
"""),
code("""
more = await hub.search("infection-related serious adverse events", sources=["heidi/shared-corpus"]).execute()
more
"""),
code("""
chat.use(chat.view + more)
chat.context
"""),
code("""
await chat.send("Does the consortium data change the picture?")
"""),
md("""
The whole room, with each model's pre-flight at the top of its tab. Every message was one request per model asked;
the passages and the growing history are what she pays tokens for. `chat.reset()` would drop the earlier turns
while keeping the passages and the pre-flights.
"""),
code("""
chat
"""),
md("""
## The other way round

Sometimes the question changes faster than the sources. `hub.chat(model, sources=...)` searches on every turn and then
asks; the same filters shape what each turn's results become before the model sees them. Free model, free sources, so
no pre-flight interrupts here.
"""),
code("""
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"]).filter(published_gte="2024-01-01").top(4)
await live.send("How many deaths were reported, and were they related to treatment?")
"""),
code("live.context      # what that turn carried; live.last.results is the search behind it"),
md("""
## Where this leaves us

- Browse, narrow, compose, execute, filter, chat: each step shows its cost before it spends anything.
- One search works over any endpoint. A data source returns references, a model a summary, some return both; the row
  says which, and the chat uses whatever came back.
- Payment is checked twice. The client predicts from Hub metadata and wallet balances and holds what it knows will fail;
  the Space's own 402 or 403 is the authority and lands in the same card. Only the second one costs a round trip.
- Search and chat behave the same way because a model is just another endpoint.
- What a chat sends is a *view of results* you can see (`chat.context`) and reshape with the same verbs you used on
  results (`filter`, `only`, `drop`, `top`), before the first paid message or between turns.
- A chat is a room. Questions are shared, each model keeps its own transcript, and the card is one tab per model.
  `chat.add` brings a model in from the next turn (briefed, by default), `chat.remove` stops asking one, `send`
  returns one reply per model, indexable by path, and `chat.spent` is the room's total.
- Search and chat compose both ways. `results.chat(...)` starts a chat from a search; `chat.use(chat.view + more)`
  folds a later search into a running chat. There is one way to search, and it always shows its cost first.
- Every message carries the earlier turns; the card shows how big that is, and `chat.reset()` starts over without
  losing the view.

*User flows* covers the rest: headless use, failures and retries, budgets, the Aggregator, errors and the sync twin.
*Advanced use cases* has the parts that go beyond today's Space API.
"""),
]

# ============================================================================================ ADVANCED
ADVANCED = [
md("""
# Advanced use cases

*Each section stands on its own and runs against the same in-memory fakes as the story. These are the parts of the
SDK that go beyond what the Space API does today; where a section needs something the API does not have, it says so
and shows the shape we would propose.*
"""),
code(SETUP),
md("""
## 1. Filters that travel to the Space

A filter on document metadata has two possible homes. If the Space applies it, the filter runs *before* `limit`: you
get `limit` matching documents and, on a per-document price, pay only for those. If the SDK applies it, the filter runs
*after* `limit` on whatever came back: you may get fewer than `limit`, and you have paid for the ones it hid.

Today a Space does not filter. The proposal: a Space publishes the metadata fields it can filter on along with its
endpoint (a `filterable` list on the Hub record), accepts a `filters` object in the query body for those fields, and
echoes what it applied as `filters_applied`. The SDK then has one verb, `filter(...)`, and tells you per source which
home each key gets. The endpoint detail shows what a Space advertises:
"""),
code("""
await hub.endpoints.get("carol/papers")
"""),
code("""
await hub.endpoints.get("dave/notes")      # advertises nothing: filters on Dave's notes stay on the client
"""),
md("""
Same filter, three sources, three documents each. Carol's papers and Erin's registry take `published` at the Space;
Dave's notes do not, and they are priced per document, so the pre-flight warns that the hidden ones are still billed.
"""),
code("""
plan = hub.search("adverse events in phase 3 trials", sources=["carol/papers", "erin/trials", "dave/notes"], limit=3)
plan = plan.filter(published_gte="2024-06-01")
await plan.preflight()
"""),
code("""
invoice = await plan.top_up("dave/notes", "starter")
world.pay(invoice)                                        # mock: paid at the link
results = await plan.execute()
results
"""),
md("""
Carol returned three documents, all from mid-2024 or later: the Space filtered first and then applied the limit.
Without the Space's help she would have got two, because her third-best match is from 2023. Dave's Space did exactly
that: it returned its three best matches, the SDK hid the 2023 one, and the charge is still for three.
"""),
code("""
results["carol/papers"]
"""),
code("""
results["dave/notes"]
"""),
md("""
What actually went over the wire. The request body carries the proposed `filters` object only for Spaces that
advertise the field; the response echoes what the Space applied.
"""),
code("""
results["carol/papers"].request["filters"], results["carol/papers"].raw["filters_applied"]
"""),
code("""
"filters" in results["dave/notes"].request        # nothing was sent: the SDK filtered after the fact
"""),
md("""
A filter can split. Erin advertises only `published`, so `author` stays on the client for her and goes to the Space
for Carol. The pre-flight shows the split per source before anything is spent.
"""),
code("""
await hub.search("adverse events in phase 3 trials", sources=["carol/papers", "erin/trials"], limit=3) \\
         .filter(published_gte="2024-01-01", author="R. Chitrakoot").preflight()
"""),
md("""
The same `filter` verb works on a chat that searches every turn: the filter goes with each turn's search, to the
Space where it can.
"""),
code("""
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"]).filter(published_gte="2024-06-01")
await live.send("What were the serious adverse event rates?")
"""),
code("""
live.last.results         # that turn's search, filtered at both Spaces
"""),
md("""
## 2. A room of models from the start

`results.chat` takes one model or several. Each gets its own pre-flight row; one that is short of credits is held
and answers with a top-up card, the others answer normally. Nothing blocks on the one that cannot pay.
"""),
code("""
results = await hub.search("adverse events in phase 3 trials", sources=["carol/papers", "olga/trials-assistant"]).execute()
room = results.chat(["ivan/gpt-mini", "bob/llama-3"])
await room.preflight()
"""),
code("""
replies = await room.send("Summarise the serious adverse events.")
replies
"""),
code("""
[(r.model.path, r.outcome.value, r.reason.value if r.reason else None) for r in replies]
"""),
md("""
Credits fix the held tab. The top-up names the model when more than one could be short; here only Ivan is, so the
name is optional. Sending again asks both, and both answer.
"""),
code("""
invoice = await room.top_up("ivan/gpt-mini", bundle="starter")
world.pay(invoice)                                        # mock: paid at the link
replies = await room.send("Summarise the serious adverse events.")
replies
"""),
md("""
Who answers can change between turns. `room.add` brings a model in from the next question on, briefed with the
lead tab's transcript by default; `room.remove` stops asking one. Each model sees the shared questions and only
its own earlier answers.
"""),
code("""
await room.add("lena/sahabat-ai")      # billed in rupiah, from Lena's IDR wallet
await room.send("Were any of them fatal?")
"""),
code("""
await room.remove("ivan/gpt-mini")
await room.send("And in one line?")
"""),
md("""
`room.spent` is the room's total across every turn and every model, kept per currency because models sit behind
different wallets: Ivan bills in dollars, Lena in rupiah, and the SDK never converts. `room.spent_by(path)` is one
tab's share. The card shows the same numbers: the totals in the header, the share on each tab.
"""),
code("""
room.spent, {m.path: room.spent_by(m.path) for m in room.models}
"""),
code("""
room
"""),
md("""
**What this needs from the platform.** Three small additions, none of which change the response shape for clients
that do not filter: `filterable: [str]` on the published endpoint and the Hub's public record; `filters` in the
query body, `{field: {op: value}}` with ops `eq | gte | gt | lte | lt | contains`; `filters_applied` echoed in the
response. Until then the SDK behaves as if every Space advertised nothing, which is exactly the client-side path.
"""),
]


def build(cells, name):
    nb = nbf.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.cells = [nbf.v4.new_markdown_cell(c[1].strip()) if c[0] == "md" else nbf.v4.new_code_cell(c[1].strip()) for c in cells]
    NotebookClient(nb, timeout=180, kernel_name="python3", resources={"metadata": {"path": "."}}, allow_errors=True).execute()
    nbf.write(nb, name)
    errs = [(i, o["ename"], o["evalue"]) for i, c in enumerate(nb.cells) if c.cell_type == "code"
            for o in c.get("outputs", []) if o.get("output_type") == "error"]
    print(f"{name}: {len(nb.cells)} cells, {len(errs)} errors", *[f"\n   cell {i}: {n}: {v}" for i, n, v in errs])
    return bool(errs)


ALL = {"flows": (FLOWS, "flows.ipynb"), "story": (STORY, "story.ipynb"), "advanced": (ADVANCED, "advanced.ipynb")}
if __name__ == "__main__":
    which = sys.argv[1:] or list(ALL)
    failed = [build(*ALL[w]) for w in which]
    sys.exit(1 if any(failed) else 0)
