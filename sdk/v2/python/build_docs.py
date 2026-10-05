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

import syfthub
from syfthub import errors as E
from syfthub import hub as H
from syfthub import models as M
from syfthub import results as R
from syfthub import search as S

OUT = Path(__file__).parent / "docs" / "index.html"

# ----------------------------------------------------------------------------- what goes on the page
GROUPS = [
    ("Connect", "Open a session and sign in.",
     [H.connect, H.Hub, H._Login, M.Identity, M.Budget]),
    ("Browse", "Find endpoints on the Hub and shortlist them.",
     [M.Selection, M.Endpoint, M.Policy, M.Pricing, M.Connection]),
    ("Search", "Compose a search, review what it will cost, pay what is short, then send it.",
     [S.Search, S.SearchRow]),
    ("Results", "What came back, one row per source, and what you can do with it.",
     [R.Results, M.SourceResult, M.Document, M.Answer]),
    ("Chat", "Talk to one or more models about your results.",
     [R.Chat, R.Replies, R.Reply, R.Context]),
    ("Wallets and payment", "Prepaid credits, and what to do when a wallet runs short.",
     [M.Wallets, M.Wallet, M.TopUp, M.Charge]),
    ("Outcomes", "The states a source or a reply can end up in.",
     [M.Outcome, M.SkipReason, M.Rail]),
    ("Errors", "Raised only for mistakes in how the SDK is called. Payment problems are never exceptions.",
     [E.SyftHubError, E.NotLoggedIn, E.BudgetExceeded, E.RunNotReady, E.NothingToRun]),
]

# Display names for things you reach through an attribute rather than by class name.
ALIAS = {H._Login: "hub.login", H.connect: "syfthub.connect"}

