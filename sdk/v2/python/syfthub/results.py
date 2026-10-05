"""Results of an executed search, and the two things you do next: talk to a model
about them (Chat), or hand them to an Aggregator. Chat has the same pre-flight,
pending and top-up behaviour as search: a model is a Space endpoint too."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

from . import render
from .errors import RunNotReady
from .models import Answer, Charge, Document, Endpoint, Outcome, SkipReason, SourceResult, TopUp

if TYPE_CHECKING:  # pragma: no cover
    from .hub import Hub


class Results:
    """What a search returned: one row per source, plus views and follow-up actions.

    Each row is a ``SourceResult`` that was returned, skipped with a reason, or is waiting on a
    payment. Payment problems are rows with an action attached, never exceptions. Views such as
    ``filter``, ``only``, ``drop`` and ``top`` reshape what you look at without touching the raw
    responses."""

    def __init__(self, hub: "Hub", query: str, rows: list[SourceResult], *, limit: int, threshold: float,
                 history: list[dict[str, str]] | None = None, estimate: dict[str, float] | None = None,
                 filters: dict[str, Any] | None = None) -> None:
        self._hub, self.query, self._rows = hub, query, rows
        self.limit, self.threshold = limit, threshold
        self.history = history or []
        self.estimate = estimate or {}
        self.filters = filters or {}

    # -- views: every verb returns a new Results; raw responses are untouched ----------------
    def _view(self, rows, filters=None) -> "Results":
        return Results(self._hub, self.query, rows, limit=self.limit, threshold=self.threshold,
                       history=self.history, estimate=self.estimate, filters=filters if filters is not None else self.filters)

    def __add__(self, other: "Results") -> "Results":
        """Combine two result sets into one view.

        Rows from both are kept; when a source appears in both, the later one wins. Filters and estimates
        are merged. Raw responses are untouched. The usual reason is
        ``chat.use(chat.view + more)``: adding fresh evidence to a running chat.

        Returns:
            A new ``Results``."""
        rows = {r.endpoint.path: r for r in self._rows}
        rows.update({r.endpoint.path: r for r in other._rows})
        est = dict(self.estimate)
        for k, v in other.estimate.items():
            est[k] = round(est.get(k, 0.0) + v, 6)
        q = self.query if self.query == other.query else f"{self.query} + {other.query}"
        return Results(self._hub, q, list(rows.values()), limit=max(self.limit, other.limit), threshold=self.threshold,
                       history=self.history, estimate=est, filters={**self.filters, **other.filters})

    def filter(self, **filters: Any) -> "Results":
        """Hide passages whose metadata does not match.

        This is a view over what already came back, so it costs nothing and the raw responses stay
        intact. To filter before paying, use ``Search.filter`` instead.

        Args:
            **filters: Conditions such as ``published_gte="2024-01-01"``. Same syntax as
                ``Search.filter``.

        Returns:
            A new ``Results`` view."""
        from dataclasses import replace
        merged = {**self.filters, **filters}
        return self._view([replace(r, filters=merged) for r in self._rows], merged)

    def only(self, *paths: str) -> "Results":
        """Keep only these sources.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            A new ``Results`` view."""
        return self._view([r for r in self._rows if r.endpoint.path in set(paths)])

    def drop(self, *paths: str) -> "Results":
        """Hide these sources.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            A new ``Results`` view."""
        return self._view([r for r in self._rows if r.endpoint.path not in set(paths)])

    def top(self, k: int) -> "Results":
        """Keep only the best passages across every source.

        Summaries from model endpoints are unaffected.

        Args:
            k: How many passages to keep, ranked by similarity score.

        Returns:
            A new ``Results`` view."""
        from dataclasses import replace
        ranked = sorted(self.documents, key=lambda pd: -pd[1].similarity_score)[:k]
        keep = {}
        for p, d in ranked:
            keep.setdefault(p, set()).add(d.document_id)
        return self._view([replace(r, keep_ids=frozenset(keep.get(r.endpoint.path, set()))) for r in self._rows])

    # -- reading ---------------------------------------------------------------
    def __iter__(self) -> Iterator[SourceResult]:
        return iter(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, key: str | int) -> SourceResult:
        """One source's result.

        Args:
            key: The source as ``owner/slug``, or its position.

        Returns:
            The ``SourceResult``: its passages, cost, and payment envelope."""
        if isinstance(key, int):
            return self._rows[key]
        for r in self._rows:
            if r.endpoint.path == key:
                return r
        raise KeyError(key)

    @property
    def paths(self) -> list[str]:
        """The ``owner/slug`` of every row."""
        return [r.endpoint.path for r in self._rows]

    @property
    def ok_count(self) -> int:
        """How many sources answered."""
        return sum(r.ok for r in self._rows)

    @property
    def skipped(self) -> list[SourceResult]:
        """The rows that were not answered, each with its reason."""
        return [r for r in self._rows if r.skipped]

    @property
    def documents(self) -> list[tuple[str, Document]]:
        """Every passage as ``(source path, Document)`` pairs, after the view's filters and ``top(k)``."""
        return [(r.endpoint.path, d) for r in self._rows if r.ok for d in r.documents]

    @property
    def pending(self) -> list[TopUp | Charge]:
        """What is waiting on you: one ``TopUp`` per short prepaid wallet, or one ``Charge`` per MPP source."""
        out: list[TopUp | Charge] = []
        by_wallet: dict[str, TopUp] = {}
        for r in self._rows:
            if r.topup:
                t = by_wallet.get(r.topup.wallet.key)
                if t is None:
                    by_wallet[r.topup.wallet.key] = t = r.topup
                    out.append(t)
                same = [x for x in self._rows if x.topup and x.topup.wallet.key == t.wallet.key]
                t.waiting = tuple(x.endpoint.path for x in same)
                t.needed = round(sum((x.topup.needed or 0) for x in same), 6)
            if r.charge:
                out.append(r.charge)
        return out

    @property
    def spent(self) -> float:
        """What was charged, as a single number. Use ``cost`` to see it per currency."""
        return round(sum(r.cost for r in self._rows), 6)

    @property
    def charges(self) -> list[dict[str, Any]]:
        """Every payment entry from every row's ``policy_metadata``, in one flat list."""
        return _charges(self._rows)

    @property
    def cost(self) -> dict[str, float]:
        """What was charged, per currency."""
        return _totals(self.charges)

    @property
    def answers(self) -> dict[str, str]:
        """Summaries by source path, from the endpoints that return one (models and model-backed sources)."""
        return {r.endpoint.path: r.summary for r in self._rows if r.ok and r.summary}

    @property
    def returns(self) -> str:
        """What this set carries overall: ``"references"``, ``"summary"``, or ``"both"``."""
        kinds = {r.returns for r in self._rows if r.ok} - {"nothing"}
        return "both" if len(kinds) > 1 or "both" in kinds else (kinds.pop() if kinds else "nothing")

    @property
    def raw(self) -> dict[str, dict[str, Any]]:
        """Every response body exactly as returned, keyed by source path."""
        return {r.endpoint.path: r.raw for r in self._rows}

    def _repr_html_(self) -> str:
        return render.results_table(self)

    def __repr__(self) -> str:
        f = f" filter {self.filters}" if self.filters else ""
        lines = [f'Results "{self.query}"{f} ({self.ok_count}/{len(self)} ok)']
        for r in self._rows:
            what = (f"{len(r.documents)} docs" + (f" + summary: {r.summary[:40]}…" if r.summary else "")) if r.ok else (r.detail or "")
            oc = r.outcome.value + (f" ({r.reason.value})" if r.reason else "")
            lines.append(f"  {r.endpoint.path:<24} {oc:<32} {what}")
        return "\n".join(lines)

    def _ipython_display_(self) -> None:
        from IPython.display import HTML, display
        if self._hub.interactive and self.pending:
            from . import widgets
            display(widgets.results_card(self))
        else:
            display(HTML(self._repr_html_()))

    # -- payment actions (server-detected; pre-flight handles the predictable ones) ----
    def top_up(self, path_or_wallet: str, *, bundle: str) -> TopUp:
        """Buy a credit bundle for a wallet a Space rejected for lack of credit.

        Use this after ``execute()`` when a row came back as ``no_credits``. Pay at the invoice's
        ``checkout_url``, then ``retry()``.

        Args:
            path_or_wallet: An endpoint path such as ``"dave/notes"``, or a wallet key.
            bundle: The bundle's id, for example ``"starter"``.

        Returns:
            The ``TopUp`` with the Space's invoice attached."""
        for t in self.pending:
            if isinstance(t, TopUp) and (path_or_wallet in t.waiting or t.wallet.key == path_or_wallet):
                inv = t.wallet.top_up(bundle)
                for r in self._rows:
                    if r.topup and r.topup.wallet.key == t.wallet.key:
                        r.topup.invoice = inv
                t.invoice = inv
                return t
        raise RunNotReady(f"{path_or_wallet} is not waiting for credits")

    def approve(self, *paths: str) -> "Results":
        """Pay the pending MPP charges from your Hub wallet and re-send those sources (experimental).

        Args:
            *paths: Only these sources. Leave empty to approve every pending charge.

        Returns:
            This ``Results``, updated in place.

        Raises:
            BudgetExceeded: When paying would cross the session budget."""
        for r in self._rows:
            if r.charge and (not paths or r.endpoint.path in paths):
                cred = self._hub._pay_mpp(r.charge)
                self._replace(r, self._hub._query_source(r.endpoint, self.query, self.limit, self.threshold, self.history, x_payment=cred))
        return self

    def retry(self, *paths: str) -> "Results":
        """Re-send the sources that were skipped for a reason that can change.

        Covers no credits, over budget, unreachable, and rate limited. Rows you skipped yourself are
        left alone.

        Args:
            *paths: Only these sources. Leave empty to retry every retryable row.

        Returns:
            This ``Results``, updated in place."""
        again = [r for r in self._rows if (not paths or r.endpoint.path in paths)
                 and r.skipped and r.reason is not None and r.reason.retryable]
        if not again:
            return self
        fresh = self._hub.search(self.query, sources=[r.endpoint for r in again], limit=self.limit,
                                 similarity_threshold=self.threshold, history=self.history).execute()
        for old, new in zip(again, fresh):
            self._replace(old, new)
        return self

    def proceed(self, *paths: str) -> "Results":
        """Send the sources that pre-flight held as over budget, accepting the cost.

        Args:
            *paths: Only these sources. Leave empty to send every held row.

        Returns:
            This ``Results``, updated in place."""
        for r in list(self._rows):
            if r.reason is SkipReason.OVER_BUDGET and (not paths or r.endpoint.path in paths):
                self._replace(r, self._hub._query_source(r.endpoint, self.query, self.limit, self.threshold, self.history))
        return self

    def skip(self, *paths: str) -> "Results":
        """Mark sources as skipped by you, so ``retry()`` leaves them alone.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            This ``Results``, updated in place."""
        for r in self._rows:
            if r.endpoint.path in paths and not r.ok:
                r.outcome, r.reason, r.topup, r.charge = Outcome.SKIPPED, SkipReason.BY_USER, None, None
        return self

    def _replace(self, old: SourceResult, new: SourceResult) -> None:
        self._rows[self._rows.index(old)] = new

    # -- next steps -------------------------------------------------------------------
    def chat(self, models, *, via: str = "direct", include: str = "both") -> "Chat":
        """Talk to one model, or several, about these results.

        Pre-flight runs on every model right away, so you see the price per message and your balance.
        Nothing is sent until ``.send(prompt)``.

        Args:
            models: One model path, or a list of them, for example ``["ivan/gpt-mini", "bob/llama-3"]``.
            via: ``"direct"`` asks the model's Space; ``"aggregator"`` routes through the Aggregator.
            include: What the models get as context: ``"references"`` for the passages, ``"summaries"``
                for other endpoints' answers, or ``"both"``.

        Returns:
            A ``Chat`` over these results."""
        return Chat(self._hub, models, sources=None, via=via, fixed=self, include=include)

    def ask(self, model: Endpoint | str, prompt: str | None = None) -> "Reply":
        """Ask one model one question about these results, with no thread kept.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.
            prompt: The question. Leave empty to ask for a summary of the results.

        Returns:
            A ``Reply``: the answer, or a skipped reply with its top-up attached."""
        return self.chat(model).send(prompt or self.query)[0]

    def aggregate(self, model: Endpoint | str, prompt: str | None = None, *, aggregator: str | None = None) -> Answer:
        """Hand the passages to the Aggregator to rerank them and generate one answer.

        The Aggregator route does not exist yet; this is a proposal for its shape.

        Args:
            model: The model the Aggregator should use for the answer.
            prompt: The question. Leave empty to ask for a summary.
            aggregator: Another Aggregator URL, instead of the one the session was opened with.

        Returns:
            An ``Answer`` with citations."""
        m = self._hub.get(model) if isinstance(model, str) else model
        ans = self._hub._aggregate(self, m, prompt or self.query, aggregator)
        ans.results = self
        return ans


