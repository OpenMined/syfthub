"""``SearchPlan``, pre-flight rows, and the actions a pre-flight can raise."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pydantic import Field, PrivateAttr, field_validator, model_validator

from .._version import __version__
from ..errors import StaleSnapshot, ValidationError
from .base import FROZEN, Bound, Frozen
from .enums import ActionKind, Reason, Verdict
from .filters import Condition, Filter, Group, SourceSelection
from .money import Bundle, Money
from .ports import HubPorts
from .session import Budget
from .sources import Source
from .wallets import Invoice, Wallet

if TYPE_CHECKING:
    from .results import Results

_PATH = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def _now() -> datetime:
    return datetime.now(UTC)


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def check_snapshot_version(found: Any) -> None:
    """Raise ``StaleSnapshot`` unless ``found`` was written by a compatible SDK major version.

    Args:
        found: the ``version`` a snapshot was written with.
    """
    if not isinstance(found, str) or _major(found) != _major(__version__):
        raise StaleSnapshot(found, __version__)


def as_path(value: str | Source | SourceSelection) -> str:
    """Accept a ``Source``, a ``SourceSelection`` or an ``owner/slug`` string; return the path.

    Args:
        value: a ``Source``, a ``SourceSelection`` or an ``owner/slug`` string.

    Returns:
        The path.
    """
    path = value.path if isinstance(value, (Source, SourceSelection)) else value
    if not isinstance(path, str) or not _PATH.match(path):
        raise ValidationError(f"not a source path (owner/slug): {value!r}")
    return path


def as_selection(value: str | Source | SourceSelection) -> SourceSelection:
    """A ``SourceSelection``: a bare path or ``Source`` carries no filter.

    Args:
        value: a ``Source``, a ``SourceSelection`` or an ``owner/slug`` string.

    Returns:
        The selection.
    """
    if isinstance(value, SourceSelection):
        as_path(value)
        return value
    return SourceSelection(path=as_path(value))


class SearchPlan(Bound):
    """What ``hub.search`` composes and ``execute`` sends.

    The query, the sources it goes to, their filters, and the options. Nothing is sent until
    ``execute``.

    A plan is a pure function of its fields. Prices, credits, access and reachability are read
    fresh at ``preflight``, so a plan can be saved with ``to_dict`` and rebuilt in another
    process with ``SearchPlan.from_dict(hub, d)`` (``hub.load`` on the sync twin).

    ``sources`` holds paths. ``filters`` maps a path to the filter that source is queried
    with; only a source you named can carry one, never an automatic pick. ``skip`` is the one
    decision you make on a plan and returns a new one.

    Example:
        ::

            plan = hub.search("Artemis launches", [source.where(recent), "esa/news"], limit=3)
            pre = await plan.preflight()      # what each source will cost and need
            plan = plan.skip("esa/news")      # a new plan; the row becomes HELD by_user
            results = await plan.execute()
    """

    model_config = FROZEN

    query: str
    sources: tuple[str, ...] = ()
    filters: dict[str, Filter] = Field(default_factory=dict)  # by path, named sources only
    limit: int = 5
    similarity_threshold: float = 0.5
    include_metadata: bool = True
    skips: tuple[str, ...] = ()
    max_sources: int | None = None  # a ceiling on automatic picking; never caps named sources
    version: str = Field(default_factory=lambda: __version__)
    created_at: datetime = Field(default_factory=_now)
    _pre: Any = PrivateAttr(default=None)

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be blank")
        return v

    @field_validator("limit", "max_sources")
    @classmethod
    def _at_least_one(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("must be at least 1")
        return v

    @field_validator("similarity_threshold")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("similarity_threshold must be within 0..1")
        return v

    @model_validator(mode="before")
    @classmethod
    def _split_selections(cls, data: Any) -> Any:
        """Split ``SourceSelection`` and ``Source`` items out of ``sources``.

        Their paths go to ``sources`` and their filters to ``filters``.
        """
        if not isinstance(data, dict) or isinstance(data.get("sources"), str):
            return data
        given = data.get("sources")
        if given is None or all(isinstance(s, str) for s in given):
            return data
        filters = dict(data.get("filters") or {})
        paths: list[str] = []
        for item in given:
            selection = as_selection(item)
            paths.append(selection.path)
            if selection.filters is not None:
                filters[selection.path] = selection.filters
        return {**data, "sources": tuple(paths), "filters": filters}

    @field_validator("sources", "skips")
    @classmethod
    def _paths(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(as_path(p) for p in v)

    @model_validator(mode="after")
    def _filters_name_plan_sources(self) -> SearchPlan:
        """A filter rides on a named source: nothing is filtered on an automatic pick."""
        stray = [p for p in self.filters if p not in self.sources]
        if stray:
            raise ValueError(f"filters for sources not in this plan: {', '.join(stray)}")
        return self

    @classmethod
    def from_dict(cls, hub: HubPorts, d: dict[str, Any]) -> SearchPlan:
        """Rebuild a saved plan and bind it to ``hub``.

        Args:
            hub: the session the plan will send through.
            d: what ``to_dict`` wrote.

        Returns:
            The plan, bound.

        Raises:
            StaleSnapshot: when it was saved by another major version of the SDK.
        """
        check_snapshot_version(d.get("version"))
        return super().from_dict(hub, d)

    @property
    def explicit(self) -> bool:
        """True when ``sources`` was given at compose; False when the SDK picks every free source."""
        return bool(self.sources)

    @property
    def active(self) -> tuple[str, ...]:
        """Sources minus skips, in order."""
        return tuple(p for p in self.sources if p not in self.skips)

    @property
    def pre(self) -> Preflight | None:
        """The last ``Preflight`` this plan ran, if any."""
        pre: Preflight | None = self._pre
        return pre

    def filter_for(self, path: str) -> Condition | Group | None:
        """The filter this plan sends to ``path``, if any.

        Args:
            path: ``owner/slug``.

        Returns:
            The filter, or None.
        """
        return self.filters.get(path)

    def skip(self, *paths: str | Source) -> SearchPlan:
        """The one decision. Returns a new plan; rows for these paths become ``HELD by_user``.

        Args:
            *paths: ``owner/slug`` strings or ``Source`` objects.

        Returns:
            A new plan with those sources held.
        """
        new = tuple(as_path(p) for p in paths)
        if self.explicit:
            unknown = [p for p in new if p not in self.sources]
            if unknown:
                raise ValidationError(f"not in this plan's sources: {', '.join(unknown)}")
        merged = self.skips + tuple(p for p in new if p not in self.skips)
        return self._derive(skips=merged)

    async def preflight(self) -> Preflight:
        """Price and check every active source without sending the query.

        Returns:
            One ``PlanRow`` per source with a ``Verdict``, and one ``Action`` per cause that
            holds rows back. The snapshot is also kept on ``pre``.
        """
        pre = await self._require_hub().preflight(self)
        self._pre = pre
        return pre

    async def execute(self, *, strict: bool = False) -> Results:
        """Pre-flight, then send the query to every row that may go, in parallel.

        Pays on the way where a Space charges. Rejections and failures land in rows and never
        raise.

        Args:
            strict: raise on a held or failed row instead of returning it.

        Returns:
            One row per source.
        """
        return await self._require_hub().execute(self, strict=strict)


class PlanRow(Frozen):
    """One source as pre-flight saw it.

    The ``verdict`` says whether ``execute`` will send to it, ``estimate`` what it may cost,
    ``wallet`` where that would be paid from, and ``note`` why it is held.
    """

    source: Source
    verdict: Verdict
    estimate: Money = Money()
    wallet: Wallet | None = None
    reason: Reason | None = None
    note: str | None = None

    @property
    def send(self) -> bool:
        """True when ``execute`` will send to this source."""
        return self.verdict.sends

    @property
    def path(self) -> str:
        """The source's ``owner/slug``."""
        return self.source.path


