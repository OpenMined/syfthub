"""Generate and execute story.ipynb and advanced.ipynb. Run: .venv/bin/python build_notebooks.py"""
import sys
import nbformat as nbf
from nbclient import NotebookClient

md = lambda s: ("md", s)
code = lambda s: ("code", s)

STORY = [
md("""
# Alice asks the hub a question

*A walkthrough of the SyftHub Python SDK, v2, as a mock. Everything below runs against in-memory fakes that return exactly
what the real Hub and Space APIs return. Names, prices and documents are invented.*

Alice is an oncology researcher. She wants to know what adverse events were reported in recent phase 3 trials, across data
other people hold, and then talk it through with a model. She has never used SyftHub before.
"""),
code("""
import syfthub
hub = syfthub.connect("https://hub.example.com")
hub.login(username="alice", password="secret")
"""),
md("""
## What is out there?

She starts by looking. Sources and models are listed together; the pricing column tells her what each one costs before she
touches it, and the policies column flags anything else that might get in the way.
"""),
code("hub.browse()"),
md("""
Too many. She describes what she is after, roughly, and narrows to data sources. Then she adds two by name: Dave's
clinician notes, and Olga's assistant, an endpoint that answers in its own words *and* returns the passages it used.
An endpoint decides what it returns: references, a summary, or both. A search accepts any of them.
"""),
code("""
picked = (hub.browse().matching("trial adverse events").filter(type="data_source")
          + hub.browse().pick("dave/notes", "olga/trials-assistant"))
picked
"""),
md("One of them is paid per document. She looks closer."),
code('hub.get("dave/notes")'),
md("""
## What would this cost?

She writes the question and composes a search over the four sources. **Nothing is sent yet.** The pre-flight table shows
what each call would cost at most, her balance on every wallet involved, and a verdict per source. Dave's notes are held:
she has no credits on his wallet.
"""),
code("""
search = hub.search("What adverse events were reported in phase 3 trials?", sources=picked)
search
"""),
md("""
The card tells her what to do. Credits are bought from Dave's Space; `top_up` returns the checkout link. She pays in the
browser, the provider tells Dave's Space, and the balance is there.
"""),
code("""
topup = search.top_up("dave/notes", bundle="starter")
topup
"""),
code("""
hub._simulate_checkout_paid(topup.invoice["id"])   # mock: Alice pays at the link and the webhook fires
search.refresh()
"""),
md("""
## Run it

`execute()` re-checks pre-flight, then asks every endpoint that passes, in parallel. Each row is what that Space returned:
the **returns** column says whether it was references, a summary, or both. Frank's feed is rate limited today; that could
not be known in advance, so it was sent and came back skipped. The charges table at the bottom is assembled from the
Spaces' own receipts.
"""),
code("""
results = search.execute()
results
"""),
md("She reads what Erin's registry returned, and what it cost."),
code('results["erin/trials"]'),
md("""
## Only recent work

Documents carry whatever metadata their Space attached. She keeps the ones published since 2024. This happens on her
side, over what came back, so it narrows the `limit` she already asked for; if she filtered hard she would raise it.
(The same verb on a search, before executing, can send the filter to the Space instead: see *Advanced use cases*.)
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
chat
"""),
md("""
Before spending anything she looks at exactly what the model will see. No turns yet, so only the passages: in citation
order, with Olga's own answer labelled as hers, so the model can cite a passage or another endpoint's conclusion.
"""),
code("chat.context"),
md("If she sends anyway, nothing goes to Ivan's Space. The reply is the same card, with the same action."),
code("""
chat.send("Summarise the serious adverse events across these sources.")
"""),
code("""
topup = chat.top_up(bundle="starter")
hub._simulate_checkout_paid(topup.invoice["id"])   # mock: paid at the link
chat.send("Summarise the serious adverse events across these sources.")
"""),
md("""
Citations point back to the context above. Now she follows up. The question only makes sense together with the
first turn, so the earlier turns ride along with every message; the reply says which turn this is and what the
conversation has cost so far.
"""),
code("""
chat.send("Were any of them fatal?")
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
chat.send("And in the registry data alone, what stood out?")
"""),
md("The model condenses its own previous answer: history, not context, is doing the work here."),
code("""
chat.send("Put that in two bullets for a slide.")
"""),
md("""
## A second opinion

Ivan is metered and she has paid for every message. Bob's model is free. A chat is a room: she adds Bob, who is
briefed with the questions so far and Ivan's answers, and from here every question goes to both. The card grows a
tab per model, each with its own pre-flight and transcript; the context line and the spend stay shared.
"""),
code("""
chat.add("bob/llama-3")
chat
"""),
code("""
replies = chat.send("Do you agree with those two bullets, and what would you add?")
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
chat.remove("ivan/gpt-mini")
"""),
md("""
## More evidence, mid-conversation

The consortium corpus was not in her search. A search is the same wherever she is: same pre-flight, same cost card.
She adds its results to what the chat already carries and checks the context before asking.
"""),
code("""
more = hub.search("infection-related serious adverse events", sources=["heidi/shared-corpus"]).execute()
more
"""),
code("""
chat.use(chat.view + more)
chat.context
"""),
code("""
chat.send("Does the consortium data change the picture?")
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
live.send("How many deaths were reported, and were they related to treatment?")
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

Not in this story yet: the Aggregator as an optional step, headless use, and `interactive=True` widgets. The code for
those exists; the story will grow into them. *Advanced use cases* has the parts that go beyond today's Space API.
"""),
]