# --------------------------------------------------------------------------- chat
class Reply:
    """One model's answer to one message, or a skipped model with its action attached.

    A reply has the same three outcomes as a search row: answered, skipped with a reason, or waiting
    on a payment."""

    def __init__(self, chat: "Chat", model: Endpoint, prompt: str, model_result: SourceResult,
                 results: Results | None, citations: dict[int, str], turn: int) -> None:
        self.chat, self.model, self.prompt, self.model_result = chat, model, prompt, model_result
        self.results, self.citations, self.turn = results, citations, turn
        self.context: Context | None = None
        self.searched = False          # True when this turn ran its own search (hub.chat with sources)

    @property
    def outcome(self) -> Outcome:
        """``success``, ``skipped``, or ``payment_required``."""
        return self.model_result.outcome

    @property
    def reason(self) -> SkipReason | None:
        """Why the model was skipped, when it was."""
        return self.model_result.reason

    @property
    def text(self) -> str | None:
        """The answer, or ``None`` when the model did not answer."""
        return self.model_result.summary

    @property
    def ok(self) -> bool:
        """``True`` when the model answered."""
        return self.model_result.ok

    @property
    def pending(self) -> list[TopUp | Charge]:
        """The top-up or MPP charge to resolve, when the model was held or asked for a payment."""
        return [x for x in (self.model_result.topup, self.model_result.charge) if x]

    @property
    def charges(self) -> list[dict[str, Any]]:
        """This model's payment entries for the turn. The turn's search, if any, is on ``Replies.charges``."""
        return _charges([self.model_result])

    @property
    def cost(self) -> dict[str, float]:
        """What this model charged for the turn, per currency."""
        return _totals(self.charges)

    def top_up(self, *, bundle: str) -> TopUp:
        """Buy a credit bundle for this model's wallet.

        Args:
            bundle: The bundle's id, for example ``"starter"``.

        Returns:
            The ``TopUp`` with the Space's invoice attached."""
        return self.chat.top_up(self.model.path, bundle=bundle)

    def _repr_html_(self) -> str:
        return render.reply_card(self)

    def __repr__(self) -> str:
        if self.ok:
            return f"Reply({self.model.path}: {self.text[:60]}…)"
        return f"Reply({self.model.path}: {self.outcome.value}{' ' + self.reason.value if self.reason else ''})"


