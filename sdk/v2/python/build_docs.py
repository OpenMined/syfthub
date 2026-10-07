"""Generate docs/index.html, the reference for the v2 SDK.

The page is built by introspecting the package: classes, fields, properties, methods and their
signatures come from the code, and the explanations come from the Google-style docstrings
(summary, Args, Returns, Raises, Attributes). Only the examples are written here by hand.

Run: .venv/bin/python build_docs.py
"""
from __future__ import annotations

import dataclasses
import enum
import html
import inspect
import re
from pathlib import Path

from pydantic import BaseModel

import syfthub
from syfthub import _sync, _transport as T, auth as A, chat as C, endpoints as EP, errors as E, hub as H, models as M
from syfthub import results as R, search as S, wallets as W
from syfthub.testing import World

OUT = Path(__file__).parent / "docs" / "index.html"

# ----------------------------------------------------------------------------- what goes on the page
GROUPS = [
    ("Session", "Open a session, tune the transport, sign in.",
     [H.AsyncHub, _sync.Hub, T.Options, T.Retry, T.Timeout, T.CircuitBreaker, A.AuthNamespace, M.Identity, M.Budget, M.Money]),
    ("Discovery", "Find endpoints on the Hub and shortlist them.",
     [EP.EndpointsNamespace, M.EndpointList, M.Endpoint, M.Policy, M.Pricing, M.Bundle, M.Connection, M.Page]),
    ("Search", "Compose a search, review what it will cost, pay what is short, then send it.",
     [S.SearchPlan, M.PlanRow, M.FilterSplit]),
    ("Results", "What came back, one row per source, and what you can do with it.",
     [R.Results, M.SourceResult, M.Document, M.ChargeEntry, M.RateLimit, M.Answer]),
    ("Chat", "Talk to one or more models about your results.",
     [C.Chat, C.Replies, C.Reply, C.Context, M.Message]),
    ("Wallets and payment", "Prepaid credits, invoices, and what to do when a wallet runs short.",
     [W.WalletsNamespace, M.WalletList, M.Wallet, M.Invoice, M.TopUp, M.Charge]),
    ("Enums", "The closed sets. Every one is a str enum, so the wire value works too.",
     [M.EndpointType, M.Rail, M.PolicyType, M.PriceUnit, M.Outcome, M.Reason, M.Verdict, M.ReturnKind, M.Include, M.Via,
      M.AuthMethod, M.Health, M.InvoiceStatus]),
    ("Errors", "Raised only for misuse and for failures with no remedy in the flow. A Space saying no is a row, never an exception.",
     [E.SyftHubError, E.ConfigurationError, E.ValidationError, E.AuthError, E.NotLoggedIn, E.HubError, E.NotFound,
      E.HubUnavailable, E.SpaceError, E.InvoiceError, E.AggregatorError, E.BudgetExceeded, E.InvalidState]),
    ("Testing", "Offline doubles for your own tests.",
     [World]),
]

# Display names for things you reach through an attribute rather than by class name.
ALIAS = {A.AuthNamespace: "hub.auth", EP.EndpointsNamespace: "hub.endpoints", W.WalletsNamespace: "hub.wallets",
         _sync.Hub: "syfthub.Hub", World: "syfthub.testing.World"}

# Classes whose members need no example (test doubles).
RELAXED = {World}