ADVANCED = [
md("""
# Advanced use cases

*Each section stands on its own and runs against the same in-memory fakes as the story. These are the parts of the
SDK that go beyond what the Space API does today; where a section needs something the API does not have, it says so
and shows the shape we would propose.*
"""),
code("""
import syfthub
hub = syfthub.connect("https://hub.example.com")
hub.login(username="alice", password="secret")
"""),
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
hub.get("carol/papers")
"""),
code("""
hub.get("dave/notes")      # advertises nothing: filters on Dave's notes stay on the client
"""),
md("""
Same filter, three sources, three documents each. Carol's papers and Erin's registry take `published` at the Space;
Dave's notes do not, and they are priced per document, so the pre-flight warns that the hidden ones are still billed.
"""),
code("""
search = hub.search("adverse events in phase 3 trials", sources=["carol/papers", "erin/trials", "dave/notes"], limit=3)
search.filter(published_gte="2024-06-01")
search
"""),
code("""
topup = search.top_up("dave/notes", bundle="starter")
hub._simulate_checkout_paid(topup.invoice["id"])   # mock: paid at the link
results = search.execute()
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
hub.search("adverse events in phase 3 trials", sources=["carol/papers", "erin/trials"], limit=3) \\
   .filter(published_gte="2024-01-01", author="R. Chitrakoot")
"""),
md("""
The same `filter` verb works on a chat that searches every turn: the filter goes with each turn's search, to the
Space where it can.
"""),
code("""
live = hub.chat("bob/llama-3", sources=["carol/papers", "erin/trials"]).filter(published_gte="2024-06-01")
live.send("What were the serious adverse event rates?")
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
results = hub.search("adverse events in phase 3 trials", sources=["carol/papers", "olga/trials-assistant"]).execute()
room = results.chat(["ivan/gpt-mini", "bob/llama-3"])
room
"""),
code("""
replies = room.send("Summarise the serious adverse events.")
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
topup = room.top_up("ivan/gpt-mini", bundle="starter")
hub._simulate_checkout_paid(topup.invoice["id"])   # mock: paid at the link
replies = room.send("Summarise the serious adverse events.")
replies
"""),
md("""
Who answers can change between turns. `room.add` brings a model in from the next question on, briefed with the
lead tab's transcript by default; `room.remove` stops asking one. Each model sees the shared questions and only
its own earlier answers.
"""),
code("""
room.add("lena/sahabat-ai")      # billed in rupiah, from Lena's IDR wallet
room.send("Were any of them fatal?")
"""),
code("""
room.remove("ivan/gpt-mini")
room.send("And in one line?")
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
    NotebookClient(nb, timeout=120, kernel_name="python3", resources={"metadata": {"path": "."}}, allow_errors=True).execute()
    nbf.write(nb, name)
    errs = [(i, o["ename"], o["evalue"]) for i, c in enumerate(nb.cells) if c.cell_type == "code"
            for o in c.get("outputs", []) if o.get("output_type") == "error"]
    print(f"{name}: {len(nb.cells)} cells, {len(errs)} errors", *[f"\n   cell {i}: {n}: {v}" for i, n, v in errs])
    return bool(errs)


failed = [build(STORY, "story.ipynb"), build(ADVANCED, "advanced.ipynb")]
sys.exit(1 if any(failed) else 0)
