"""Results of an executed search. Immutable: every method returns a new ``Results``.

Views (``filter``, ``only``, ``drop``, ``top``, ``+``) reshape what you look at without touching the raw
responses. Actions (``retry``, ``approve``, ``skip``, ``top_up``) talk to Spaces and return the updated set."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

from .errors import InvalidState
from .models import (Charge, ChargeEntry, Document, Endpoint, Include, Invoice, Message, Money, Outcome, Reason,
                     ReturnKind, SourceResult, TopUp, total, validate_filters)

if TYPE_CHECKING:  # pragma: no cover
    from .chat import Chat, Reply
    from .hub import AsyncHub
    from .models import Answer


class Results:
    """What a search returned: one row per source, plus views and follow-up actions.

    Each row is a ``SourceResult`` that was returned, held, rejected, failed, or is waiting on a payment.
    Payment problems are rows with an action attached, never exceptions. Nothing here changes under you:
    hold on to the object a method returns.

    Attributes:
        query: The question that was sent.
        limit: How many passages each source was asked for.
        threshold: The similarity cut-off.
        history: The earlier turns that travelled with the query.
        estimate: Pre-flight's estimated maximum, per currency.
        filters: The metadata filters this view applies.
        note: Anything the SDK wants you to know about this run, such as sources chosen by default."""

    def __init__(self, hub: "AsyncHub", query: str, rows: tuple[SourceResult, ...] | list[SourceResult], *, limit: int,
                 threshold: float, history: list[Message] | None = None, estimate: dict[str, Money] | None = None,
                 filters: dict[str, Any] | None = None, note: str | None = None) -> None:
        self._hub, self.query, self._rows = hub, query, tuple(rows)
        self.limit, self.threshold = limit, threshold
        self.history = list(history or [])
        self.estimate = dict(estimate or {})
        self.filters = dict(filters or {})
        self.note = note

    def _with(self, rows=None, **kw) -> "Results":
        args = dict(limit=self.limit, threshold=self.threshold, history=self.history, estimate=self.estimate,
                    filters=self.filters, note=self.note)
        args.update(kw)
        return Results(self._hub, self.query, self._rows if rows is None else rows, **args)

    # -- views ------------------------------------------------------------------------------
    def filter(self, **filters: Any) -> "Results":
        """Hide passages whose metadata does not match. A view over what came back; raw stays intact.

        Args:
            **filters: Conditions such as ``published_gte="2024-01-01"``. Same syntax as ``SearchPlan.filter``.

        Returns:
            A new ``Results``."""
        validate_filters(filters)
        merged = {**self.filters, **filters}
        return self._with([r.model_copy(update={"local_filters": {**r.local_filters, **filters}}) for r in self._rows],
                          filters=merged)

    def only(self, *paths: str) -> "Results":
        """Keep only these sources.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            A new ``Results``."""
        keep = set(paths)
        return self._with([r for r in self._rows if r.endpoint.path in keep])

    def drop(self, *paths: str) -> "Results":
        """Hide these sources.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            A new ``Results``."""
        gone = set(paths)
        return self._with([r for r in self._rows if r.endpoint.path not in gone])

    def top(self, k: int) -> "Results":
        """Keep only the ``k`` best passages across every source, by similarity. Summaries are unaffected.

        Args:
            k: How many passages to keep.

        Returns:
            A new ``Results``."""
        ranked = sorted(self.documents, key=lambda pd: -pd[1].similarity_score)[:k]
        keep: dict[str, set[str]] = {}
        for p, d in ranked:
            keep.setdefault(p, set()).add(d.document_id)
        return self._with([r.model_copy(update={"keep_ids": frozenset(keep.get(r.endpoint.path, set()))}) for r in self._rows])

    def __add__(self, other: "Results") -> "Results":
        """Combine two result sets into one view. A source present in both keeps the newer row."""
        by = {r.endpoint.path: r for r in self._rows}
        by.update({r.endpoint.path: r for r in other._rows})
        q = self.query if self.query == other.query else f"{self.query} + {other.query}"
        est = {**self.estimate}
        for k, v in other.estimate.items():
            est[k] = est[k] + v if k in est else v
        out = self._with(list(by.values()), estimate=est, filters={**self.filters, **other.filters})
        out.query = q
        return out

    # -- reading ----------------------------------------------------------------------------
    def __iter__(self) -> Iterator[SourceResult]:
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, key: str | int) -> SourceResult:
        """One source's result, by ``owner/slug`` or by position.

        Raises:
            KeyError: When no row has that path."""
        if isinstance(key, int):
            return self._rows[key]
        for r in self._rows:
            if r.endpoint.path == key:
                return r
        raise KeyError(f"{key}: not in these results ({', '.join(self.paths)})")

    @property
    def paths(self) -> list[str]:
        """The ``owner/slug`` of every row."""
        return [r.endpoint.path for r in self._rows]

    @property
    def returned(self) -> list[SourceResult]:
        """The rows that answered."""
        return [r for r in self._rows if r.ok]

    @property
    def ok_count(self) -> int:
        """How many sources answered."""
        return len(self.returned)

    @property
    def skipped(self) -> list[SourceResult]:
        """The rows that did not answer: held, rejected, failed or waiting on a payment."""
        return [r for r in self._rows if not r.ok]

    @property
    def documents(self) -> list[tuple[str, Document]]:
        """Every passage as ``(source path, Document)`` pairs, after the view's filters and ``top(k)``."""
        return [(r.endpoint.path, d) for r in self._rows if r.ok for d in r.documents]

    @property
    def answers(self) -> dict[str, str]:
        """Summaries by source path, from the endpoints that return one."""
        return {r.endpoint.path: r.summary for r in self._rows if r.ok and r.summary}

    @property
    def kind(self) -> ReturnKind:
        """What this set carries overall."""
        kinds = {r.kind for r in self.returned} - {ReturnKind.NOTHING}
        if len(kinds) > 1 or ReturnKind.BOTH in kinds:
            return ReturnKind.BOTH
        return kinds.pop() if kinds else ReturnKind.NOTHING

    @property
    def raw(self) -> dict[str, dict[str, Any]]:
        """Every response body exactly as returned, keyed by source path."""
        return {r.endpoint.path: r.raw for r in self._rows}

    @property
    def pending(self) -> list[TopUp | Charge]:
        """What is waiting on you: one ``TopUp`` per short prepaid wallet, one ``Charge`` per MPP source."""
        out: list[TopUp | Charge] = []
        by_wallet: dict[str, TopUp] = {}
        for r in self._rows:
            if r.topup:
                t = by_wallet.get(r.topup.wallet.key)
                if t is None:
                    by_wallet[r.topup.wallet.key] = r.topup.model_copy(update={"waiting": (r.endpoint.path,)})
                else:
                    need = (t.needed + r.topup.needed) if (t.needed is not None and r.topup.needed is not None) else t.needed
                    by_wallet[t.wallet.key] = t.model_copy(update={"needed": need, "waiting": t.waiting + (r.endpoint.path,)})
            if r.charge:
                out.append(r.charge)
        return list(by_wallet.values()) + out

    @property
    def charges(self) -> list[ChargeEntry]:
        """Every payment entry from every row's envelope, in one flat list."""
        return [c for r in self._rows for c in r.charges]

    @property
    def cost(self) -> dict[str, Money]:
        """What was charged, per currency, from the Spaces' own receipts. Never converted."""
        return total(c.signed for c in self.charges)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict of the whole set, for chatbots and caches. ``Results.from_dict`` reads it back."""
        return {"query": self.query, "limit": self.limit, "threshold": self.threshold, "note": self.note,
                "history": [m.wire() for m in self.history], "filters": dict(self.filters),
                "estimate": {k: str(v.amount) for k, v in self.estimate.items()},
                "rows": [r.model_dump(mode="json") for r in self._rows]}

    @classmethod
    def from_dict(cls, hub: "AsyncHub", d: dict[str, Any]) -> "Results":
        """Rebuild a ``Results`` written by ``to_dict``.

        Args:
            hub: The session the actions should use.
            d: The dict.

        Returns:
            The ``Results``."""
        rows = [SourceResult.model_validate(r) for r in d["rows"]]
        est = {k: Money.of(v, k) for k, v in d.get("estimate", {}).items()}
        return cls(hub, d["query"], rows, limit=d["limit"], threshold=d["threshold"],
                   history=[Message(**m) for m in d.get("history", [])], estimate=est, filters=d.get("filters"),
                   note=d.get("note"))

    # -- actions ----------------------------------------------------------------------------
    async def top_up(self, wallet_or_path: str, bundle: str) -> Invoice:
        """Buy a credit bundle for a wallet a Space rejected for lack of credit.

        Args:
            wallet_or_path: A wallet key, or the path of a source waiting on it.
            bundle: The bundle id, for example ``"starter"``.

        Returns:
            The ``Invoice``. Pay at its ``checkout_url``, then ``await results.retry()``.

        Raises:
            InvalidState: When nothing is waiting on that wallet."""
        for t in self.pending:
            if isinstance(t, TopUp) and (wallet_or_path in t.waiting or t.wallet.key == wallet_or_path):
                return await t.buy(bundle)
        raise InvalidState(f"{wallet_or_path} is not waiting for credits; pending: "
                           f"{[t.wallet.key for t in self.pending if isinstance(t, TopUp)] or 'none'}")

    async def retry(self, *paths: str, ignore_budget: bool = False) -> "Results":
        """Re-send the sources whose reason can change: no credits, over budget, rate limited, unreachable.

        Rows you skipped yourself are left alone.

        Args:
            *paths: Only these sources. Leave empty for every retryable row.
            ignore_budget: Also send rows held as over budget, this once.

        Returns:
            A new ``Results`` with the re-sent rows replaced."""
        again = [r for r in self._rows if (not paths or r.endpoint.path in paths) and r.retryable]
        if not again:
            return self._with(note="nothing to retry" if not paths else f"none of {list(paths)} is retryable")
        plan = self._hub.search(self.query, sources=[r.endpoint for r in again], limit=self.limit,
                                similarity_threshold=self.threshold, history=self.history, filters=self.filters)
        fresh = await plan.execute(ignore_budget=ignore_budget)
        by = {r.endpoint.path: r for r in fresh}
        return self._with([by.get(r.endpoint.path, r) for r in self._rows])

    async def approve(self, *paths: str) -> "Results":
        """Pay the pending MPP charges from your Hub wallet and re-send those sources (experimental).

        Args:
            *paths: Only these sources. Leave empty to approve every pending charge.

        Returns:
            A new ``Results``.

        Raises:
            BudgetExceeded: When paying would cross the session budget."""
        rows = list(self._rows)
        for i, r in enumerate(rows):
            if r.charge and (not paths or r.endpoint.path in paths):
                cred = await self._hub._pay_mpp(r.charge)
                rows[i] = await self._hub._query_source(r.endpoint, self.query, self.limit, self.threshold, self.history,
                                                        x_payment=cred, filters=self.filters)
        return self._with(rows)

    def skip(self, *paths: str) -> "Results":
        """Mark sources as skipped by you, so ``retry()`` leaves them alone.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            A new ``Results``."""
        gone = set(paths)
        return self._with([r.model_copy(update={"outcome": Outcome.HELD, "reason": Reason.BY_USER, "topup": None, "charge": None})
                           if r.endpoint.path in gone and not r.ok else r for r in self._rows])

    # -- next steps -------------------------------------------------------------------------
    def chat(self, models, *, include: Include | str = Include.BOTH) -> "Chat":
        """Talk to one model, or several, about these results. Nothing is sent until ``send``.

        Args:
            models: One model path, or a list of them, or ``Endpoint`` objects.
            include: What the models get as context: the passages, other endpoints' answers, or both.

        Returns:
            A ``Chat`` over this view."""
        from .chat import Chat
        return Chat(self._hub, models, sources=None, fixed=self, include=Include(include))

    async def ask(self, model: Endpoint | str, prompt: str | None = None) -> "Reply":
        """Ask one model one question about these results, with no thread kept.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.
            prompt: The question. Leave empty to ask for a summary of the results.

        Returns:
            A ``Reply``: the answer, or a skipped reply with its top-up attached."""
        replies = await self.chat(model).send(prompt or self.query)
        return replies[0]

    async def aggregate(self, model: Endpoint | str, prompt: str | None = None) -> "Answer":
        """Hand this view's passages to the Aggregator to rerank them and generate one cited answer.

        The Aggregator route does not exist yet; this is the proposal's "documents supplied" form.

        Args:
            model: The model the Aggregator should use.
            prompt: The question. Leave empty to ask for a summary.

        Returns:
            An ``Answer``.

        Raises:
            AggregatorError: When the route is missing or fails."""
        return await self._hub._aggregator.from_results(self, model, prompt or self.query)

    # -- display ----------------------------------------------------------------------------
    def _repr_html_(self) -> str:
        from .notebook import render
        return render.results_table(self)

    def __repr__(self) -> str:
        f = f" filter {self.filters}" if self.filters else ""
        lines = [f'Results "{self.query}"{f} ({self.ok_count}/{len(self)} returned)']
        for r in self._rows:
            what = (f"{len(r.documents)} docs" + (f" + summary: {r.summary[:40]}…" if r.summary else "")) if r.ok else (r.detail or "")
            oc = r.outcome.value + (f" ({r.reason.value})" if r.reason else "")
            lines.append(f"  {r.endpoint.path:<24} {oc:<32} {what}")
        return "\n".join(lines)
