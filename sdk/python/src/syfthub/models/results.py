"""``Results``: one ``SourceResult`` per source, plus the views over their documents."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from pydantic import Field

from ..errors import ValidationError
from .base import FROZEN, Bound, Frozen
from .enums import Outcome, Rail, Reason, ReturnKind
from .money import Money
from .ports import HubPorts
from .search import AnyAction, SearchPlan, TopUp, _now, check_snapshot_version
from .sources import Source
from .wallets import Charge, ChargeEntry, RateLimit

_RETRYABLE_REJECTIONS = frozenset({Reason.RATE_LIMITED, Reason.NO_CREDITS})
_RETRYABLE_FAILURES = frozenset({Reason.UNREACHABLE, Reason.TIMEOUT, Reason.SERVER_ERROR})


class Document(Frozen):
    """One passage a source returned, with its score and metadata.

    ``content`` is the text, ``score`` the rank the Space gave it, ``metadata`` the keys the
    publisher declared (see ``Source.metadata_fields``). A model source's answer is a
    ``Document`` too, with ``score=None`` and ``is_summary`` True.

    Example:
        >>> d = Document(content="Walker on sleep", similarity_score=0.71, metadata={"title": "#1"})
        >>> d.score, d.title, d.is_summary
        (0.71, '#1', False)
    """

    id: str = Field(default="", alias="document_id")
    content: str = ""
    score: float | None = Field(default=None, alias="similarity_score")
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    # The Space origin this document came from; None for a tunnelled source. Relative links
    # in ``metadata`` resolve against it.
    base_url: str | None = None

    @classmethod
    def from_space(cls, source: str, d: dict[str, Any], *, base_url: str | None = None) -> Document:
        """One ``references.documents[]`` item; tolerant of missing or null fields.

        Args:
            source: the source's path.
            d: the item as the Space sent it.
            base_url: the Space origin relative links resolve against.

        Returns:
            The document.
        """
        metadata = d.get("metadata")
        return cls(
            document_id=str(d.get("document_id") or d.get("id") or ""),
            content=str(d.get("content") or ""),
            similarity_score=_float(d.get("similarity_score", d.get("score"))),
            metadata=metadata if isinstance(metadata, dict) else {},
            source=source,
            base_url=base_url,
        )

    @classmethod
    def summary(cls, source: str, text: str) -> Document:
        """A model source's answer as an unscored document.

        Args:
            source: the source's path.
            text: the model's answer.

        Returns:
            The document.
        """
        return cls(document_id="summary", content=text, similarity_score=None, source=source)

    @property
    def title(self) -> str | None:
        """``metadata["title"]`` when the publisher set one."""
        value = self.metadata.get("title")
        return value if isinstance(value, str) else None

    @property
    def is_summary(self) -> bool:
        """True for a model source's answer, which has no score."""
        return self.score is None

    @property
    def image_urls(self) -> tuple[str, ...]:
        """``metadata["image_urls"]`` as absolute URLs.

        The Space sends them relative to its own origin; ``metadata`` keeps them that way.
        Empty without a base (a tunnelled source) or without the key.
        """
        raw = self.metadata.get("image_urls")
        if not self.base_url or not isinstance(raw, list):
            return ()
        return tuple(urljoin(self.base_url, u) for u in raw if isinstance(u, str) and u)


class SourceResult(Frozen):
    """One source's row in ``Results``: what came back, or why nothing did, and what it cost.

    ``outcome`` is ``RETURNED``, ``REJECTED`` (the Space said no: ``reason`` says why, ``raw``
    holds its body), ``FAILED`` (no usable answer: ``error`` says why) or ``HELD`` (pre-flight
    never sent it). ``documents`` are the passages or the model's summary; ``metadata_fields``
    are the keys the Space said they carry. ``cost``, ``charges``, ``paid_from`` and ``rail``
    record the payment; ``request`` is the body that was sent.

    A ``FAILED`` row with ``Reason.INVALID_FILTER`` means the Space refused the plan's filter
    for this source; ``error`` carries its ``field: reason``.
    """

    source: Source
    outcome: Outcome
    reason: Reason | None = None
    status_code: int = 0
    documents: tuple[Document, ...] = ()
    metadata_fields: tuple[str, ...] = ()
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
        """The source's ``owner/slug``."""
        return self.source.path

    @property
    def ok(self) -> bool:
        """True when the Space answered."""
        return self.outcome is Outcome.RETURNED

    @property
    def retryable(self) -> bool:
        """Worth sending again later.

        A transient failure, a rate limit, or a host whose circuit was open at the time. Held
        for credits, budget, access or by the user is not.
        """
        if self.outcome is Outcome.REJECTED:
            return self.reason in _RETRYABLE_REJECTIONS
        if self.outcome is Outcome.FAILED:
            return self.reason in _RETRYABLE_FAILURES
        if self.outcome is Outcome.HELD:
            return self.reason is Reason.CIRCUIT_OPEN
        return False

    @property
    def chunks(self) -> tuple[Document, ...]:
        """The scored passages, in the Space's order."""
        return tuple(d for d in self.documents if not d.is_summary)

    @classmethod
    def metadata_fields_of(cls, body: dict[str, Any]) -> tuple[str, ...]:
        """``references.provider_info.metadata_fields`` of a Space response.

        Empty when the Space did not say (older Spaces, model sources).

        Args:
            body: a Space response body.

        Returns:
            The keys, or an empty tuple.
        """
        refs = body.get("references")
        info = refs.get("provider_info") if isinstance(refs, dict) else None
        raw = info.get("metadata_fields") if isinstance(info, dict) else None
        return tuple(f for f in raw if isinstance(f, str)) if isinstance(raw, list) else ()

    @property
    def summaries(self) -> tuple[Document, ...]:
        """A model source's answer, as unscored documents."""
        return tuple(d for d in self.documents if d.is_summary)


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _by_score(pairs: list[tuple[str, Document]]) -> list[tuple[str, Document]]:
    return sorted(pairs, key=lambda p: -(p[1].score or 0.0))