# Hand-written examples, keyed "Label.member", or "Label" for the type itself.
EX = {
"AsyncHub": '''import syfthub

async with syfthub.AsyncHub() as hub:                     # SYFTHUB_URL, SYFTHUB_TOKEN from the environment
    results = await hub.search("adverse events in phase 3 trials").execute()''',
"AsyncHub.login": '''await hub.login(username="alice", password="secret")
await hub.login(token="syft_pat_...")                     # the headless path''',
"AsyncHub.set_budget": '''hub.set_budget(2.00)                                      # hold any source that would push the session past $2
hub.budget.remaining''',
"AsyncHub.search": '''plan = hub.search("What adverse events were reported in phase 3 trials?", sources=picked, limit=5)
await plan.preflight()                                    # costs, balances, verdicts; nothing sent
results = await plan.execute()''',
"AsyncHub.chat": '''live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"]).filter(published_gte="2024-01-01")
await live.send("How many deaths were reported?")''',
"AsyncHub.aggregate": '''answer = await hub.aggregate("phase 3 adverse events", sources=["carol/papers", "kim/ledger"], model="bob/llama-3")
if answer.pending:
    answer = await answer.approve()                       # or buy the bundle, then answer.resume()''',
"AsyncHub.close": "await hub.close()                                        # async with does this for you",
"AsyncHub.transport": "world = hub.transport.world                               # mock only: poke the fake world",
"syfthub.Hub": '''with syfthub.Hub() as hub:
    results = hub.search("adverse events in phase 3 trials").execute()''',
"Options": '''from syfthub import Options, Retry, CircuitBreaker

hub = syfthub.AsyncHub(options=Options(
    retries=Retry(max_attempts=4, rate_limit_wait=30),
    circuit_breaker=CircuitBreaker(failures=2, cooldown=120),
    concurrency=4,
))''',
"Options.user_agent": '''Options(user_agent_suffix="my-app/2.1").user_agent("0.1.0")
# -> 'syfthub-python/0.1.0 python/3.12.4 my-app/2.1\'''',
"Retry": "Retry(max_attempts=3, initial=0.5, multiplier=1.5, jitter=0.5, rate_limit_wait=10)",
"Retry.delay": '''Retry().delay(1), Retry().delay(2)                        # seconds before the first and second retry, jittered
# -> (0.41, 0.63)''',
"Timeout": "Timeout(connect=5, read=30)",
"CircuitBreaker": "CircuitBreaker(failures=3, cooldown=60)",
"hub.auth": '''await hub.auth.login(username="alice", password="secret")
await hub.auth.login_with_token("syft_pat_...")
await hub.auth.login_with_google()''',
"hub.auth.login": 'await hub.auth.login(username="alice", password="secret")',
"hub.auth.login_with_token": 'await hub.auth.login_with_token("syft_pat_...")',
"hub.auth.login_with_google": "await hub.auth.login_with_google()                      # opens the browser",
"hub.auth.whoami": '''me = await hub.auth.whoami()
me.username, me.hub_wallet_balance
# -> ('alice', Money(1.5, 'USD'))''',
"hub.auth.logout": "await hub.auth.logout()",
"Identity": '''hub.me
# -> Identity(alice, alice@example.com, password, hub wallet $1.50)''',
"Budget": '''hub.set_budget(2.00)
hub.budget
# -> Budget($2.00 of $2.00 left)''',
"Budget.remaining": "hub.budget.remaining",
"Money": '''from syfthub import Money
Money.of(0.02) * 5 + Money.of(0.05)
# -> Money(0.15, 'USD')
Money.of(300, "IDR") + Money.of(1)                        # raises ValidationError: currencies never mix''',
"Money.of": 'Money.of("0.02"), Money.of(300, "IDR")',
"Money.is_zero": "Money().is_zero\n# -> True",
"Money.__add__": "Money.of(0.05) + Money.of(0.02)\n# -> Money(0.07, 'USD')",
"hub.endpoints": '''eps = await hub.endpoints.list()
await hub.endpoints.search("clinical notes")
await hub.endpoints.get("dave/notes")''',
"hub.endpoints.list": '''await hub.endpoints.list()                                 # everything, pages followed for you
await hub.endpoints.list(type="data_source", free=True)
await hub.endpoints.list(matching="trial adverse events")''',
"hub.endpoints.pages": '''async for page in hub.endpoints.pages(page_size=50):
    print(page.offset, len(page.items), page.total)''',
"hub.endpoints.search": 'await hub.endpoints.search("adverse events in oncology trials")',
"hub.endpoints.get": '''ep = await hub.endpoints.get("dave/notes")
ep.pricing.label
# -> '$0.02/document via xendit\'''',
"hub.endpoints.resolve": 'await hub.endpoints.resolve(["dave/notes", "collective/oncology", picked])',
"EndpointList": '''eps = await hub.endpoints.list()
picked = eps.matching("trial adverse events").filter(type="data_source") + eps.pick("dave/notes")
picked.paths''',
"EndpointList.paths": "picked.paths\n# -> ['carol/papers', 'erin/trials', 'dave/notes']",
"EndpointList.filter": 'eps.filter(type="data_source", free=True)',
"EndpointList.matching": 'eps.matching("trial adverse events")',
"EndpointList.pick": 'eps.pick("dave/notes", "olga/trials-assistant")',
"EndpointList.__add__": 'eps.matching("trials") + eps.pick("dave/notes")',
"Endpoint": '''ep = await hub.endpoints.get("dave/notes")
ep.type, ep.pricing.label, ep.filterable
# -> (<EndpointType.DATA_SOURCE: 'data_source'>, '$0.02/document via xendit', ())''',
"Endpoint.path": "ep.path\n# -> 'dave/notes'",
"Endpoint.url": "ep.url\n# -> 'https://dave.spaces.example'",
"Endpoint.pricing": "ep.pricing.rail, ep.pricing.price\n# -> (<Rail.XENDIT: 'xendit'>, Money(0.02, 'USD'))",
"Endpoint.policy": 'ep.policy("rate_limit").config["limit"]\n# -> \'60/m\'',
"Policy": "[p.type.value for p in ep.policies]\n# -> ['xendit', 'rate_limit']",
"Policy.is_payment": "ep.policies[0].is_payment\n# -> True",
"Pricing": "ep.pricing\n# -> Pricing(rail=xendit, price=Money(0.02, 'USD'), unit=document, …)",
"Pricing.currency": "ep.pricing.currency\n# -> 'USD'",
"Pricing.paid": "ep.pricing.paid\n# -> True",
"Pricing.prepaid": "ep.pricing.prepaid\n# -> True",
"Pricing.label": "ep.pricing.label\n# -> '$0.02/document via xendit'",
"Pricing.estimate": "ep.pricing.estimate(limit=5)\n# -> Money(0.10, 'USD')",
"Pricing.from_policies": "Pricing.from_policies(ep.policies)",
"Bundle": "[(b.id, str(b.amount)) for b in ep.pricing.bundles]\n# -> [('starter', '$5.00'), ('pro', '$20.00')]",
"Connection": "ep.connect[0].config['url']\n# -> 'https://dave.spaces.example'",
"Page": '''async for page in hub.endpoints.pages():
    page.items, page.offset, page.total''',
"SearchPlan": '''plan = hub.search("adverse events in phase 3 trials", sources=picked)   # sync, free
plan = plan.filter(published_gte="2024-01-01")
await plan.preflight()
results = await plan.execute()''',
"SearchPlan.filter": 'plan.filter(published_gte="2024-01-01", author_contains="chitrakoot")',
"SearchPlan.filters_for": '''split = plan.filters_for(plan.rows[0])
split.remote, split.local''',
"SearchPlan.ready": "plan.ready\n# -> False until await plan.preflight()",
"SearchPlan.endpoints": "await plan.endpoints()",
"SearchPlan.preflight": "await plan.preflight()                                    # shows the table in a notebook",
"SearchPlan.refresh": "await plan.refresh()                                      # after paying",
"SearchPlan.estimate": "plan.estimate\n# -> {'USD': Money(0.15, 'USD')}",
"SearchPlan.sending": "[r.endpoint.path for r in plan.sending]",
"SearchPlan.held": "[(r.endpoint.path, r.hold_reason) for r in plan.held]",
"SearchPlan.pending": "plan.pending\n# -> [TopUp(w-dave-xendit-usd: needs $0.10, waiting ['dave/notes'])]",
"SearchPlan.top_up": '''invoice = await plan.top_up("dave/notes", "starter")
invoice.checkout_url''',
"SearchPlan.execute": '''results = await plan.execute()
results = await plan.execute(ignore_budget=True)         # send what pre-flight held as over budget''',
"PlanRow": "plan.rows[0].verdict, plan.rows[0].estimate\n# -> (<Verdict.READY: 'ready'>, Money(0.05, 'USD'))",
"FilterSplit": "plan.filters_for(row).remote\n# -> {'published_gte': '2024-01-01'}",
"Results": '''results = await plan.execute()
results.ok_count, results.cost
recent = results.filter(published_gte="2024-01-01").top(5)''',
"Results.filter": 'results.filter(published_gte="2024-01-01")',
"Results.only": 'results.only("erin/trials", "olga/trials-assistant")',
"Results.drop": 'results.drop("frank/registry")',
"Results.top": "results.top(3)",
"Results.__add__": '''more = await hub.search("infection-related SAEs", sources=["heidi/shared-corpus"]).execute()
both = results + more''',
"Results.__getitem__": 'results["erin/trials"].documents',
"Results.paths": "results.paths",
"Results.returned": "[r.endpoint.path for r in results.returned]",
"Results.ok_count": "results.ok_count\n# -> 4",
"Results.skipped": "[(r.endpoint.path, r.outcome, r.reason) for r in results.skipped]",
"Results.documents": '''for path, doc in results.documents[:3]:
    print(path, doc.similarity_score, doc.content[:60])''',
"Results.answers": "results.answers\n# -> {'olga/trials-assistant': 'Across my curated corpus, …'}",
"Results.kind": "results.kind\n# -> <ReturnKind.BOTH: 'both'>",
"Results.raw": 'results.raw["erin/trials"]["policy_metadata"]',
"Results.pending": "results.pending\n# -> [TopUp(…)] or [Charge(…)]",
"Results.charges": "[(c.source, c.status, str(c.amount)) for c in results.charges]",
"Results.cost": "results.cost\n# -> {'USD': Money(0.13, 'USD')}",
"Results.to_dict": '''import json
json.dumps(results.to_dict())''',
"Results.from_dict": "syfthub.Results.from_dict(hub, json.loads(saved))",
"Results.top_up": '''invoice = await results.top_up("dave/notes", "starter")
# pay at invoice.checkout_url, then
results = await results.retry()''',
"Results.retry": '''results = await results.retry()                           # every retryable row
results = await results.retry("frank/registry")
results = await results.retry(ignore_budget=True)''',
"Results.approve": 'results = await results.approve("kim/ledger")             # MPP, experimental',
"Results.skip": 'results = results.skip("frank/registry")',
"Results.chat": '''chat = results.chat("ivan/gpt-mini")
chat = results.chat(["ivan/gpt-mini", "bob/llama-3"], include="references")''',
"Results.ask": '''reply = await results.ask("bob/llama-3", "What stands out?")
reply.text''',
"Results.aggregate": '''answer = await results.aggregate("bob/llama-3")
answer.text, answer.citations''',
"SourceResult": '''row = results["erin/trials"]
row.outcome, row.cost, len(row.documents)''',
"SourceResult.ok": "row.ok",
"SourceResult.retryable": "row.retryable",
"SourceResult.all_documents": "len(row.all_documents)                                   # before client-side filters",
"SourceResult.documents": "row.documents",
"SourceResult.kind": "row.kind\n# -> <ReturnKind.REFERENCES: 'references'>",
"SourceResult.summary": 'results["olga/trials-assistant"].summary',
"SourceResult.usage": 'results["olga/trials-assistant"].usage["total_tokens"]',
"SourceResult.cost": "row.cost\n# -> Money(0.05, 'USD')",
"SourceResult.policy_metadata": 'row.policy_metadata["entries"][0]["status"]\n# -> \'charged\'',
"SourceResult.charges": "row.charges[0].transaction_id",
"SourceResult.detail": 'results["frank/registry"].detail',
"Document": "doc.document_id, doc.similarity_score, doc.metadata.get('published')",
"ChargeEntry": "c = results.charges[0]\nc.source, c.policy_type, c.status, c.amount",
"ChargeEntry.signed": "sum((c.signed for c in results.charges if c.signed), Money())",
"RateLimit": 'results["frank/registry"].rate_limit\n# -> RateLimit(limit=\'2/m\', remaining=0, reset_seconds=37)',
"Answer": '''answer = await results.aggregate("bob/llama-3")
answer.text, answer.citations, answer.reranked[:2]''',
"Answer.ok": "answer.ok",
"Answer.resume": '''invoice = await answer.pending[0].buy("starter")           # a TopUp the Aggregator forwarded
# pay, then
answer = await answer.resume()''',
"Answer.approve": "answer = await answer.approve()                           # pays forwarded MPP charges, resumes",
"Chat": '''chat = results.chat("ivan/gpt-mini")
await chat.preflight()
replies = await chat.send("Summarise the serious adverse events.")
await chat.add("bob/llama-3")
await chat.send("Do you agree?")''',
"Chat.turn": "chat.turn",
"Chat.add": 'await chat.add("bob/llama-3")                            # briefed with the transcript so far',
"Chat.remove": 'await chat.remove("ivan/gpt-mini")',
"Chat.fork": 'branch = chat.fork().only("erin/trials")                   # compare two views over one conversation',
"Chat.lead": "chat.lead.path",
"Chat.endpoint": 'chat.endpoint("bob/llama-3").pricing.label',
"Chat.preflight": "await chat.preflight()",
"Chat.rows": 'chat.rows["ivan/gpt-mini"].verdict',
"Chat.pending": "chat.pending",
"Chat.top_up": '''invoice = await chat.top_up(bundle="starter")             # one model short: no need to name it
invoice = await chat.top_up("ivan/gpt-mini", bundle="starter")''',
"Chat.view": "chat.view.paths",
"Chat.history": 'await hub.search("follow-up", sources=picked, history=chat.history).execute()',
"Chat.context": "chat.context                                              # earlier turns + passages, with token counts",
"Chat.use": 'chat.use(results.only("erin/trials").top(3))\nchat.use(chat.view + more)',
"Chat.filter": 'chat.filter(published_gte="2024-01-01")',
"Chat.only": 'chat.only("erin/trials", "olga/trials-assistant")',
"Chat.drop": 'chat.drop("frank/registry")',
"Chat.top": "chat.top(4)",
"Chat.reset": "chat.reset()                                              # drops the turns, keeps the passages",
"Chat.send": '''replies = await chat.send("Were any of them fatal?")
replies.text                                              # one model
replies["bob/llama-3"].text                               # several''',
"Chat.last": "chat.last.cost",
"Chat.spent": "chat.spent\n# -> {'USD': Money(0.08, 'USD')}",
"Chat.spent_by": 'chat.spent_by("ivan/gpt-mini")',
"Chat.to_dict": "json.dumps(chat.to_dict())",
"Replies": '''replies = await chat.send("Do you agree?")
replies.models, replies["bob/llama-3"].text, replies.cost''',
"Replies.__getitem__": 'replies["bob/llama-3"]',
"Replies.models": "replies.models",
"Replies.text": "replies.text                                              # when one model was asked",
"Replies.citations": "replies.citations",
"Replies.reason": "replies.reason",
"Replies.ok": "replies.ok",
"Replies.context": "replies.context.tokens",
"Replies.pending": "replies.pending",
"Replies.charges": "replies.charges",
"Replies.cost": "replies.cost",
"Replies.to_dict": 'replies.to_dict()["replies"][0]["text"]',
"Reply": 'reply = replies["bob/llama-3"]\nreply.ok, reply.text, reply.cost',
"Reply.outcome": "reply.outcome",
"Reply.reason": "reply.reason",
"Reply.text": "reply.text",
"Reply.ok": "reply.ok",
"Reply.pending": "reply.pending",
"Reply.charges": "reply.charges",
"Reply.cost": "reply.cost",
"Context": "ctx = chat.context\nctx.turns, ctx.counts, ctx.tokens",
"Context.source_tokens": "ctx.source_tokens",
"Context.history_tokens": "ctx.history_tokens",
"Context.tokens": "ctx.tokens",
"Context.turns": "ctx.turns",
"Context.counts": "ctx.counts\n# -> {'references': 10, 'summaries': 1}",
"Message": "chat.history[0]\n# -> Message(role=<Role.USER: 'user'>, content='Summarise …')",
"Message.wire": "chat.history[0].wire()\n# -> {'role': 'user', 'content': 'Summarise …'}",
"hub.wallets": '''await hub.wallets.list()
w = await hub.wallets.for_endpoint("dave/notes")
invoice = await w.top_up("starter")''',
"hub.wallets.list": "await hub.wallets.list()\nawait hub.wallets.list(picked)",
"hub.wallets.get": 'await hub.wallets.get("w-dave-xendit-usd")',
"hub.wallets.for_endpoint": 'await hub.wallets.for_endpoint("dave/notes")',
"hub.wallets.balance": 'await hub.wallets.balance("dave/notes")\n# -> Money(0.0, \'USD\')',
"WalletList": 'wallets = await hub.wallets.list()\nwallets["dave/notes"], wallets["w-dave-xendit-usd"]',
"WalletList.__getitem__": 'wallets["dave/notes"].balance',
"Wallet": "w.key, w.rail, w.balance, w.endpoints",
"Wallet.bundle": 'w.bundle("starter").amount',
"Wallet.top_up": 'invoice = await w.top_up("starter")',
"Wallet.refresh": "w = await w.refresh()",
"Invoice": '''invoice = await plan.top_up("dave/notes", "starter")
invoice.checkout_url, invoice.status''',
"Invoice.paid": "invoice.paid",
"Invoice.wait_paid": "invoice = await invoice.wait_paid(timeout=600, poll=5)      # headless: polls the balance route",
"TopUp": '''topup = plan.pending[0]
topup.wallet.key, topup.needed, topup.waiting''',
"TopUp.balance": "topup.balance",
"TopUp.bundles": "[b.id for b in topup.bundles]",
"TopUp.buy": 'invoice = await topup.buy("starter")',
"Charge": 'charge = results.pending[0]\ncharge.amount\n# -> Money(0.05, \'USD\')',
"EndpointType": 'ep.type is EndpointType.DATA_SOURCE\n(await hub.endpoints.list(type="model")).paths',
"EndpointType.returns_references": "EndpointType.MODEL_DATA_SOURCE.returns_references\n# -> True",
"EndpointType.returns_summary": "EndpointType.DATA_SOURCE.returns_summary\n# -> False",
"Rail": "ep.pricing.rail\n# -> <Rail.XENDIT: 'xendit'>",
"Rail.prepaid": "Rail.CLUSTER.prepaid, Rail.MPP.prepaid\n# -> (True, False)",
"PolicyType": "[p.type for p in ep.policies]",
"PolicyType.is_payment": "PolicyType.STRIPE.is_payment\n# -> True",
"PriceUnit": "ep.pricing.unit\n# -> <PriceUnit.DOCUMENT: 'document'>",
"Outcome": '''for row in results:
    if row.outcome is Outcome.REJECTED:
        print(row.endpoint.path, row.reason)''',
"Reason": 'results["frank/registry"].reason\n# -> <Reason.RATE_LIMITED: \'rate_limited\'>',
"Reason.retryable": "Reason.RATE_LIMITED.retryable, Reason.ACCESS_DENIED.retryable\n# -> (True, False)",
"Verdict": "plan.rows[0].verdict\n# -> <Verdict.READY: 'ready'>",
"Verdict.label": "Verdict.NEEDS_CREDITS.label\n# -> 'needs credits'",
"ReturnKind": "results.kind\n# -> <ReturnKind.BOTH: 'both'>",
"Include": 'results.chat("bob/llama-3", include=Include.REFERENCES)',
"Via": 'hub.chat("bob/llama-3", via=Via.AGGREGATOR)',
"AuthMethod": "hub.me.auth\n# -> <AuthMethod.TOKEN: 'token'>",
"Health": "ep.health\n# -> <Health.HEALTHY: 'healthy'>",
"InvoiceStatus": "invoice.status is InvoiceStatus.PAID",
"SyftHubError": '''try:
    await hub.endpoints.get("nobody/here")
except syfthub.SyftHubError as e:
    print(type(e).__name__, e)''',
"ConfigurationError": 'syfthub.AsyncHub("hub.example.com")                      # raises: url must include a scheme',
"ValidationError": 'hub.search("q", sources=picked, limit=0)                  # raises: limit must be at least 1',
"AuthError": '''try:
    await hub.login(token="bad")
except syfthub.AuthError as e:
    print(e.who, e)''',
"NotLoggedIn": '''try:
    await hub.auth.whoami()
except syfthub.NotLoggedIn:
    await hub.login(token=os.environ["SYFTHUB_TOKEN"])''',
"HubError": "except syfthub.HubError as e:\n    print(e.status, e.url, e.request_id)",
"NotFound": 'await hub.endpoints.get("nobody/here")                    # raises NotFound',
"HubUnavailable": "except syfthub.HubUnavailable:\n    schedule_retry()",
"SpaceError": "except syfthub.SpaceError as e:\n    print(e.path, e.status, e.body)",
"InvoiceError": 'await w.top_up("no-such-bundle")                         # raises InvoiceError',
"AggregatorError": '''try:
    await results.aggregate("bob/llama-3")
except syfthub.AggregatorError as e:
    print(e.status, e)''',
"BudgetExceeded": '''try:
    await results.approve()
except syfthub.BudgetExceeded as e:
    print(e.needed, e.remaining)''',
"InvalidState": 'await chat.remove("nobody/here")                          # raises InvalidState',
"syfthub.testing.World": '''from syfthub.testing import World, MockTransport

world = World()
hub = syfthub.AsyncHub(options=syfthub.Options(http_client=MockTransport(world)))
world.pay(invoice)                                        # the user paid and the webhook fired
world.space_down("grace/archive")''',
}