class Action(Frozen):
    """Base: one per cause, not per source. ``steps`` are plain-English steps to resolve it."""

    kind: ActionKind
    affects: tuple[Source, ...] = ()
    steps: tuple[str, ...] = ()

    @property
    def paths(self) -> tuple[str, ...]:
        """The paths of the sources this action affects."""
        return tuple(s.path for s in self.affects)


class TopUp(Action):
    """A prepaid wallet is short.

    ``shortfall`` is the gap; ``top_up()`` buys a bundle to cover it.
    """

    kind: ActionKind = ActionKind.TOP_UP
    wallet: Wallet
    shortfall: Money
    bundles: tuple[Bundle, ...] = ()
    suggested: Bundle | None = None

    async def top_up(self, bundle: str | Bundle | None = None) -> Invoice:
        """Same route and return as ``wallet.top_up``. Omit ``bundle`` for ``suggested``.

        Args:
            bundle: a bundle or its id; ``suggested`` when omitted.

        Returns:
            The invoice to pay.
        """
        chosen = bundle if bundle is not None else self.suggested
        if chosen is None:
            raise ValidationError(
                f"no bundle on wallet {self.wallet.key} covers {self.shortfall}; pass one explicitly"
            )
        return await self.wallet.top_up(chosen)


class OverBudget(Action):
    """The ``estimate`` crosses the session's cap for its currency; ``hub.set_budget`` lifts it."""

    kind: ActionKind = ActionKind.OVER_BUDGET
    estimate: Money
    budget: Budget


class AccessDenied(Action):
    """The sources' access policy shuts this caller out; ``rule`` is the pattern that did."""

    kind: ActionKind = ActionKind.ACCESS_DENIED
    rule: str | None = None


class CircuitOpen(Action):
    """The sources' host is cooling down after failures, until ``reopens_at``."""

    kind: ActionKind = ActionKind.CIRCUIT_OPEN
    reopens_at: datetime


AnyAction = TopUp | OverBudget | AccessDenied | CircuitOpen


class Preflight(Frozen):
    """What ``plan.preflight()`` found.

    A ``PlanRow`` per source, the ``actions`` that would free the held ones, and the
    worst-case ``estimate`` per currency across the rows that send. Iterate it for the rows,
    or index by path. A snapshot: run ``plan.preflight()`` again for a fresh one.

    Example:
        ::

            pre = await plan.preflight()
            if not pre.ready:
                for action in pre.actions:      # one per cause, e.g. a TopUp for a short wallet
                    print(action.kind, action.paths, action.steps)
            pre["nasa/news"].verdict
    """

    rows: tuple[PlanRow, ...] = ()
    actions: tuple[AnyAction, ...] = ()
    estimate: dict[str, Money] = Field(default_factory=dict)
    budget: Budget = Budget()
    checked_at: datetime = Field(default_factory=_now)

    @property
    def ready(self) -> bool:
        """True when every row will send."""
        return not self.held

    @property
    def sending(self) -> tuple[PlanRow, ...]:
        """The rows ``execute`` will send to."""
        return tuple(r for r in self.rows if r.send)

    @property
    def held(self) -> tuple[PlanRow, ...]:
        """The rows it will not; ``actions`` says what would free them."""
        return tuple(r for r in self.rows if not r.send)

    def __iter__(self) -> Iterator[PlanRow]:  # type: ignore[override]
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, path: str) -> PlanRow:
        for row in self.rows:
            if row.path == path:
                return row
        raise KeyError(path)