# Hand-written examples, keyed "Label.member", or "Label" for the type itself.
EX = {
"syfthub.connect": '''import syfthub

hub = syfthub.connect("https://hub.example.com")

# In a notebook, render payment decisions as widgets with buttons
hub = syfthub.connect("https://hub.example.com", interactive=True)''',
"hub.login": '''hub.login(username="alice", password="secret")
hub.login.google()
hub.login.token("syft_pat_...")''',
"hub.login.__call__": 'hub.login(username="alice", password="secret")',
"hub.login.google": '''# Opens the browser; returns once the Hub confirms
hub.login.google()''',
"hub.login.token": 'hub.login.token("syft_pat_...")',
"Hub": '''hub = syfthub.connect("https://hub.example.com")
hub.login(username="alice", password="secret")
hub.browse()''',
"Hub.whoami": '''me = hub.whoami()
me.username, me.hub_wallet_balance
# -> ('alice', 1.0)''',
"Hub.set_budget": '''# Hold any source that would push this session past 2 USD
hub.set_budget(2.00)''',
"Hub.browse": '''# Everything, with a pricing column
hub.browse()

# Only free data sources
hub.browse(type="data_source", free=True)

# Fuzzy, typo-tolerant match on name, description and tags
hub.browse(matching="trial adverse events")''',
"Hub.find": '''# Semantic search on the Hub itself, for a Hub too large to browse
hub.find("adverse events in oncology trials")''',
"Hub.get": '''ep = hub.get("dave/notes")
ep.pricing.label()
# -> '$0.02/document via xendit\'''',
"Hub.wallets": '''# Every prepaid wallet behind what you can see, with balances
hub.wallets()

# Just the wallets behind a shortlist
hub.wallets(picked)''',
"Hub.wallet": '''hub.wallet("dave/notes").balance
# -> 0.0''',
"Hub.balance": '''hub.balance("dave/notes")
# -> 0.0''',
"Hub.search": '''search = hub.search(
    "What adverse events were reported in phase 3 trials?",
    sources=picked,
    limit=5,
)
# Shows the pre-flight table. Nothing has been sent.
search''',
"Hub.chat": '''# Search these two sources before every message, then ask the model
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"])
live.filter(published_gte="2024-01-01").top(4)
live.send("How many deaths were reported?")''',
"Hub._simulate_checkout_paid": '''topup = search.top_up("dave/notes", bundle="starter")
# Stands in for: the user pays at topup.checkout_url and the webhook credits the wallet
hub._simulate_checkout_paid(topup.invoice["id"])''',
"Hub._simulate_space_up": 'hub._simulate_space_up("grace/archive")',
"Identity": '''me = hub.whoami()
me.auth
# -> 'password\'''',
"Budget": '''budget = hub.set_budget(2.00)
budget.remaining
# -> 2.0''',
"Budget.remaining": '''hub.budget.remaining
# -> 1.85''',
"Selection": '''picked = hub.browse().matching("trial adverse events").filter(type="data_source")
picked.paths
# -> ['carol/papers', 'erin/trials', 'frank/registry']''',
"Selection.filter": 'hub.browse().filter(type="data_source", free=True)',
"Selection.matching": 'hub.browse().matching("trial adverse events")',
"Selection.pick": 'hub.browse().pick("dave/notes", "olga/trials-assistant")',
"Selection.__add__": '''picked = (
    hub.browse().matching("trial adverse events").filter(type="data_source")
    + hub.browse().pick("dave/notes", "olga/trials-assistant")
)''',
"Selection.paths": '''picked.paths
# -> ['carol/papers', 'erin/trials', 'dave/notes', 'olga/trials-assistant']''',
"Endpoint": '''ep = hub.get("dave/notes")
ep.type, ep.pricing.label(), ep.filterable
# -> ('data_source', '$0.02/document via xendit', ())''',
"Endpoint.path": '''hub.get("dave/notes").path
# -> 'dave/notes\'''',
"Endpoint.url": '''hub.get("dave/notes").url
# -> 'https://dave.spaces.example\'''',
"Endpoint.pricing": '''hub.get("dave/notes").pricing.label()
# -> '$0.02/document via xendit\'''',
"Policy": '''for p in hub.get("dave/notes").policies:
    print(p.type, p.enabled, p.config.get("price"))''',
"Policy.is_payment": '[p for p in ep.policies if p.is_payment]',
"Pricing": '''pricing = hub.get("dave/notes").pricing
pricing.rail, pricing.price, pricing.unit, pricing.currency
# -> (<Rail.XENDIT: 'xendit'>, 0.02, 'document', 'USD')''',
"Pricing.paid": '''hub.get("heidi/shared-corpus").pricing.paid
# -> False''',
"Pricing.label": '''ep.pricing.label()
# -> '$0.02/document via xendit\'''',
"Pricing.from_policies": 'Pricing.from_policies(list(ep.policies))',
"Connection": '''hub.get("dave/notes").connect[0].config["url"]
# -> 'https://dave.spaces.example\'''',
"Search": '''search = hub.search("What adverse events were reported?", sources=picked)
search.total_estimate, [r.endpoint.path for r in search.held]
# -> ({'USD': 0.15}, ['dave/notes'])''',
"Search.filter": '''# Date filters go to the Spaces that support them; the author filter is applied here
search.filter(published_gte="2024-06-01", author="R. Chitrakoot")

# The pre-flight table now has a filters column: "at the Space" or "here, after limit"
search''',
"Search.filters_for": '''to_space, here = search.filters_for(search.rows[0])
to_space, here
# -> ({'published_gte': '2024-06-01'}, {'author': 'R. Chitrakoot'})''',
"Search.pending": '''for topup in search.pending:
    print(topup.wallet.key, topup.needed, topup.waiting)''',
"Search.sending": '''[r.endpoint.path for r in search.sending]
# -> ['carol/papers', 'erin/trials']''',
"Search.held": '''[(r.endpoint.path, r.verdict) for r in search.held]
# -> [('dave/notes', 'needs credits')]''',
"Search.top_up": '''topup = search.top_up("dave/notes", bundle="starter")
# Pay here; the Space's webhook credits the wallet
topup.checkout_url''',
"Search.refresh": '''# After paying, run pre-flight again
search.refresh()''',
"Search.execute": '''results = search.execute()
results.ok_count, results.cost
# -> (4, {'USD': 0.13})''',
"Search.total_estimate": '''search.total_estimate
# -> {'USD': 0.15, 'IDR': 300.0}''',
"SearchRow": '''row = search.rows[0]
row.endpoint.path, row.estimate, row.verdict, row.send
# -> ('carol/papers', 0.05, 'ready', True)''',
"Results": '''results = search.execute()
results                      # one row per source, with outcome and cost
results["erin/trials"]       # one source in detail''',
"Results.__getitem__": '''results["erin/trials"].documents
results[0].cost''',
"Results.filter": '''# A view: the raw responses are untouched
recent = results.filter(published_gte="2024-01-01")''',
"Results.only": 'recent.only("erin/trials", "olga/trials-assistant")',
"Results.drop": 'results.drop("frank/registry")',
"Results.top": '''# The three best passages across every source
results.top(3)''',
"Results.__add__": '''more = hub.search("infection-related SAEs", sources=["heidi/shared-corpus"]).execute()
# Add the new evidence to a running chat
chat.use(chat.view + more)''',
"Results.documents": '''for path, doc in results.documents:
    print(path, round(doc.similarity_score, 2), doc.content[:60])''',
"Results.paths": '''results.paths
# -> ['carol/papers', 'erin/trials', 'dave/notes', 'olga/trials-assistant']''',
"Results.ok_count": '''results.ok_count
# -> 3''',
"Results.skipped": '''[(r.endpoint.path, r.reason) for r in results.skipped]
# -> [('dave/notes', <SkipReason.NO_CREDITS: 'no_credits'>)]''',
"Results.pending": '''for action in results.pending:
    print(type(action).__name__, action.endpoint.path)''',
"Results.spent": '''results.spent
# -> 0.13''',
"Results.charges": '''results.charges
# -> [{'policy': 'xendit', 'amount': 0.05, 'currency': 'USD', ...}, ...]''',
"Results.cost": '''results.cost
# -> {'USD': 0.13}''',
"Results.answers": '''results.answers
# -> {'olga/trials-assistant': 'Across the three trials ...'}''',
"Results.returns": '''results.returns
# -> 'both\'''',
"Results.raw": '''results.raw["erin/trials"]["policy_metadata"]''',
"Results.top_up": '''# After execute, for a row the Space rejected for credits
results.top_up("dave/notes", bundle="starter")
# ...pay at the checkout URL, then:
results.retry()''',
"Results.retry": '''# Re-send what was skipped for no credits, over budget, unreachable or rate limited
results.retry()''',
"Results.approve": '''# MPP only: pay the pending challenges from your Hub wallet and re-send
results.approve()''',
"Results.proceed": '''# Send the rows that were held as over budget
results.proceed()''',
"Results.skip": '''# Mark a row as skipped by you; retry() leaves it alone
results.skip("kim/ledger")''',
"Results.chat": '''chat = recent.chat("ivan/gpt-mini")

# Or a room with two models answering side by side
room = recent.chat(["ivan/gpt-mini", "bob/llama-3"])''',
"Results.ask": '''# One question, one answer, no thread kept
reply = recent.ask("bob/llama-3", "Summarise the serious adverse events.")
reply.text''',
"Results.aggregate": '''# Via the Aggregator: rerank the passages, then generate one answer
answer = results.aggregate("bob/llama-3")
answer.text, answer.citations''',
"SourceResult": '''r = results["erin/trials"]
r.ok, len(r.documents), r.cost, r.currency
# -> (True, 5, 0.05, 'USD')''',
"SourceResult.ok": 'results["erin/trials"].ok',
"SourceResult.all_documents": '''# Everything the Space returned, before filter() or top()
len(results["erin/trials"].all_documents)''',
"SourceResult.documents": '''for doc in recent["erin/trials"].documents:
    print(doc.metadata["published"], doc.content[:60])''',
"SourceResult.returns": '''results["olga/trials-assistant"].returns
# -> 'summary\'''',
"SourceResult.summary": 'results["olga/trials-assistant"].summary',
"SourceResult.cost": '''results["erin/trials"].cost
# -> 0.05''',
"SourceResult.currency": '''results["erin/trials"].currency
# -> 'USD\'''',
"SourceResult.policy_metadata": '''results["erin/trials"].policy_metadata["entries"]''',
"SourceResult.detail": '''results["dave/notes"].detail
# -> 'Insufficient credits: balance 0.00, needs 0.10\'''',
"SourceResult.skipped": '[r.endpoint.path for r in results if r.skipped]',
"Document": '''path, doc = results.documents[0]
doc.similarity_score, doc.metadata.get("published")
# -> (0.91, '2024-03-02')''',
"Answer": '''answer = results.aggregate("bob/llama-3")
answer.text
answer.citations
# -> {1: 'erin/trials', 2: 'carol/papers'}''',
"Chat": '''chat = recent.chat("ivan/gpt-mini")
chat                          # price per message, your balance, the transcript
chat.send("Summarise the serious adverse events.")
chat.send("Were any of them fatal?")
chat.spent
# -> {'USD': 0.02}''',
"Chat.send": '''replies = chat.send("Were any of them fatal?")

# One model in the room: read the answer directly
replies.text

# Several models: pick the tab
replies["bob/llama-3"].text''',
"Chat.context": '''# Earlier turns per model, then the passages, each with a token count
chat.context''',
"Chat.use": '''# Narrow what the models see to three passages from two sources
chat.use(recent.only("erin/trials", "olga/trials-assistant").top(3))

# Add new evidence mid-conversation
chat.use(chat.view + more)''',
"Chat.add": '''# Joins from the next message on, briefed with the lead model's transcript
chat.add("bob/llama-3")

# Joins with only the passages, no briefing
chat.add("lena/sahabat-ai", brief=False)''',
"Chat.remove": '''# Its tab stays readable; it is not asked again
chat.remove("ivan/gpt-mini")''',
"Chat.top_up": '''# One model is short: no need to name it
topup = chat.top_up(bundle="starter")

# Several could be: say which
topup = chat.top_up("ivan/gpt-mini", bundle="starter")''',
"Chat.reset": '''# Drop every model's turns; the passages and pre-flights stay
chat.reset()''',
"Chat.filter": '''# On a chat that searches every message, the filter travels with each search
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"])
live.filter(published_gte="2024-01-01")''',
"Chat.only": 'chat.only("erin/trials", "olga/trials-assistant")',
"Chat.drop": 'chat.drop("frank/registry")',
"Chat.top": 'chat.top(3)',
"Chat.spent": '''chat.spent
# -> {'USD': 0.04, 'IDR': 600.0}''',
"Chat.spent_by": '''chat.spent_by("lena/sahabat-ai")
# -> {'IDR': 600.0}''',
"Chat.view": '''# The Results the passages come from
chat.view''',
"Chat.history": '''# Share the thread with the Spaces, explicitly
hub.search("Were any fatal?", sources=picked, history=chat.history)''',
"Chat.last": '''chat.last.text''',
"Chat.turn": '''chat.turn
# -> 4''',
"Chat.model": '''chat.model.path
# -> 'ivan/gpt-mini\'''',
"Chat.endpoint": 'chat.endpoint("bob/llama-3").pricing.label()',
"Chat.refresh": '''# After paying, check balances again
chat.refresh()''',
"Chat.rows": '''{path: row.verdict for path, row in chat.rows.items()}
# -> {'ivan/gpt-mini': 'ready', 'bob/llama-3': 'ready'}''',
"Chat.row": '''chat.row.verdict
# -> 'ready\'''',
"Chat.pending": '''[t.wallet.key for t in chat.pending]
# -> ['w-ivan-stripe-usd']''',
"Replies": '''replies = room.send("Do you agree, and what would you add?")
replies.models
# -> ['ivan/gpt-mini', 'bob/llama-3']
replies["bob/llama-3"].text''',
"Replies.__getitem__": '''replies["bob/llama-3"]
replies[0]''',
"Replies.models": '''replies.models
# -> ['ivan/gpt-mini', 'bob/llama-3']''',
"Replies.text": '''# One model in the room
replies.text

# Several models: this raises; index by model path instead
replies["bob/llama-3"].text''',
"Replies.citations": '''replies.citations
# -> {1: 'erin/trials', 3: 'carol/papers'}''',
"Replies.reason": '''replies.reason
# -> <SkipReason.NO_CREDITS: 'no_credits'>''',
"Replies.ok": '''replies.ok
# -> True''',
"Replies.context": '''replies.context.tokens
# -> 1240''',
"Replies.pending": '''[t.wallet.key for t in replies.pending]''',
"Replies.charges": '''replies.charges
# -> [{'policy': 'stripe', 'amount': 0.01, 'currency': 'USD', ...}]''',
"Replies.cost": '''replies.cost
# -> {'USD': 0.01}''',
"Replies.top_up": '''topup = replies.top_up("ivan/gpt-mini", bundle="starter")
topup.checkout_url''',
"Reply": '''reply = replies["bob/llama-3"]
reply.ok, reply.cost
# -> (True, {'USD': 0.01})''',
"Reply.outcome": '''reply.outcome
# -> <Outcome.SUCCESS: 'success'>''',
"Reply.reason": '''reply.reason
# -> None''',
"Reply.text": 'reply.text',
"Reply.ok": '''if reply.ok:
    print(reply.text)''',
"Reply.pending": '''for topup in reply.pending:
    print(topup.needed, topup.currency)''',
"Reply.charges": 'reply.charges',
"Reply.cost": '''reply.cost
# -> {'USD': 0.01}''',
"Reply.top_up": '''topup = reply.top_up(bundle="starter")
topup.checkout_url''',
"Context": '''ctx = chat.context
ctx.turns, ctx.history_tokens, ctx.source_tokens
# -> (2, 310, 930)''',
"Context.source_tokens": '''chat.context.source_tokens
# -> 930''',
"Context.history_tokens": '''chat.context.history_tokens
# -> 310''',
"Context.tokens": '''chat.context.tokens
# -> 1240''',
"Context.turns": '''chat.context.turns
# -> 2''',
"Context.counts": '''chat.context.counts
# -> {'references': 6, 'summaries': 1}''',
"Wallets": '''wallets = hub.wallets()
wallets["dave/notes"].balance        # by the endpoint it funds
wallets["w-dave-xendit-usd"].balance # by wallet key''',
"Wallets.__getitem__": '''hub.wallets()["dave/notes"]
hub.wallets()["w-dave-xendit-usd"]''',
"Wallet": '''w = hub.wallet("dave/notes")
w.owner, w.type, w.currency, w.balance, w.endpoints
# -> ('dave', <Rail.XENDIT: 'xendit'>, 'USD', 0.0, ('dave/notes', 'dave/imaging'))''',
"Wallet.top_up": '''invoice = hub.wallet("dave/notes").top_up("starter")
invoice["checkout_url"]''',
"Wallet.refresh": 'hub.wallet("dave/notes").refresh().balance',
"TopUp": '''topup = search.pending[0]
topup.needed, topup.currency, [b["id"] for b in topup.bundles]
# -> (0.10, 'USD', ['starter', 'plus'])''',
"TopUp.balance": '''topup.balance
# -> 0.0''',
"TopUp.currency": '''topup.currency
# -> 'USD\'''',
"TopUp.bundles": '''[(b["id"], b["price"]) for b in topup.bundles]
# -> [('starter', 5.0), ('plus', 20.0)]''',
"TopUp.checkout_url": '''# None until a bundle is chosen
topup = search.top_up("dave/notes", bundle="starter")
topup.checkout_url
# -> 'https://dave.spaces.example/pay/inv_...\'''',
"Charge": '''for charge in results.pending:
    print(charge.endpoint.path, charge.amount, charge.currency)''',
"Outcome": '''r = results["dave/notes"]
r.outcome is Outcome.SKIPPED and r.reason is SkipReason.NO_CREDITS
# -> True''',
"SkipReason": '''[(r.endpoint.path, r.reason.value) for r in results.skipped]
# -> [('dave/notes', 'no_credits')]''',
"SkipReason.retryable": '[r for r in results.skipped if r.reason.retryable]',
"Rail": '''ep.pricing.rail
# -> <Rail.XENDIT: 'xendit'>''',
"Rail.prepaid": '''ep.pricing.rail.prepaid
# -> True''',
"SyftHubError": '''try:
    hub.whoami()
except syfthub.SyftHubError as e:
    print(e)''',
"NotLoggedIn": '''try:
    hub.whoami()
except syfthub.NotLoggedIn:
    hub.login(username="alice", password="secret")''',
"BudgetExceeded": '''try:
    results.approve()
except syfthub.BudgetExceeded as e:
    hub.set_budget(e.needed)
    results.approve()''',
"RunNotReady": '''try:
    chat.top_up(bundle="starter")          # two models are short: which one?
except syfthub.RunNotReady as e:
    print(e)                               # "several models are short: name one, ..."''',
"NothingToRun": '''try:
    results.retry()
except syfthub.NothingToRun:
    print("every source is done")''',
}