# Verbs at a glance: (verb, lives on, what it does)
VERBS = [
    ("endpoints.list / search / get", "hub", "List endpoints (pages followed), search the Hub's listings, or open one."),
    ("wallets.list / for_endpoint / balance", "hub", "Your prepaid balances, one wallet per owner, rail and currency."),
    ("login", "hub, hub.auth", "Sign in with a password or a token. The only top-level alias."),
    ("search, then preflight, then execute", "hub, SearchPlan", "Compose for free, see the cost, send what passes."),
    ("filter", "SearchPlan, Results, Chat", "Narrow by document metadata. On a plan, sent to Spaces that support it."),
    ("matching / pick / +", "EndpointList", "Fuzzy-match, pick by name, combine two lists."),
    ("top_up / buy", "SearchPlan, Results, Chat, Wallet, TopUp", "Buy a credit bundle. You get an Invoice with a checkout URL; wait_paid polls."),
    ("retry / approve / skip", "Results", "Re-send what can change, pay MPP charges, or drop a source. Each returns a new Results."),
    ("only / drop / top / +", "Results", "Views. The raw responses are never changed."),
    ("chat / ask / aggregate", "Results", "Start a room about the results, ask once, or hand them to the Aggregator."),
    ("send", "Chat", "One message to every model in the room. Returns a reply per model."),
    ("use / view / context", "Chat", "See what the next message carries and change which passages it uses."),
    ("add / remove / fork / reset", "Chat", "Change who answers, branch the conversation, or start the thread over."),
]