class Replies:
    """What one ``send`` returns: a reply from every model that was asked.

    Index it by model path or by position. When only one model is in the room, ``text``, ``ok`` and
    ``citations`` pass straight through to that reply."""

    def __init__(self, chat: "Chat", prompt: str, turn: int, replies: list[Reply], results: Results | None,
                 searched: bool) -> None:
        self.chat, self.prompt, self.turn = chat, prompt, turn
        self._replies, self.results, self.searched = replies, results, searched

    def __getitem__(self, key: str | int) -> Reply:
        """One model's reply.

        Args:
            key: The model as ``owner/slug``, or its position in tab order.

        Returns:
            The ``Reply``."""
        if isinstance(key, int):
            return self._replies[key]
        for r in self._replies:
            if r.model.path == key:
                return r
        raise KeyError(f"{key}: this turn was answered by {', '.join(self.models)}")

    def __iter__(self) -> Iterator[Reply]:
        return iter(self._replies)

    def __len__(self) -> int:
        return len(self._replies)

    @property
    def models(self) -> list[str]:
        """The paths of the models asked this turn, in tab order."""
        return [r.model.path for r in self._replies]

    def _sole(self) -> Reply:
        if len(self._replies) != 1:
            raise AttributeError(f"this turn has {len(self._replies)} replies; pick one: replies[{self.models[0]!r}], …")
        return self._replies[0]

    @property
    def text(self) -> str | None:
        """The answer, when one model was asked.

        Raises:
            AttributeError: When several models answered. Index by model path instead."""
        return self._sole().text

    @property
    def citations(self) -> dict[int, str]:
        """The citations, when one model was asked.

        Raises:
            AttributeError: When several models answered."""
        return self._sole().citations

    @property
    def reason(self) -> SkipReason | None:
        """The skip reason, when one model was asked.

        Raises:
            AttributeError: When several models answered."""
        return self._sole().reason

    @property
    def ok(self) -> bool:
        """``True`` when at least one model answered."""
        return any(r.ok for r in self._replies)

    @property
    def context(self) -> "Context | None":
        """What this message carried to the models: earlier turns and passages."""
        return self._replies[0].context if self._replies else None

    @property
    def pending(self) -> list[TopUp | Charge]:
        """Every top-up or MPP charge attached to this turn's replies."""
        return [x for r in self._replies for x in r.pending]

    @property
    def charges(self) -> list[dict[str, Any]]:
        """Payment entries for this turn: one per model, plus the turn's search when there was one."""
        rows = [r.model_result for r in self._replies]
        if self.searched and self.results is not None:
            rows += list(self.results)
        return _charges(rows)

    @property
    def cost(self) -> dict[str, float]:
        """What this turn cost, per currency: the models plus the turn's search."""
        return _totals(self.charges)

    def top_up(self, model: str | None = None, *, bundle: str) -> TopUp:
        """Buy a credit bundle for a model that was held this turn.

        Args:
            model: The model as ``owner/slug``. Leave empty when only one model is short.
            bundle: The bundle's id, for example ``"starter"``.

        Returns:
            The ``TopUp`` with the Space's invoice attached."""
        return self.chat.top_up(model, bundle=bundle)

    def _repr_html_(self) -> str:
        return render.replies_card(self)

    def __repr__(self) -> str:
        return f"Replies(turn {self.turn}: " + "; ".join(repr(r) for r in self._replies) + ")"