# Verbs at a glance: (verb, lives on, what it does)
VERBS = [
    ("browse / find / get", "hub", "List endpoints, search the Hub for them, or open one."),
    ("filter", "Selection, Search, Results, Chat", "Narrow by type, owner or tag, or by document metadata. On a Search, the filter is sent to Spaces that support it."),
    ("matching / pick / +", "Selection", "Fuzzy-match, pick by name, combine two lists."),
    ("search, then execute", "hub, Search", "Compose a search and review its pre-flight, then send what passes."),
    ("top_up", "Search, Results, Chat, Wallet", "Buy a credit bundle for a wallet that is short. You get an invoice with a checkout URL."),
    ("retry / approve / proceed / skip", "Results", "Act on skipped rows: re-send them, pay MPP charges, accept going over budget, or drop them."),
    ("only / drop / top / +", "Results", "Views over what came back. The raw responses are never changed."),
    ("chat / ask / aggregate", "Results", "Start a conversation about the results, ask once, or hand them to the Aggregator."),
    ("send", "Chat", "One message to every model in the room. Returns a reply per model."),
    ("use / view / context", "Chat", "See what the next message carries and change which passages it uses."),
    ("add / remove", "Chat", "Change who answers from the next message on."),
    ("reset", "Chat", "Start the thread over, keeping the passages."),
]