TOUR = '''import syfthub

async with syfthub.AsyncHub(token="syft_pat_...") as hub:

    # Shortlist some sources
    eps = await hub.endpoints.list()
    picked = eps.matching("trial adverse events").filter(type="data_source") + eps.pick("dave/notes")

    # Compose a search: free, nothing sent. Pre-flight shows the cost per source and what is held
    plan = hub.search("What adverse events were reported in phase 3 trials?", sources=picked)
    await plan.preflight()

    # One wallet is short: buy a bundle, pay at the link (or wait for the payment in a script)
    invoice = await plan.top_up("dave/notes", "starter")
    invoice = await invoice.wait_paid()

    # Send it. Every source comes back returned, held, rejected, failed, or payment required
    results = await plan.execute()
    recent = results.filter(published_gte="2024-01-01")

    # Talk to a model about the results. Same pre-flight: price per message, your balance
    chat = recent.chat("ivan/gpt-mini")
    chat.context                                   # what the next message will carry
    await chat.send("Summarise the serious adverse events.")

    # A second opinion joins from here on, briefed with the transcript so far
    await chat.add("bob/llama-3")
    (await chat.send("Do you agree, and what would you add?"))["bob/llama-3"].text
    await chat.remove("ivan/gpt-mini")

    # Add fresh evidence mid-conversation
    more = await hub.search("infection-related SAEs", sources=["heidi/shared-corpus"]).execute()
    chat.use(chat.view + more)

    chat.spent
    # -> {'USD': Money(0.08, 'USD')}'''


