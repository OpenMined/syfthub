"""Exceptions are reserved for things the caller cannot act on inside the flow.
Expected branches (payment required, insufficient credits, a source being
down) are *outcomes* on the run, not exceptions."""


class SyftHubError(Exception):
    """Base class for every error the SDK raises. Catch it to handle any SDK error in one place."""
    pass


class NotLoggedIn(SyftHubError):
    """You called something that needs a signed-in user. Call ``hub.login(...)`` first."""
    pass


class BudgetExceeded(SyftHubError):
    """An action would spend more than the session budget allows.

    Raised by ``results.approve()`` when paying the pending MPP charges would cross the cap you set
    with ``hub.set_budget``. Raise the budget, or approve fewer sources.

    Attributes:
        needed: How much the action would cost, in ``currency``.
        remaining: How much of the budget is left.
        currency: The budget's currency."""

    def __init__(self, needed: float, remaining: float, currency: str = "USD") -> None:
        super().__init__(f"Needs {needed:.2f} {currency}, budget has {remaining:.2f} left")
        self.needed, self.remaining, self.currency = needed, remaining, currency


class NothingToRun(SyftHubError):
    """Nothing is left to send: every source is already answered, skipped by you, or not retryable.

    Reserved for ``execute()`` and ``retry()``. The mock does not raise it yet."""
    pass


class RunNotReady(SyftHubError):
    """The action does not apply in the current state, and the message says what to do instead.

    For example: topping up a source that is not short of credits, or sending a message in a chat
    with no model in it."""
    pass