class Context:
    """Exactly what the next message will carry to the models.

    Two halves: the earlier turns of this chat, then the passages and summaries in citation order.
    Each half is counted in tokens. In a room with several models the questions are shared, but each
    model sees only its own earlier answers."""

    def __init__(self, items: list[tuple[str, str, float | None, str]], include: str, view: Results | None,
                 history: list[dict[str, str]] | None = None,
                 transcripts: dict[str, list[dict[str, str]]] | None = None) -> None:
        self.items = items            # (source path, text, score or None, kind: reference | summary)
        self.include = include
        self.view = view
        self.history = list(history or [])   # the first model's transcript: [{"role": "user"|"assistant", "content": …}]
        self.transcripts = transcripts or {}

    @property
    def source_tokens(self) -> int:
        """A rough token estimate for the passages and summaries, at about four characters per token."""
        return sum(len(t) for _, t, _, _ in self.items) // 4

    @property
    def history_tokens(self) -> int:
        """A rough token estimate for the earlier turns."""
        return sum(len(m["content"]) for m in self.history) // 4

    @property
    def tokens(self) -> int:
        """The two estimates together: everything the next message carries besides the prompt."""
        return self.source_tokens + self.history_tokens

    @property
    def turns(self) -> int:
        """How many earlier turns are included."""
        return len(self.history) // 2

    @property
    def counts(self) -> dict[str, int]:
        """How many passages and how many summaries are included, as ``{"references": n, "summaries": m}``."""
        return {"references": sum(k == "reference" for *_, k in self.items),
                "summaries": sum(k == "summary" for *_, k in self.items)}

    def _repr_html_(self) -> str:
        return render.context_card(self)

    def __repr__(self) -> str:
        c = self.counts
        return (f"Context({self.turns} earlier turns ~{self.history_tokens} tokens, {c['references']} references, "
                f"{c['summaries']} summaries ~{self.source_tokens} tokens)")