# ----------------------------------------------------------------------------- docstring parsing
SECTIONS = ("Args", "Arguments", "Returns", "Raises", "Attributes")


def parse_doc(text: str) -> dict:
    """Split a Google-style docstring into summary, body paragraphs and named sections."""
    out = {"summary": "", "body": [], "args": [], "returns": "", "raises": [], "attributes": []}
    if not text:
        return out
    lines = text.split("\n")
    i, free = 0, []
    while i < len(lines):
        ln = lines[i]
        head = ln.strip().rstrip(":")
        if ln.strip().endswith(":") and head in SECTIONS:
            items: list[tuple[str, str]] = []
            i += 1
            cur_name, cur_desc = None, []
            while i < len(lines) and (lines[i].startswith(" ") or not lines[i].strip()):
                raw = lines[i]
                if not raw.strip():
                    i += 1
                    continue
                m = re.match(r"^\s{4}(\S[^:]*):\s*(.*)$", raw) if head not in ("Returns",) else None
                if m and not raw.startswith("        "):
                    if cur_name is not None:
                        items.append((cur_name, " ".join(cur_desc).strip()))
                    cur_name, cur_desc = m.group(1).strip(), [m.group(2)]
                else:
                    cur_desc.append(raw.strip())
                i += 1
            if cur_name is not None:
                items.append((cur_name, " ".join(cur_desc).strip()))
            if head in ("Args", "Arguments"):
                out["args"] = items
            elif head == "Returns":
                out["returns"] = " ".join(d for d in cur_desc).strip()
            elif head == "Raises":
                out["raises"] = items
            elif head == "Attributes":
                out["attributes"] = items
            continue
        free.append(ln)
        i += 1
    paras = [p.strip().replace("\n", " ") for p in "\n".join(free).split("\n\n") if p.strip()]
    if paras:
        out["summary"], out["body"] = paras[0], paras[1:]
    return out


# ----------------------------------------------------------------------------- rendering helpers
def e(s: object) -> str:
    return html.escape(str(s))


def rich(s: str) -> str:
    """Escape, then turn ``code`` spans into <code>."""
    return re.sub(r"``([^`]+)``", r"<code>\1</code>", e(s))


def docinfo(obj) -> dict:
    d = inspect.getdoc(obj) or ""
    if isinstance(obj, type) and (d.startswith(obj.__name__ + "(") or d.startswith("Usage docs: https://docs.pydantic")):
        d = ""                         # a dataclass or pydantic model without its own docstring: skip the generated one
    if isinstance(obj, type) and any(d == (inspect.getdoc(b) or "") for b in obj.__mro__[1:]):
        d = ""                         # inherited from list / str / Exception: not about this class
    return parse_doc(d)


def badges(obj, name: str = "") -> str:
    out = []
    d = inspect.getdoc(obj) or ""
    if "PROPOSED" in d or "proposal" in d.lower() or "does not exist yet" in d.lower():
        out.append('<span class="b warn" title="Needs something the Space or Hub API does not have today">proposed</span>')
    if name.startswith("_simulate"):
        out.append('<span class="b mute" title="Exists only in this mock">mock only</span>')
    if "experimental" in d.lower():
        out.append('<span class="b info" title="The MPP rail is experimental">experimental</span>')
    return " ".join(out)


def anno(a) -> str:
    if a is inspect.Parameter.empty or a is inspect.Signature.empty:
        return ""
    s = a if isinstance(a, str) else (getattr(a, "__name__", None) if isinstance(a, type) else None) or str(a)
    s = re.sub(r"\b(syfthub\.[a-z_.]+\.|typing\.|decimal\.)", "", s).replace("NoneType", "None")
    return e(s.strip("'\""))


