"""SyftHub v2 SDK: UX mock. In-memory fakes only.

    import syfthub
    hub = syfthub.connect("https://hub.example.com")
    hub.login(username="alice", password="secret")
    hub.browse()
    search = hub.search("adverse events in phase 3", sources=["carol/papers", "dave/notes", "olga/trials-assistant"])   # any endpoint type
    results = search.execute()
    results.top_up("dave/notes", bundle="starter"); ...; results.retry()
    results.ask("bob/llama-3")          # model over the raw results, direct
    results.aggregate("bob/llama-3")    # same via an Aggregator (route to be built)
    hub.chat("bob/llama-3", sources=[...]).send("...")
"""
from .errors import BudgetExceeded, NotLoggedIn, RunNotReady, SyftHubError
from .hub import Hub, connect
from .models import (Answer, Budget, Charge, Connection, Document, Endpoint, Identity, Outcome, Policy,
                     Pricing, Rail, Selection, SkipReason, SourceResult, TopUp, Wallet, Wallets)
from .search import Search
from .results import Chat, Context, Replies, Reply, Results

__all__ = ["connect", "Hub", "Search", "Results", "Chat", "Reply", "Replies", "Context", "Endpoint", "Selection", "Policy", "Connection", "Pricing", "Rail",
           "Identity", "Budget", "Wallet", "Wallets", "Document", "TopUp", "Charge", "SourceResult", "Answer", "Outcome", "SkipReason",
           "SyftHubError", "NotLoggedIn", "BudgetExceeded", "RunNotReady"]
__version__ = "0.0.2"