def build_context(results: Results | None, include: str, exclude_models: str | list[str],
                  history: list[dict[str, str]] | None = None,
                  transcripts: dict[str, list[dict[str, str]]] | None = None) -> Context:
    excl = {exclude_models} if isinstance(exclude_models, str) else set(exclude_models)
    items: list[tuple[str, str, float | None, str]] = []
    if results is not None and include in ("references", "both"):
        items += [(p, d.content, d.similarity_score, "reference") for p, d in results.documents]
    if results is not None and include in ("summaries", "both"):
        items += [(p, f"(answer from {p}) {a}", None, "summary") for p, a in results.answers.items() if p not in excl]
    return Context(items, include, results, history, transcripts)


class Chat:
    """A room: you ask, one or more models answer, each with its own transcript.

    Open one with ``results.chat(models)`` to talk about a results view, or ``hub.chat(models,
    sources=...)`` to search before every message. Every message goes to every active model. Models
    join with ``add`` and leave with ``remove``. ``context`` shows exactly what the next message will
    carry, ``use(view)`` swaps the passages, and ``reset()`` starts the thread over. Rendering a chat
    shows one tab per model with its price per message, your balance, and its transcript."""

    def __init__(self, hub: "Hub", models, sources: list | None, *, via: str = "direct",
                 limit: int = 5, fixed: Results | None = None, include: str = "both") -> None:
        self._hub = hub
        self.models: list[Endpoint] = []          # every model that was ever in the room, in tab order
        self.active: list[str] = []               # paths currently asked
        self.transcripts: dict[str, list[dict[str, str]]] = {}
        self.joined_at: dict[str, int] = {}
        self.left_at: dict[str, int | None] = {}
        self.briefed_with: dict[str, str | None] = {}
        self.sources, self.via, self.limit, self.include = sources, via, limit, include
        self._fixed = fixed
        self._filters: dict[str, Any] = {}      # search-each-turn mode: travels with every turn's search
        self._top: int | None = None
        self._last_results: Results | None = None
        self.turns: list[Replies] = []
        self.preflight = None
        for m in ([models] if isinstance(models, (str, Endpoint)) else list(models)):
            self.add(m, brief=False)

    # -- who is in the room -------------------------------------------------------------
    @property
    def turn(self) -> int:
        """How many messages have been answered by at least one model."""
        return sum(1 for t in self.turns if t.ok)

    def _ep(self, model) -> Endpoint:
        return self._hub.get(model) if isinstance(model, str) else model

    def add(self, model, *, brief: bool = True) -> "Chat":
        """Bring another model into the room from the next message on.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.
            brief: ``True`` shows the newcomer the lead model's transcript so far, with the earlier
                answers labelled as another model's. ``False`` gives it only the passages.

        Returns:
            This chat. Pre-flight for the new model has run; nothing is sent."""
        ep = self._ep(model)
        if ep.path in self.active:
            return self
        lead = self.active[0] if self.active else None
        if ep.path not in self.transcripts:
            self.models.append(ep)
        self.active.append(ep.path)
        self.joined_at[ep.path] = self.turn + 1
        self.left_at[ep.path] = None
        if brief and lead and self.transcripts.get(lead):
            self.transcripts[ep.path] = [dict(m) for m in self.transcripts[lead]]
            self.briefed_with[ep.path] = lead
        else:
            self.transcripts.setdefault(ep.path, [])
            self.briefed_with[ep.path] = None
        self._rebuild_preflight()
        return self

    def remove(self, model) -> "Chat":
        """Stop asking a model.

        Its tab and transcript stay readable; it is just not sent any more messages.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.

        Returns:
            This chat."""
        ep = self._ep(model)
        if ep.path not in self.active:
            raise KeyError(f"{ep.path} is not in this chat (asked: {', '.join(self.active) or 'nobody'})")
        self.active.remove(ep.path)
        self.left_at[ep.path] = self.turn
        self._rebuild_preflight()
        return self

    def _rebuild_preflight(self) -> None:
        from .search import build_search
        eps = [m for m in self.models if m.path in self.active]
        self.preflight = build_search(self._hub, "", eps, limit=1, threshold=0.0, history=[])
        self.preflight.kind = "chat"

    @property
    def model(self) -> Endpoint:
        """The lead model: the first one in the room that is still active."""
        if not self.active:
            raise RunNotReady("no model in this chat: chat.add(model)")
        return next(m for m in self.models if m.path == self.active[0])

    def endpoint(self, path: str) -> Endpoint:
        """The record of a model in this room.

        Args:
            path: The model as ``owner/slug``.

        Returns:
            Its ``Endpoint``."""
        return next(m for m in self.models if m.path == path)

    # -- pre-flight on the models -------------------------------------------------------
    def refresh(self) -> "Chat":
        """Run pre-flight again for every active model, for example after paying.

        Returns:
            This chat."""
        self.preflight.refresh()
        return self

    @property
    def rows(self) -> dict[str, Any]:
        """Each active model's pre-flight row, keyed by path."""
        return {r.endpoint.path: r for r in self.preflight.rows}

    @property
    def row(self):
        """The lead model's pre-flight row."""
        return self.rows[self.model.path]

    @property
    def pending(self) -> list[TopUp]:
        """One ``TopUp`` per wallet that pre-flight found short."""
        return self.preflight.pending

    def top_up(self, model: str | None = None, *, bundle: str) -> TopUp:
        """Buy a credit bundle for a model whose wallet is short.

        Args:
            model: The model as ``owner/slug``. Leave empty when only one model is short.
            bundle: The bundle's id, for example ``"starter"``.

        Returns:
            The ``TopUp`` with the Space's invoice attached. Pay at its ``checkout_url``, then just
            ``send``."""
        short = [t for t in self.pending]
        if not short:
            raise RunNotReady("no model in this chat is short of credits")
        if model is None:
            if len(short) > 1:
                raise RunNotReady("several models are short: name one, chat.top_up('owner/model', bundle=…)")
            model = short[0].waiting[0]
        return self.preflight.top_up(model, bundle=bundle)

    # -- what goes to the models ----------------------------------------------------------
    @property
    def view(self) -> Results | None:
        """The ``Results`` the passages come from. For a chat that searches every message, the last message's results."""
        return self._fixed if self._fixed is not None else self._last_results

    @property
    def history(self) -> list[dict[str, str]]:
        """The lead model's transcript, in the shape a Space's ``messages`` field takes. Pass it to ``hub.search(history=...)`` to share the thread with Spaces."""
        return list(self.transcripts.get(self.active[0], [])) if self.active else []

    @property
    def context(self) -> Context:
        """What the next message will carry: the earlier turns per model, then the passages, with token counts."""
        return build_context(self.view, self.include, self.active, self.history,
                             {p: self.transcripts[p] for p in self.active})

    def use(self, view: Results, *, include: str | None = None) -> "Chat":
        """Change which results the passages come from, keeping the conversation.

        Args:
            view: Any ``Results`` view, for example ``recent.top(3)`` or ``chat.view + more``.
            include: ``"references"``, ``"summaries"``, or ``"both"``. Leave empty to keep the current
                setting.

        Returns:
            This chat."""
        self._fixed = view
        if include:
            self.include = include
        return self

    def filter(self, **filters: Any) -> "Chat":
        """Only use passages whose metadata matches.

        On a chat over fixed results this narrows the view. On a chat that searches every message the
        filter travels with each search, to the Space where it can and into this client otherwise.

        Args:
            **filters: Conditions such as ``published_gte="2024-01-01"``. Same syntax as
                ``Search.filter``.

        Returns:
            This chat."""
        if self._fixed is not None:
            return self.use(self._fixed.filter(**filters))
        self._filters.update(filters)
        return self

    def only(self, *paths: str) -> "Chat":
        """Keep only these sources in the view.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            This chat."""
        return self.use(self._fixed.only(*paths)) if self._fixed is not None else self

    def drop(self, *paths: str) -> "Chat":
        """Hide these sources from the view.

        Args:
            *paths: Sources as ``owner/slug``.

        Returns:
            This chat."""
        return self.use(self._fixed.drop(*paths)) if self._fixed is not None else self

    def top(self, k: int) -> "Chat":
        """Keep only the best passages.

        On a chat that searches every message, this applies to each message's results.

        Args:
            k: How many passages to keep.

        Returns:
            This chat."""
        if self._fixed is not None:
            return self.use(self._fixed.top(k))
        self._top = k
        return self

    def reset(self) -> "Chat":
        """Start the thread over.

        Every model's earlier turns are dropped. The results view and the pre-flights stay.

        Returns:
            This chat."""
        for p in self.transcripts:
            self.transcripts[p] = []
        return self

    # -- a turn -----------------------------------------------------------------------
    def send(self, prompt: str) -> Replies:
        """Send a message to every active model.

        Each model gets the passages, its own transcript, and your message. A model whose wallet is short
        is not called at all: its reply is skipped with the top-up attached, and the others still answer.

        Args:
            prompt: Your message.

        Returns:
            ``Replies``, one per active model, indexable by model path."""
        if not self.active:
            raise RunNotReady("no model in this chat: chat.add(model)")
        self.refresh()
        results = self._fixed
        searched = self._fixed is None and bool(self.sources)
        if searched:
            search = self._hub.search(prompt, sources=self.sources, limit=self.limit, history=self.history)
            if self._filters:
                search.filter(**self._filters)
            results = search.execute()
            if self._top:
                results = results.top(self._top)
            self._last_results = results
        ctx = build_context(results, self.include, self.active, self.history,
                            {p: self.transcripts[p] for p in self.active})
        cites = {i: p for i, (p, *_rest) in enumerate(ctx.items, 1)}
        context = "\n".join(f"[{i}] {t}" for i, (_, t, *_r) in enumerate(ctx.items, 1))
        turn = self.turn + 1
        rows = self.rows

        def one(path: str) -> Reply:
            ep = self.endpoint(path)
            row = rows[path]
            system = []
            if ctx.items:
                system.append({"role": "system", "content": "Answer using the numbered context. Cite as [n].\n" + context})
            if self.briefed_with.get(path) and self.transcripts[path] and not any(
                    m["role"] == "assistant" and m.get("by") == path for m in self.transcripts[path]):
                system.append({"role": "system", "content": f"Earlier answers in this conversation were given by "
                                                            f"{self.briefed_with[path]}; continue from them."})
            messages = system + [{"role": m["role"], "content": m["content"]} for m in self.transcripts[path]] \
                + [{"role": "user", "content": prompt}]
            if not row.send:   # pre-flight held the model: no round trip
                mr = SourceResult(ep, 0, {}, Outcome.SKIPPED, row.hold_reason, 0, predicted=True, note=row.note)
                if row.hold_reason is SkipReason.NO_CREDITS:
                    mr.topup = TopUp(ep, row.wallet, row.estimate, invoice=self.preflight._invoices.get(row.wallet.key))
            else:
                mr = self._hub._query_source(ep, prompt, 1, 0.0, [], messages=messages, max_tokens=300)
            r = Reply(self, ep, prompt, mr, results, cites, turn)
            r.context, r.searched = ctx, searched
            return r

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(one, list(self.active)))
        for r in replies:
            if r.ok:
                self.transcripts[r.model.path] += [{"role": "user", "content": prompt},
                                                   {"role": "assistant", "content": r.text, "by": r.model.path}]
        out = Replies(self, prompt, turn, replies, results, searched)
        self.turns.append(out)
        return out

    @property
    def last(self) -> Replies:
        """The replies to the most recent message."""
        return self.turns[-1]

    @property
    def spent(self) -> dict[str, float]:
        """What the whole room has cost so far, per currency. Currencies are never converted."""
        out: dict[str, float] = {}
        for t in self.turns:
            for k, v in t.cost.items():
                out[k] = round(out.get(k, 0.0) + v, 6)
        return out

    def spent_by(self, path: str) -> dict[str, float]:
        """One model's share of the room's spend.

        Args:
            path: The model as ``owner/slug``.

        Returns:
            Its spend so far, per currency."""
        out: dict[str, float] = {}
        for t in self.turns:
            for r in t:
                if r.model.path == path:
                    for k, v in r.cost.items():
                        out[k] = round(out.get(k, 0.0) + v, 6)
        return out

    def _repr_html_(self) -> str:
        return render.chat_card(self)

    def __repr__(self) -> str:
        return f"Chat(models={self.active}, via={self.via}, turns={len(self.turns)})"


# --------------------------------------------------------------------------- helpers
def _charges(rows) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        for e in r.policy_metadata.get("entries", []):
            if e.get("kind") != "payment":
                continue
            tx = e.get("transaction") or {}
            out.append({"source": r.endpoint.path, "policy_type": e.get("policy_type"), "status": e.get("status"),
                        "amount": e.get("amount"), "currency": e.get("currency"),
                        "wallet": r.endpoint.pricing.wallet_id, "rail": tx.get("rail") or r.endpoint.pricing.rail.value,
                        "transaction_id": tx.get("id"), "details": e.get("details") or {}})
    return out


def _totals(charges) -> dict[str, float]:
    tot: dict[str, float] = {}
    for c in charges:
        if c["amount"] is None:
            continue
        sign = -1 if c["status"] == "refunded" else 1 if c["status"] == "charged" else 0
        cur = c["currency"] or "USD"
        tot[cur] = round(tot.get(cur, 0.0) + sign * c["amount"], 6)
    return tot