def signature(fn) -> tuple[str, str, list[tuple[str, str, str | None]]]:
    """(parameter list as text, return type, rows of (name, type, default or None))."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return "(…)", "", []
    parts, rows, star_done = [], [], False
    for p in sig.parameters.values():
        if p.name in ("self", "cls"):
            continue
        if p.kind is p.VAR_POSITIONAL:
            parts.append(f"*{p.name}"); rows.append((f"*{p.name}", anno(p.annotation), None)); star_done = True
            continue
        if p.kind is p.VAR_KEYWORD:
            parts.append(f"**{p.name}"); rows.append((f"**{p.name}", anno(p.annotation), None))
            continue
        if p.kind is p.KEYWORD_ONLY and not star_done:
            parts.append("*"); star_done = True
        dflt = None if p.default is p.empty else repr(p.default)
        parts.append(p.name + (f"={dflt}" if dflt is not None else ""))
        rows.append((p.name, anno(p.annotation), dflt))
    return "(" + ", ".join(parts) + ")", anno(sig.return_annotation), rows


def example(key: str) -> str:
    code = EX.get(key)
    if not code:
        return ""
    return f'<div class="ex"><div class="ex-label">Example</div><pre><code>{e(code)}</code></pre></div>'


def params_table(rows, args: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    desc = {n: d for n, d in args}
    desc.update({f"*{n}": d for n, d in args if not n.startswith("*")})
    desc.update({f"**{n}": d for n, d in args if not n.startswith("*")})
    desc.update({n.lstrip("*"): d for n, d in args})
    trs = []
    for n, t, dflt in rows:
        text = desc.get(n) or desc.get(n.lstrip("*")) or ""
        if dflt is None and not n.startswith("*"):
            tail = '<span class="req">required</span>'
        elif dflt is None:
            tail = ""
        else:
            tail = f'<span class="dflt">Default <code>{e(dflt)}</code></span>'
        trs.append(f"<tr><td><code>{e(n)}</code></td><td class=t>{t or ''}</td><td>{rich(text)} {tail}</td></tr>")
    return ('<table class="params"><thead><tr><th>Parameter</th><th>Type</th><th>What it is</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>')


def member_block(label: str, name: str, obj, kind: str) -> str:
    key = f"{label}.{name}"
    if kind == "property":
        fget = obj.fget
        ret = anno(inspect.signature(fget).return_annotation) if fget else ""
        info = docinfo(fget)
        head = f'<b>{e(name)}</b>' + (f'<span class="t"> : {ret}</span>' if ret else "")
        body = f"<p>{rich(info['summary'])}</p>" + "".join(f"<p>{rich(p)}</p>" for p in info["body"])
        extra = ""
        if info["raises"]:
            extra += "<p class=\"raises\">Raises " + "; ".join(f"<code>{e(n)}</code> {rich(d)}" for n, d in info["raises"]) + "</p>"
        return f'<div class="member" id="{e(key)}"><div class="sig">{head} {badges(fget, name)}</div>{body}{extra}{example(key)}</div>'

    fn = obj.__func__ if isinstance(obj, (staticmethod, classmethod)) else obj
    params, ret, rows = signature(fn)
    info = docinfo(fn)
    if name == "__call__":
        head = f"<b>{e(label)}</b>{e(params)}"
    elif name == "__add__":
        head = f"<b>{e(label).lower()} + other</b>"
        rows = []
    elif name == "__getitem__":
        head = f"<b>{e(label).lower()}[key]</b>"
    else:
        head = f"<b>{e(name)}</b>{e(params)}"
    k = {"staticmethod": "static method", "classmethod": "class method", "function": "function"}.get(kind, "")
    if inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn):
        k = (k + " async").strip()
        head = "await " + head if not inspect.isasyncgenfunction(fn) else "async for … in " + head
    klabel = f'<span class="k">{k}</span>' if k else ""
    out = [f'<div class="member" id="{e(key)}"><div class="sig">{klabel}{head}'
           f'{(" <span class=t>→ " + ret + "</span>") if ret else ""} {badges(fn, name)}</div>']
    out.append(f"<p>{rich(info['summary'])}</p>")
    out += [f"<p>{rich(p)}</p>" for p in info["body"]]
    out.append(params_table(rows, info["args"]))
    if info["returns"]:
        out.append(f'<p class="returns"><b>Returns</b> {rich(info["returns"])}</p>')
    if info["raises"]:
        out.append('<p class="raises"><b>Raises</b> ' + "; ".join(f"<code>{e(n)}</code> {rich(d)}" for n, d in info["raises"]) + "</p>")
    out.append(example(key))
    out.append("</div>")
    return "".join(out)


def source_notes(cls) -> dict[str, str]:
    """Inline ``# comments`` next to fields or enum members in the class source."""
    try:
        src = inspect.getsource(cls)
    except (OSError, TypeError):
        return {}
    notes = {}
    for m in re.finditer(r"^\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:=][^\n#]*#\s*(.*)$", src, flags=re.M):
        notes[m.group(1)] = m.group(2).strip()
    return notes