TOUR = '''import syfthub

hub = syfthub.connect("https://hub.example.com")
hub.login(username="alice", password="secret")

# Shortlist some sources
picked = (
    hub.browse().matching("trial adverse events").filter(type="data_source")
    + hub.browse().pick("dave/notes", "olga/trials-assistant")
)

# Compose a search. Nothing is sent yet: you see the cost per source and what is held
search = hub.search("What adverse events were reported in phase 3 trials?",
                    sources=picked)
search

# One wallet is short: buy a bundle and pay at topup.checkout_url
topup = search.top_up("dave/notes", bundle="starter")

# Send it. Every source comes back returned, skipped with a reason, or payment required
results = search.execute()
recent = results.filter(published_gte="2024-01-01")

# Talk to a model about the results. Same pre-flight: price per message, your balance.
chat = recent.chat("ivan/gpt-mini")
chat.context                                   # what the next message will carry
chat.send("Summarise the serious adverse events.")

# A second opinion joins from here on, briefed with the transcript so far
chat.add("bob/llama-3")
chat.send("Do you agree, and what would you add?")["bob/llama-3"].text
chat.remove("ivan/gpt-mini")

# Add fresh evidence mid-conversation
more = hub.search("infection-related SAEs", sources=["heidi/shared-corpus"]).execute()
chat.use(chat.view + more)

chat.spent
# -> {'USD': 0.10}'''


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
    if isinstance(obj, type) and d.startswith(obj.__name__ + "("):
        d = ""                         # a dataclass without its own docstring: skip the generated one
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
    s = a if isinstance(a, str) else getattr(a, "__name__", None) or str(a)
    return e(s.replace("typing.", "").strip("'\""))


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
    if inspect.isfunction(cls):                       # syfthub.connect
        block = member_block("syfthub", "connect", cls, "function")
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
  <div class="rule"><b>Payment is a state, not an error</b><p>Each source comes back as returned, skipped with a reason,
  or waiting on a payment, with the fix attached. Nothing raises.</p></div>
  <div class="rule"><b>Views, not copies</b><p><code>filter</code>, <code>only</code>, <code>drop</code>, <code>top</code>
  and <code>+</code> change what you look at. The raw responses stay as the Spaces returned them.</p></div>
</div>
<p class="m">This page is generated from the package by <code>build_docs.py</code>. The examples are the ones the
<a href="../story.ipynb">story</a> and <a href="../advanced.ipynb">advanced</a> notebooks run.</p>

<h2 id="tour">Quick tour</h2>
<p class="lead">The whole flow in one screen: shortlist, search, pay, read, chat.</p>
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
            if inspect.isfunction(cls):
                continue
            for n, v in vars(cls).items():
                public = not n.startswith("_") or n in ("__add__", "__getitem__", "__call__") or n.startswith("_simulate")
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
