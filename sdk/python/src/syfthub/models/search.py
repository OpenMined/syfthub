"""``SearchPlan``, pre-flight rows, and the actions a pre-flight can raise."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import Field, PrivateAttr, field_validator

from .. import __version__
from ..errors import StaleSnapshot, ValidationError
from .base import Bound, Frozen
from .enums import ActionKind, Reason, Verdict
from .money import Bundle, Money
from .session import Budget
from .sources import Source
from .wallets import Invoice, Wallet

if TYPE_CHECKING:
    from .results import Results

_PATH = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def check_snapshot_version(found: Any) -> None:
    """Raise ``StaleSnapshot`` unless ``found`` was written by a compatible SDK major version."""
    if not isinstance(found, str) or _major(found) != _major(__version__):
        raise StaleSnapshot(found, __version__)


def as_path(value: str | Source) -> str:
    """Accept a ``Source`` or an ``owner/slug`` string; return the path."""
    path = value.path if isinstance(value, Source) else value
    if not isinstance(path, str) or not _PATH.match(path):
        raise ValidationError(f"not a source path (owner/slug): {value!r}")
    return path


class SearchPlan(Bound):
    """A pure function of query, sources, options and skips. Everything else is read fresh at
    pre-flight, so a plan can be stored and rebuilt from another process."""

    query: str
    sources: tuple[str, ...] = ()
    limit: int = 5
    similarity_threshold: float = 0.5
    include_metadata: bool = True
    skips: tuple[str, ...] = ()
    max_sources: int = 10
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
    def _at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("must be at least 1")
        return v

    @field_validator("similarity_threshold")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("similarity_threshold must be within 0..1")
        return v

    @field_validator("sources", "skips")
    @classmethod
    def _paths(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(as_path(p) for p in v)

    @classmethod
    def from_dict(cls, hub: Any, d: dict[str, Any]) -> SearchPlan:
        check_snapshot_version(d.get("version"))
        return super().from_dict(hub, d)

    @property
    def explicit(self) -> bool:
        """True when ``sources`` was given at compose; False when the Hub picks them."""
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

    def skip(self, *paths: str | Source) -> SearchPlan:
        """The one decision. Returns a new plan; rows for these paths become ``HELD by_user``."""
        new = tuple(as_path(p) for p in paths)
        if self.explicit:
            unknown = [p for p in new if p not in self.sources]
            if unknown:
                raise ValidationError(f"not in this plan's sources: {', '.join(unknown)}")
        merged = self.skips + tuple(p for p in new if p not in self.skips)
        plan = self.model_copy(update={"skips": merged})
        plan._bind(self._hub)
        return plan

    async def preflight(self) -> Preflight:
        pre: Preflight = await self._require_hub().preflight(self)
        self._pre = pre
        return pre

    async def execute(self, *, strict: bool = False) -> Results:
        results: Results = await self._require_hub().execute(self, strict=strict)
        return results


class PlanRow(Frozen):
    source: Source
    verdict: Verdict
    estimate: Money = Money()
    wallet: Wallet | None = None
    reason: Reason | None = None
    note: str | None = None

    @property
    def send(self) -> bool:
        return self.verdict.sends

    @property
    def path(self) -> str:
        return self.source.path


class Action(Frozen):
    """Base: one per cause, not per source. ``steps`` are plain-English steps to resolve it."""

    kind: ActionKind
    affects: tuple[Source, ...] = ()
    steps: tuple[str, ...] = ()

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(s.path for s in self.affects)


class TopUp(Action):
    kind: ActionKind = ActionKind.TOP_UP
    wallet: Wallet
    shortfall: Money
    bundles: tuple[Bundle, ...] = ()
    suggested: Bundle | None = None

    async def top_up(self, bundle: str | Bundle | None = None) -> Invoice:
        """Same route and return as ``wallet.top_up``. Omit ``bundle`` for ``suggested``."""
        chosen = bundle if bundle is not None else self.suggested
        if chosen is None:
            raise ValidationError(
                f"no bundle on wallet {self.wallet.key} covers {self.shortfall}; pass one explicitly"
            )
        return await self.wallet.top_up(chosen)


class OverBudget(Action):
    kind: ActionKind = ActionKind.OVER_BUDGET
    estimate: Money
    budget: Budget


class AccessDenied(Action):
    kind: ActionKind = ActionKind.ACCESS_DENIED
    rule: str | None = None


class CircuitOpen(Action):
    kind: ActionKind = ActionKind.CIRCUIT_OPEN
    reopens_at: datetime


AnyAction = TopUp | OverBudget | AccessDenied | CircuitOpen


class Preflight(Frozen):
    """A snapshot. Run ``plan.preflight()`` again for a fresh one."""

    rows: tuple[PlanRow, ...] = ()
    actions: tuple[AnyAction, ...] = ()
    estimate: dict[str, Money] = Field(default_factory=dict)
    budget: Budget = Budget()
    checked_at: datetime = Field(default_factory=_now)

    @property
    def ready(self) -> bool:
        return not self.held

    @property
    def sending(self) -> tuple[PlanRow, ...]:
        return tuple(r for r in self.rows if r.send)

    @property
    def held(self) -> tuple[PlanRow, ...]:
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