class Results(Bound):
    """What ``plan.execute()`` returns: one ``SourceResult`` per source, and views over them.

    Iterate it for the rows or index by path. ``ok``, ``failed``, ``held`` and ``retryable``
    split the rows; ``chunks`` ranks every scored passage across sources, best first, as
    ``(path, Document)`` pairs; ``answers`` maps a model source to its summary; ``cost`` sums
    what was paid, per currency. Nothing raises here: a source that said no is a row with a
    ``reason``, and ``retry()`` re-sends only the rows worth sending again::

        results = await plan.execute()
        for path, doc in results.chunks[:5]:
            print(f"[{doc.score:.2f}] {path}: {doc.content[:80]}")
        if results.retryable:
            results = await results.retry()
        results["nasa/news"].outcome, results.cost

    Immutable. Views (``only``, ``drop``, ``top``, ``+``) return a new ``Results``; ``to_dict``
    saves it and ``Results.from_dict(hub, d)`` (``hub.load`` on the sync twin) rebuilds it.
    """

    model_config = FROZEN

    rows: tuple[SourceResult, ...] = ()
    plan: SearchPlan
    actions: tuple[AnyAction, ...] = ()
    executed_at: datetime = Field(default_factory=_now)

    @classmethod
    def from_dict(cls, hub: HubPorts, d: dict[str, Any]) -> Results:
        """Rebuild a saved result and bind it to ``hub``.

        Args:
            hub: the session the result rebinds to.
            d: what ``to_dict`` wrote.

        Returns:
            The result, bound.

        Raises:
            StaleSnapshot: when it was saved by another major version of the SDK.
        """
        plan = d.get("plan")
        check_snapshot_version(plan.get("version") if isinstance(plan, dict) else None)
        return super().from_dict(hub, d)

    def _bind(self, hub: HubPorts) -> None:
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
        """Every row's path, in order."""
        return tuple(r.path for r in self.rows)

    @property
    def ok(self) -> tuple[SourceResult, ...]:
        """Rows whose Space answered."""
        return tuple(r for r in self.rows if r.ok)

    @property
    def failed(self) -> tuple[SourceResult, ...]:
        """Rows the Space rejected or that failed; ``reason`` and ``error`` say why."""
        return tuple(r for r in self.rows if r.outcome in (Outcome.REJECTED, Outcome.FAILED))

    @property
    def held(self) -> tuple[SourceResult, ...]:
        """Rows pre-flight never sent."""
        return tuple(r for r in self.rows if r.outcome is Outcome.HELD)

    @property
    def retryable(self) -> tuple[SourceResult, ...]:
        """Rows worth sending again; what ``retry()`` re-sends."""
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
        """Whether this holds passages, model answers, both, or nothing."""
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
        """``path -> the Space's response body``, untouched."""
        return {r.path: r.raw for r in self.rows}

    def _view(self, rows: list[SourceResult]) -> Results:
        return self._derive(rows=tuple(rows))

    def only(self, *paths: str) -> Results:
        """A view with just these rows.

        Args:
            *paths: ``owner/slug`` strings.

        Returns:
            The view.
        """
        want = set(paths)
        return self._view([r for r in self.rows if r.path in want])

    def drop(self, *paths: str) -> Results:
        """A view without these rows.

        Args:
            *paths: ``owner/slug`` strings.

        Returns:
            The view.
        """
        avoid = set(paths)
        return self._view([r for r in self.rows if r.path not in avoid])

    def top(self, k: int) -> Results:
        """Keep the ``k`` best-scored chunks across sources; summaries are always kept.

        Args:
            k: how many chunks to keep, across sources.

        Returns:
            The view.
        """
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
        """Merge: rows from ``other`` replace rows for the same path, in this one's order.

        The plan is this one's. An action of this result loses the paths ``other`` answered
        for, and goes when none are left: ``other`` carries its own actions for them.
        """
        merged = {r.path: r for r in self.rows}
        merged.update({r.path: r for r in other.rows})
        answered = {r.path for r in other.rows}
        kept: list[AnyAction] = []
        for action in self.actions:
            affects = tuple(s for s in action.affects if s.path not in answered)
            if len(affects) == len(action.affects):
                kept.append(action)
            elif affects:
                kept.append(action.model_copy(update={"affects": affects}))
        return self._derive(rows=tuple(merged.values()), actions=tuple(kept) + other.actions)

    async def retry(self) -> Results:
        """Re-send the retryable rows and merge the fresh rows in.

        The same as ``self.plan.execute()`` for just those rows, in this result's order,
        merged back with ``+``. With nothing retryable, returns this result.

        Returns:
            This result with the fresh rows merged in.
        """
        retry_paths = tuple(r.path for r in self.retryable)
        if not retry_paths:
            return self
        plan = self.plan.model_copy(
            update={
                "sources": retry_paths,
                "filters": {p: f for p, f in self.plan.filters.items() if p in retry_paths},
            }
        )
        plan._bind(self._require_hub())
        fresh: Results = await plan.execute()
        return self + fresh
