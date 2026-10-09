"""``Results``: one ``SourceResult`` per source, plus the views over their documents."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from pydantic import Field

from ..errors import ValidationError
from .base import Bound, Frozen
from .enums import Outcome, Rail, Reason, ReturnKind
from .money import Money
from .search import AnyAction, SearchPlan, TopUp, _now, check_snapshot_version
from .sources import Source
from .wallets import Charge, ChargeEntry, RateLimit

_RETRYABLE_REJECTIONS = frozenset({Reason.RATE_LIMITED, Reason.NO_CREDITS})


class Document(Frozen):
    """One ``references.documents[]`` item, or a model's summary with ``score=None``."""

    id: str = Field(default="", alias="document_id")
    content: str = ""
    score: float | None = Field(default=None, alias="similarity_score")
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = ""

    @property
    def title(self) -> str | None:
        value = self.metadata.get("title")
        return value if isinstance(value, str) else None

    @property
    def is_summary(self) -> bool:
        return self.score is None


class SourceResult(Frozen):
    """One row of ``Results``: its own billing and served-by record."""

    source: Source
    outcome: Outcome
    reason: Reason | None = None
    status_code: int = 0
    documents: tuple[Document, ...] = ()
    summary: str | None = None
    cost: Money | None = None
    charges: tuple[ChargeEntry, ...] = ()
    paid_from: str | None = None
    rail: Rail | None = None
    charge: Charge | None = None
    topup: TopUp | None = None
    rate_limit: RateLimit | None = None
    elapsed_ms: int = 0
    attempts: int = 0
    error: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def path(self) -> str:
        return self.source.path

    @property
    def ok(self) -> bool:
        return self.outcome is Outcome.RETURNED

    @property
    def retryable(self) -> bool:
        if self.outcome is Outcome.REJECTED:
            return self.reason in _RETRYABLE_REJECTIONS
        if self.outcome is Outcome.FAILED:
            return self.reason is not Reason.NOT_FOUND
        return False

    @property
    def chunks(self) -> tuple[Document, ...]:
        return tuple(d for d in self.documents if not d.is_summary)

    @property
    def summaries(self) -> tuple[Document, ...]:
        return tuple(d for d in self.documents if d.is_summary)


def _by_score(pairs: list[tuple[str, Document]]) -> list[tuple[str, Document]]:
    return sorted(pairs, key=lambda p: -(p[1].score or 0.0))


class Results(Bound):
    """Immutable. Views (``only``, ``drop``, ``top``, ``+``) return a new ``Results``."""

    rows: tuple[SourceResult, ...] = ()
    plan: SearchPlan
    actions: tuple[AnyAction, ...] = ()
    executed_at: datetime = Field(default_factory=_now)

    @classmethod
    def from_dict(cls, hub: Any, d: dict[str, Any]) -> Results:
        plan = d.get("plan")
        check_snapshot_version(plan.get("version") if isinstance(plan, dict) else None)
        return super().from_dict(hub, d)

    def _bind(self, hub: Any) -> None:
        super()._bind(hub)
        self.plan._bind(hub)
        for action in self.actions:
            if isinstance(action, TopUp):
                action.wallet._bind(hub)
        for row in self.rows:
            if row.topup is not None:
                row.topup.wallet._bind(hub)

    def __iter__(self) -> Iterator[SourceResult]:  # type: ignore[override]
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, path: str) -> SourceResult:
        for row in self.rows:
            if row.path == path:
                return row
        raise KeyError(path)

    def __contains__(self, path: object) -> bool:
        return any(r.path == path for r in self.rows)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(r.path for r in self.rows)

    @property
    def ok(self) -> tuple[SourceResult, ...]:
        return tuple(r for r in self.rows if r.ok)

    @property
    def failed(self) -> tuple[SourceResult, ...]:
        return tuple(r for r in self.rows if r.outcome in (Outcome.REJECTED, Outcome.FAILED))

    @property
    def held(self) -> tuple[SourceResult, ...]:
        return tuple(r for r in self.rows if r.outcome is Outcome.HELD)

    @property
    def retryable(self) -> tuple[SourceResult, ...]:
        return tuple(r for r in self.rows if r.retryable)

    @property
    def chunks(self) -> tuple[tuple[str, Document], ...]:
        """Scored documents across sources, best first."""
        return tuple(_by_score([(r.path, d) for r in self.ok for d in r.chunks]))

    @property
    def answers(self) -> dict[str, str]:
        """``path -> summary`` for the model sources that answered."""
        return {r.path: r.summary for r in self.ok if r.summary}

    @property
    def documents(self) -> tuple[tuple[str, Document], ...]:
        """Scored chunks by score, then the unscored summaries after them."""
        summaries = [(r.path, d) for r in self.ok for d in r.summaries]
        return self.chunks + tuple(summaries)

    @property
    def kind(self) -> ReturnKind:
        has_chunks, has_answers = bool(self.chunks), bool(self.answers)
        if has_chunks and has_answers:
            return ReturnKind.BOTH
        if has_chunks:
            return ReturnKind.REFERENCES
        if has_answers:
            return ReturnKind.SUMMARIES
        return ReturnKind.NOTHING

    @property
    def cost(self) -> dict[str, Money]:
        """Per currency, never converted."""
        total: dict[str, Money] = {}
        for row in self.rows:
            if row.cost is not None and row.cost.positive:
                cur = row.cost.currency
                total[cur] = total[cur] + row.cost if cur in total else row.cost
        return total

    @property
    def raw(self) -> dict[str, dict[str, Any]]:
        return {r.path: r.raw for r in self.rows}

    def _view(self, rows: list[SourceResult]) -> Results:
        view = self.model_copy(update={"rows": tuple(rows)})
        view._bind(self._hub)
        return view

    def only(self, *paths: str) -> Results:
        want = set(paths)
        return self._view([r for r in self.rows if r.path in want])

    def drop(self, *paths: str) -> Results:
        avoid = set(paths)
        return self._view([r for r in self.rows if r.path not in avoid])

    def top(self, k: int) -> Results:
        """Keep the ``k`` best-scored chunks across sources; summaries are always kept."""
        if k < 0:
            raise ValidationError("k must be at least 0")
        keep = {(path, doc.id, doc.content) for path, doc in self.chunks[:k]}
        rows = [
            r.model_copy(
                update={
                    "documents": tuple(
                        d for d in r.documents if d.is_summary or (r.path, d.id, d.content) in keep
                    )
                }
            )
            for r in self.rows
        ]
        return self._view(rows)

    def __add__(self, other: Results) -> Results:
        """Rows from ``other`` replace rows for the same path; the plan is this one's."""
        merged = {r.path: r for r in self.rows}
        merged.update({r.path: r for r in other.rows})
        view = self.model_copy(
            update={"rows": tuple(merged.values()), "actions": self.actions + other.actions}
        )
        view._bind(self._hub)
        return view

    async def retry(self) -> Results:
        """Re-send the retryable rows; the same as ``self.plan.execute()`` for just those."""
        retry_paths = {r.path for r in self.retryable}
        if not retry_paths:
            return self
        plan = self.plan.model_copy(
            update={"sources": tuple(retry_paths & set(self.plan.sources)) or tuple(retry_paths)}
        )
        plan._bind(self._require_hub())
        fresh: Results = await plan.execute()
        return self + fresh
