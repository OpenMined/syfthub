"""Exceptions. Every raise in the package is a subclass of ``SyftHubError``.

A Space's answer to a search or a chat message is never an exception: it becomes a row with an
outcome and, where it applies, an action. Exceptions are for misuse of the SDK and for failures
with no remedy inside the flow."""
from __future__ import annotations

from typing import Any


class SyftHubError(Exception):
    """Base class for every error the SDK raises. Catch it to handle any SDK error in one place."""


class ConfigurationError(SyftHubError):
    """The session cannot be opened as configured: a bad URL, a missing token, invalid ``Options``.

    Raised before any request is made."""


class ValidationError(SyftHubError):
    """An argument is wrong before any request is made.

    For example a ``limit`` below one, a path that is not ``owner/slug``, or an unknown filter suffix."""


class AuthError(SyftHubError):
    """A 401 that re-minting the token did not fix.

    Attributes:
        who: ``"hub"`` or ``"space"``, whichever rejected the credentials."""

    def __init__(self, message: str, *, who: str = "hub") -> None:
        super().__init__(message)
        self.who = who


class NotLoggedIn(AuthError):
    """The action needs a signed-in user. Call ``await hub.login(...)`` first."""

    def __init__(self, message: str = "Nobody is signed in: await hub.login(username=..., password=...) or hub.login(token=...)") -> None:
        super().__init__(message, who="hub")


class HubError(SyftHubError):
    """The Hub answered with a status the SDK cannot turn into a row.

    Attributes:
        status: The HTTP status.
        method: The HTTP method.
        url: The URL that was called.
        body: The response body, when there was one.
        request_id: The Hub's request id, when it sent one."""

    def __init__(self, message: str, *, status: int = 0, method: str = "", url: str = "",
                 body: dict[str, Any] | None = None, request_id: str | None = None) -> None:
        super().__init__(message)
        self.status, self.method, self.url, self.body, self.request_id = status, method, url, body or {}, request_id


class NotFound(HubError):
    """The endpoint, wallet or collective does not exist on the Hub."""


class HubUnavailable(HubError):
    """The Hub refused the connection or kept answering 5xx after every retry."""


class SpaceError(SyftHubError):
    """A Space call outside a search row failed, such as reading a balance or creating an invoice.

    Attributes:
        status: The HTTP status.
        path: The endpoint as ``owner/slug``, when one applies.
        url: The URL that was called.
        body: The response body, when there was one."""

    def __init__(self, message: str, *, status: int = 0, path: str | None = None, url: str = "",
                 body: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status, self.path, self.url, self.body = status, path, url, body or {}


class InvoiceError(SpaceError):
    """The Space refused to create the invoice, for example because the bundle does not exist."""


class AggregatorError(SyftHubError):
    """The Aggregator route is missing or failed. There is no row to attach this to.

    Attributes:
        status: The HTTP status, when there was a response."""

    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class BudgetExceeded(SyftHubError):
    """Paying would cross the session budget you set with ``hub.set_budget``.

    Raised only when you ask to pay: by ``results.approve()`` and by ``execute(ignore_budget=False)``
    for a source pre-flight did not hold. Pre-flight itself never raises; it holds the row.

    Attributes:
        needed: What the action would cost.
        remaining: What is left of the budget."""

    def __init__(self, needed: Any, remaining: Any) -> None:
        super().__init__(f"Needs {needed}, budget has {remaining} left: raise it with hub.set_budget(...)")
        self.needed, self.remaining = needed, remaining


class InvalidState(SyftHubError):
    """The action does not apply right now; the message says what to do instead.

    For example: topping up a wallet that is not short, removing a model that is not in the room, or
    sending a message to a chat with no model in it."""
