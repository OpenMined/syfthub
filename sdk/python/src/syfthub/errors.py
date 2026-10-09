"""The ``SyftHubError`` hierarchy.

The rule: a fault that stops the whole call raises; a fault that stops one source becomes a row on
``Results``. An app catches ``SyftHubError`` once and reads ``results.failed`` for the rest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models.search import Action


class SyftHubError(Exception):
    """Base class for every error the SDK raises."""


class ConfigurationError(SyftHubError):
    """Bad URL, no token and no credentials, or invalid ``Options``."""


class ValidationError(SyftHubError, ValueError):
    """A caller-supplied value is out of range or malformed (limit < 1, threshold outside 0..1,
    a source path that is not ``owner/slug``, a snapshot that does not parse). Also a ``ValueError``,
    so pydantic wraps it when it is raised inside a field validator."""


class AuthError(SyftHubError):
    """Login failed, or the token expired and could not be re-minted."""


class HubUnreachable(SyftHubError):
    """The Hub itself could not be reached after retries."""


class SourceNotFound(SyftHubError):
    """``hub.sources.get`` on a path the Hub does not know."""

    def __init__(self, path: str) -> None:
        super().__init__(f"source not found: {path}")
        self.path = path


class PaymentError(SyftHubError):
    """Base class for payment faults."""


class PaymentTimeout(PaymentError):
    """``invoice.wait_paid`` ran out of time."""

    def __init__(self, invoice_id: str, timeout: float) -> None:
        super().__init__(f"invoice {invoice_id} not paid within {timeout:g}s")
        self.invoice_id = invoice_id
        self.timeout = timeout


class PaymentFailed(PaymentError):
    """The Hub wallet pay call or the Space invoice route returned an error."""


class StaleSnapshot(SyftHubError):
    """``from_dict`` on a dict written by an incompatible SDK version."""

    def __init__(self, found: Any, expected: str) -> None:
        super().__init__(f"snapshot version {found!r} is not compatible with SDK {expected}")
        self.found = found
        self.expected = expected


class ActionRequired(SyftHubError):
    """``execute(strict=True)`` with open actions. Carries ``.actions``."""

    def __init__(self, actions: tuple[Action, ...]) -> None:
        kinds = ", ".join(a.kind.value for a in actions)
        super().__init__(f"{len(actions)} action(s) required before sending: {kinds}")
        self.actions = actions
