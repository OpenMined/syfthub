"""SyftHub Python SDK v2: UX mock. In-memory fakes only; the shapes on the wire are real.

    import syfthub
    async with syfthub.AsyncHub() as hub:                       # SYFTHUB_URL, SYFTHUB_TOKEN
        results = await hub.search("adverse events in phase 3").execute()

    hub.endpoints.list() / .search(text) / .get(path)          # discovery
    hub.wallets.list() / .for_endpoint(path)                   # prepaid balances
    plan = hub.search(q, sources=[...]); await plan.preflight(); await plan.execute()
    results.filter(...) / .only(...) / .top(k); await results.retry(); await results.top_up(path, "starter")
    chat = results.chat("bob/llama-3"); await chat.send("...")
"""
__version__ = "0.1.0"

from ._transport import CircuitBreaker, Options, Retry, Timeout          # noqa: E402
from .errors import (AggregatorError, AuthError, BudgetExceeded, ConfigurationError, HubError, HubUnavailable,  # noqa: E402
                     InvalidState, InvoiceError, NotFound, NotLoggedIn, SpaceError, SyftHubError, ValidationError)
from .models import *  # noqa: E402,F401,F403
from .models import __all__ as _model_names  # noqa: E402
from .search import SearchPlan  # noqa: E402
from .results import Results  # noqa: E402
from .chat import Chat, Context, Replies, Reply  # noqa: E402
from .hub import AsyncHub  # noqa: E402
from ._sync import Hub  # noqa: E402

__all__ = ["AsyncHub", "Hub", "Options", "Retry", "Timeout", "CircuitBreaker", "SearchPlan", "Results", "Chat", "Reply",
           "Replies", "Context", "SyftHubError", "ConfigurationError", "ValidationError", "AuthError", "NotLoggedIn",
           "HubError", "NotFound", "HubUnavailable", "SpaceError", "InvoiceError", "AggregatorError", "BudgetExceeded",
           "InvalidState", *_model_names]