def class_section(cls) -> str:
    label = ALIAS.get(cls, cls.__name__)
    anchor = label.replace(".", "-")
    info = docinfo(cls)
    head = f'<section class="cls" id="{anchor}"><h3>{e(label)}</h3>'
    if inspect.isfunction(cls):                       # syfthub.Hub
        block = member_block("syfthub", cls.__name__, cls, "function")
        block = block.replace(f'id="syfthub.{cls.__name__}"', f'id="{anchor}"')
        return head + block.replace('<div class="member"', '<div class="member solo"', 1) + "</section>"
    intro = (f'<p class="summary">{rich(info["summary"])}</p>' if info["summary"] else "") + \
            "".join(f"<p>{rich(p)}</p>" for p in info["body"])
    body = [intro]
    attrs = dict(info["attributes"])
    notes = source_notes(cls)

    if isinstance(cls, type) and issubclass(cls, enum.Enum):
        trs = "".join(f"<tr><td><code>{e(m.value)}</code></td><td>{rich(attrs.get(m.name) or notes.get(m.name, ''))}</td></tr>"
                      for m in cls)
        body.append(f'<table class="params"><thead><tr><th>Value</th><th>Meaning</th></tr></thead><tbody>{trs}</tbody></table>')
        body.append(example(label))
        props = [(n, v) for n, v in vars(cls).items() if isinstance(v, property)]
        if props:
            body.append("<h4>Attributes</h4>" + "".join(member_block(label, n, v, "property") for n, v in props))
        return head + "".join(body) + "</section>"

    if isinstance(cls, type) and issubclass(cls, BaseException):
        if attrs:
            trs = "".join(f"<tr><td><code>{e(n)}</code></td><td>{rich(d)}</td></tr>" for n, d in attrs.items())
            body.append(f'<table class="params"><thead><tr><th>Attribute</th><th>What it holds</th></tr></thead><tbody>{trs}</tbody></table>')
        body.append(example(label))
        return head + "".join(body) + "</section>"

    if dataclasses.is_dataclass(cls):
        trs = []
        for f in dataclasses.fields(cls):
            if f.name.startswith("_"):
                continue
            if f.default is not dataclasses.MISSING:
                dflt = f'<span class="dflt">Default <code>{e(repr(f.default))}</code></span>'
            elif f.default_factory is not dataclasses.MISSING:
                dflt = '<span class="dflt">Default: empty</span>'
            else:
                dflt = ""
            text = attrs.get(f.name) or notes.get(f.name, "")
            trs.append(f"<tr><td><code>{e(f.name)}</code></td><td class=t>{anno(f.type)}</td><td>{rich(text)} {dflt}</td></tr>")
        if trs:
            body.append('<h4>Fields</h4><table class="params"><thead><tr><th>Field</th><th>Type</th><th>What it holds</th></tr></thead>'
                        f'<tbody>{"".join(trs)}</tbody></table>')
    elif isinstance(cls, type) and issubclass(cls, BaseModel):
        trs = []
        for fname, f in cls.model_fields.items():
            if f.is_required():
                dflt = ""
            elif f.default_factory is not None:
                dflt = '<span class="dflt">Default: empty</span>'
            else:
                dflt = f'<span class="dflt">Default <code>{e(repr(f.default))}</code></span>'
            text = attrs.get(fname) or notes.get(fname, "")
            trs.append(f"<tr><td><code>{e(fname)}</code></td><td class=t>{anno(f.annotation)}</td><td>{rich(text)} {dflt}</td></tr>")
        if trs:
            body.append('<h4>Fields</h4><table class="params"><thead><tr><th>Field</th><th>Type</th><th>What it holds</th></tr></thead>'
                        f'<tbody>{"".join(trs)}</tbody></table>')
    elif attrs:
        trs = "".join(f"<tr><td><code>{e(n)}</code></td><td>{rich(d)}</td></tr>" for n, d in attrs.items())
        body.append(f'<h4>Attributes</h4><table class="params"><thead><tr><th>Attribute</th><th>What it holds</th></tr></thead><tbody>{trs}</tbody></table>')

    body.append(example(label))

    props, methods, hooks = [], [], []
    for n, v in vars(cls).items():
        if n in ("__add__", "__getitem__", "__call__"):
            methods.append((n, v, "method"))
        elif n.startswith("_simulate"):
            hooks.append((n, v, "method"))
        elif n.startswith("_"):
            continue
        elif isinstance(v, property):
            props.append((n, v))
        elif n.startswith("model_"):
            continue                                   # pydantic plumbing
        elif isinstance(v, (staticmethod, classmethod)):
            methods.append((n, v, type(v).__name__))
        elif inspect.isfunction(v):
            methods.append((n, v, "method"))
    if props:
        body.append("<h4>Attributes</h4>" + "".join(member_block(label, n, v, "property") for n, v in props))
    if methods:
        body.append("<h4>Methods</h4>" + "".join(member_block(label, n, v, k) for n, v, k in methods))
    if hooks:
        body.append('<h4>Mock hooks</h4><p class="m">Stand-ins for things that happen outside the SDK in real life, '
                    "such as a user paying an invoice.</p>" + "".join(member_block(label, n, v, k) for n, v, k in hooks))
    return head + "".join(body) + "</section>"


CSS = """
:root{--bg:#fff;--fg:#1f2328;--mute:#59636e;--line:#d8dee4;--soft:#f6f8fa;--card:#fff;--accent:#0969da;
--warn-bg:#fff8c5;--warn-fg:#7d4e00;--info-bg:#ddf4ff;--info-fg:#0550ae;--mute-bg:#eaeef2;--code:#f6f8fa;--req:#b35900}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0d1117;--fg:#e6edf3;--mute:#9198a1;--line:#30363d;--soft:#161b22;--card:#0d1117;--accent:#58a6ff;
--warn-bg:#3b2e00;--warn-fg:#e3b341;--info-bg:#0c2d6b;--info-fg:#79c0ff;--mute-bg:#21262d;--code:#161b22;--req:#f0a35b}}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--mute:#9198a1;--line:#30363d;--soft:#161b22;--card:#0d1117;--accent:#58a6ff;
--warn-bg:#3b2e00;--warn-fg:#e3b341;--info-bg:#0c2d6b;--info-fg:#79c0ff;--mute-bg:#21262d;--code:#161b22;--req:#f0a35b}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
code{font-size:.9em;background:var(--mute-bg);padding:1px 5px;border-radius:4px}
pre{background:var(--code);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow:auto;font-size:13px;line-height:1.55;margin:0}
pre code{background:none;padding:0;font-size:inherit}

.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100vh}
nav{border-right:1px solid var(--line);padding:24px 18px 40px;position:sticky;top:0;height:100vh;overflow:auto;background:var(--soft)}
nav .brand{font-weight:700;font-size:17px}nav .ver{color:var(--mute);font-size:12px;margin:2px 0 18px}
nav h5{margin:18px 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
nav h5 a{color:var(--mute)}
nav a{display:block;padding:3px 0;font-size:13.5px;color:var(--fg)}nav a.sub{padding-left:12px;color:var(--mute)}nav a.sub:hover{color:var(--fg)}
main{padding:36px 56px 120px;max-width:900px}

h1{font-size:30px;line-height:1.2;margin:0 0 10px}
h1 small{display:block;font-size:15px;font-weight:400;color:var(--mute);margin-top:6px}
h2{font-size:22px;margin:64px 0 6px;padding-top:28px;border-top:1px solid var(--line)}
h2:first-of-type{margin-top:40px}
h3{font-size:19px;margin:0 0 4px}
h4{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:30px 0 10px}
p{margin:8px 0}.m{color:var(--mute)}
.lead{color:var(--mute);font-size:16px;margin:0 0 24px}
.rules{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0 8px}
.rule{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.rule b{display:block;margin-bottom:4px}.rule p{margin:0;color:var(--mute);font-size:14px}

section.cls{margin:34px 0 0;padding:26px 28px 24px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
section.cls .summary{font-size:16px;color:var(--mute);margin:0 0 8px}
.member{padding:20px 0 4px;margin:0;border-top:1px solid var(--line)}
.member:first-of-type{border-top:none}
h4 + .member{border-top:none;padding-top:4px}
.member.solo{border-top:none;padding-top:8px}
.sig{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:14.5px;line-height:1.5;margin-bottom:8px;word-break:break-word}
.sig b{font-weight:700}.sig .k{display:inline-block;color:var(--mute);font-size:11px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
text-transform:uppercase;letter-spacing:.06em;margin-right:10px;vertical-align:middle;position:relative;top:-1px}
.sig .t{color:var(--mute)}
.member p{margin:8px 0}
.returns,.raises{margin-top:10px}
.b{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;margin-left:6px;vertical-align:middle;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;background:var(--mute-bg);color:var(--mute)}
.warn{background:var(--warn-bg);color:var(--warn-fg)}.info{background:var(--info-bg);color:var(--info-fg)}

table{border-collapse:collapse;margin:12px 0 6px;width:100%;font-size:14px}
th,td{text-align:left;vertical-align:top;padding:8px 12px 8px 0;border-bottom:1px solid var(--line)}
th{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);font-weight:600}
td.t{color:var(--mute);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;white-space:nowrap}
td code{white-space:nowrap}
.req{color:var(--req);font-size:12px;margin-left:6px}.dflt{color:var(--mute);font-size:12.5px;margin-left:6px;white-space:nowrap}
.dflt code{font-size:12px}

.ex{margin:14px 0 8px}
.ex-label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin-bottom:6px}
.tour pre{padding:18px 20px}

@media (max-width:900px){.wrap{grid-template-columns:1fr}nav{position:static;height:auto;border-right:none;border-bottom:1px solid var(--line)}
main{padding:24px 16px 80px}section.cls{padding:18px 16px}.rules{grid-template-columns:1fr}td.t{white-space:normal}}
"""


def build() -> str:
    nav, body = [], []
    for title, lead, members in GROUPS:
        gid = "g-" + re.sub(r"[^a-z]+", "-", title.lower()).strip("-")
        nav.append(f'<h5><a href="#{gid}">{e(title)}</a></h5>')
        body.append(f'<h2 id="{gid}">{e(title)}</h2><p class="lead">{e(lead)}</p>')
        for cls in members:
            label = ALIAS.get(cls, cls.__name__)
            nav.append(f'<a class="sub" href="#{label.replace(".", "-")}">{e(label)}</a>')
            body.append(class_section(cls))
    verbs = "".join(f"<tr><td><code>{e(v)}</code></td><td>{e(w)}</td><td>{e(d)}</td></tr>" for v, w, d in VERBS)
    intro = f"""
<h1>SyftHub Python SDK<small>Reference for the v2 design · mock {e(syfthub.__version__)}</small></h1>
<p class="lead">Everything the SDK exposes, with a short example for each thing you can call. Start with the tour
if you are new; use the sidebar to jump to a class.</p>
<div class="rules">
  <div class="rule"><b>Compose, then execute</b><p>A search or a chat first shows what it will cost and what is held back.
  Nothing is sent until you say so.</p></div>
  <div class="rule"><b>Rows, not exceptions</b><p>Each source comes back returned, held, rejected, failed or waiting on a
  payment, with the fix attached. The outcome says who stopped the call.</p></div>
  <div class="rule"><b>Immutable results, one mutable room</b><p>Every method on <code>Results</code> returns a new one; the raw
  responses are never changed. A <code>Chat</code> mutates in place and <code>fork()</code> branches it.</p></div>
</div>
<p class="m">This page is generated from the package by <code>build_docs.py</code>. The examples are the ones the
<a href="../flows.ipynb">flows</a>, <a href="../story.ipynb">story</a> and <a href="../advanced.ipynb">advanced</a> notebooks run.
Async methods are shown with <code>await</code>; the synchronous <code>syfthub.Hub</code> has the same methods without it.</p>

<h2 id="tour">Quick tour</h2>
<p class="lead">The whole flow in one screen: shortlist, search, pay, read, chat. Compose is free and synchronous; the network is awaited.</p>
<div class="tour"><pre><code>{e(TOUR)}</code></pre></div>

<h2 id="verbs">Verbs at a glance</h2>
<p class="lead">The handful of verbs you will use most, and where they live.</p>
<table class="params"><thead><tr><th>Verb</th><th>Lives on</th><th>What it does</th></tr></thead><tbody>{verbs}</tbody></table>
<p class="m" style="margin-top:16px">Badges on this page: <span class="b warn">proposed</span> needs something the Space or Hub API
does not have today. <span class="b info">experimental</span> marks the MPP rail. <span class="b">mock only</span> exists only in this mock.</p>
"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SyftHub SDK reference</title><style>{CSS}</style></head><body><div class="wrap">
<nav><div class="brand">syfthub</div><div class="ver">Python SDK v2 · mock {e(syfthub.__version__)}</div>
<a href="#tour">Quick tour</a><a href="#verbs">Verbs at a glance</a>{"".join(nav)}</nav>
<main>{intro}{"".join(body)}</main></div></body></html>"""


def check() -> list[str]:
    """Members on the page without an example, and example keys that match nothing."""
    keys = set()
    for _, _, members in GROUPS:
        for cls in members:
            label = ALIAS.get(cls, cls.__name__)
            keys.add(label)
            if inspect.isfunction(cls) or cls in RELAXED:
                continue
            for n, v in vars(cls).items():
                public = (not n.startswith("_") and not n.startswith("model_")) or n in ("__add__", "__getitem__", "__call__")
                if public and (isinstance(v, property) or inspect.isfunction(v) or isinstance(v, (staticmethod, classmethod))):
                    keys.add(f"{label}.{n}")
    problems = [f"no example: {k}" for k in sorted(keys - set(EX))]
    problems += [f"unused example: {k}" for k in sorted(set(EX) - keys)]
    return problems


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    page = build()
    OUT.write_text(page + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(Path(__file__).parent)}: {OUT.stat().st_size // 1024} KB, "
          f"{page.count('<section')} sections, {page.count('class=\"member\"') + page.count('class=\"member solo\"')} members, "
          f"{len(EX)} examples")
    for p in check():
        print("  ", p)
