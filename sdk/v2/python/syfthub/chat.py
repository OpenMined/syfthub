"""A chat is a room: you ask, one or more models answer, each keeping its own transcript.

The room mutates in place; it is the one stateful object in the SDK. Replies are frozen snapshots.
A model is a Space endpoint, so a chat has the same pre-flight, holds and top-ups as a search."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

from .errors import InvalidState
from .models import (Charge, ChargeEntry, Endpoint, Include, Invoice, Message, Money, Outcome, PlanRow, Reason, Role,
                     SourceResult, TopUp, Via, total, validate_filters)
from .results import Results
from .search import build_rows, pending_topups

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub


# ---------------------------------------------------------------------------------- snapshots
@dataclass(frozen=True)
class Context:
    """Exactly what the next message will carry to the models: earlier turns, then passages, with token counts.

    Attributes:
        items: ``(source path, text, score or None, kind)`` in citation order; kind is ``reference`` or ``summary``.
        include: What kinds were included.
        view: The results the passages come from.
        history: The lead model's transcript.
        transcripts: Every active model's transcript."""
    items: tuple[tuple[str, str, float | None, str], ...]
    include: Include
    view: Results | None
    history: tuple[Message, ...] = ()
    transcripts: dict[str, tuple[Message, ...]] = field(default_factory=dict)

    @property
    def source_tokens(self) -> int:
        """A rough token estimate for the passages and summaries, at about four characters per token."""
        return sum(len(t) for _, t, _, _ in self.items) // 4

    @property
    def history_tokens(self) -> int:
        """A rough token estimate for the earlier turns."""
        return sum(len(m.content) for m in self.history) // 4

    @property
    def tokens(self) -> int:
        """Everything the next message carries besides the prompt."""
        return self.source_tokens + self.history_tokens

    @property
    def turns(self) -> int:
        """How many earlier turns are included."""
        return len(self.history) // 2

    @property
    def counts(self) -> dict[str, int]:
        """``{"references": n, "summaries": m}``."""
        return {"references": sum(k == "reference" for *_, k in self.items),
                "summaries": sum(k == "summary" for *_, k in self.items)}

    def _repr_html_(self) -> str:
        from .notebook import render
        return render.context_card(self)

    def __repr__(self) -> str:
        c = self.counts
        return (f"Context({self.turns} earlier turns ~{self.history_tokens} tokens, {c['references']} references, "
                f"{c['summaries']} summaries ~{self.source_tokens} tokens)")


@dataclass(frozen=True)
class Reply:
    """One model's answer to one message, or a model that did not answer with its action attached. A snapshot.

    Attributes:
        model: The model.
        prompt: Your message.
        result: The model's Space response, classified like a search row.
        citations: Which source each ``[n]`` marker points at.
        turn: The shared turn number.
        context: What the message carried.
        searched: ``True`` when this turn ran its own search."""
    model: Endpoint
    prompt: str
    result: SourceResult
    citations: dict[int, str]
    turn: int
    context: Context
    searched: bool = False

    @property
    def outcome(self) -> Outcome:
        """What happened."""
        return self.result.outcome

    @property
    def reason(self) -> Reason | None:
        """Why the model did not answer, when it did not."""
        return self.result.reason

    @property
    def text(self) -> str | None:
        """The answer, or ``None`` when the model did not answer."""
        return self.result.summary

    @property
    def ok(self) -> bool:
        """``True`` when the model answered."""
        return self.result.ok

    @property
    def pending(self) -> list[TopUp | Charge]:
        """The top-up or MPP charge to resolve, when the model was held or asked for a payment."""
        return [x for x in (self.result.topup, self.result.charge) if x]

    @property
    def charges(self) -> list[ChargeEntry]:
        """This model's payment entries for the turn."""
        return self.result.charges

    @property
    def cost(self) -> dict[str, Money]:
        """What this model charged for the turn, per currency."""
        return total(c.signed for c in self.charges)

    def _repr_html_(self) -> str:
        from .notebook import render
        return render.reply_card(self)

    def __repr__(self) -> str:
        if self.ok:
            return f"Reply({self.model.path}: {self.text[:60]}…)"
        return f"Reply({self.model.path}: {self.outcome.value}{' ' + self.reason.value if self.reason else ''})"


@dataclass(frozen=True)
class Replies:
    """What one ``send`` returns: a reply from every model that was asked. A snapshot.

    Index by model path or by position. When one model was asked, ``text``, ``ok`` and ``citations`` pass
    straight through to it.

    Attributes:
        prompt: Your message.
        turn: The shared turn number.
        results: The search behind this turn, when the chat searches every message.
        searched: ``True`` when this turn ran its own search.
        spent_so_far: The room's total after this turn, per currency."""
    prompt: str
    turn: int
    _replies: tuple[Reply, ...]
    results: Results | None
    searched: bool
    spent_so_far: dict[str, Money]

    def __getitem__(self, key: str | int) -> Reply:
        """One model's reply, by ``owner/slug`` or position.

        Raises:
            KeyError: When no model by that path answered this turn."""
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
            raise InvalidState(f"this turn has {len(self._replies)} replies; pick one: replies[{self.models[0]!r}]")
        return self._replies[0]

    @property
    def text(self) -> str | None:
        """The answer, when one model was asked.

        Raises:
            InvalidState: When several models answered; index by model path instead."""
        return self._sole().text

    @property
    def citations(self) -> dict[int, str]:
        """The citations, when one model was asked."""
        return self._sole().citations

    @property
    def reason(self) -> Reason | None:
        """The reason, when one model was asked and did not answer."""
        return self._sole().reason

    @property
    def ok(self) -> bool:
        """``True`` when at least one model answered."""
        return any(r.ok for r in self._replies)

    @property
    def context(self) -> Context | None:
        """What this message carried to the models."""
        return self._replies[0].context if self._replies else None

    @property
    def pending(self) -> list[TopUp | Charge]:
        """Every top-up or MPP charge attached to this turn's replies."""
        return [x for r in self._replies for x in r.pending]

    @property
    def charges(self) -> list[ChargeEntry]:
        """Payment entries for this turn: one per model, plus the turn's search when there was one."""
        out = [c for r in self._replies for c in r.charges]
        if self.searched and self.results is not None:
            out += self.results.charges
        return out

    @property
    def cost(self) -> dict[str, Money]:
        """What this turn cost, per currency: the models plus the turn's search."""
        return total(c.signed for c in self.charges)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict of this turn."""
        return {"prompt": self.prompt, "turn": self.turn, "searched": self.searched,
                "replies": [{"model": r.model.path, "outcome": r.outcome.value, "reason": r.reason.value if r.reason else None,
                             "text": r.text, "citations": r.citations, "cost": {k: str(v.amount) for k, v in r.cost.items()}}
                            for r in self._replies],
                "results": self.results.to_dict() if self.results is not None else None}

    def _repr_html_(self) -> str:
        from .notebook import render
        return render.replies_card(self)

    def __repr__(self) -> str:
        return f"Replies(turn {self.turn}: " + "; ".join(repr(r) for r in self._replies) + ")"


def build_context(results: Results | None, include: Include, exclude: list[str], history: list[Message],
                  transcripts: dict[str, list[Message]]) -> Context:
    items: list[tuple[str, str, float | None, str]] = []
    if results is not None and include in (Include.REFERENCES, Include.BOTH):
        items += [(p, d.content, d.similarity_score, "reference") for p, d in results.documents]
    if results is not None and include in (Include.SUMMARIES, Include.BOTH):
        items += [(p, f"(answer from {p}) {a}", None, "summary") for p, a in results.answers.items() if p not in exclude]
    return Context(tuple(items), include, results, tuple(history), {p: tuple(m) for p, m in transcripts.items()})


# ---------------------------------------------------------------------------------- the room
class Chat:
    """A room: you ask, one or more models answer, each with its own transcript.

    Open one with ``results.chat(models)`` to talk about a results view, or ``hub.chat(models, sources=...)``
    to search before every message. Every message goes to every active model. Models join with ``add`` and
    leave with ``remove``; ``fork()`` branches the conversation. ``context`` shows exactly what the next
    message will carry, ``use(view)`` swaps the passages, ``reset()`` drops the turns.

    The room mutates in place. Sends are serialised, so concurrent ``send`` calls never interleave."""

    def __init__(self, hub: "AsyncHub", models, sources: list | None, *, via: Via | str = Via.DIRECT, limit: int = 5,
                 fixed: Results | None = None, include: Include | str = Include.BOTH) -> None:
        self._hub = hub
        self.models: list[Endpoint] = []          # every model ever in the room, in tab order
        self.active: list[str] = []
        self.transcripts: dict[str, list[Message]] = {}
        self.joined_at: dict[str, int] = {}
        self.left_at: dict[str, int | None] = {}
        self.briefed_with: dict[str, str | None] = {}
        self.sources, self.via, self.limit, self.include = sources, Via(via), limit, Include(include)
        self._fixed = fixed
        self._filters: dict[str, Any] = {}
        self._top: int | None = None
        self._last_results: Results | None = None
        self.turns: list[Replies] = []
        self._rows: dict[str, PlanRow] = {}
        self._pending_models: list = [models] if isinstance(models, (str, Endpoint)) else list(models)
        self._lock = asyncio.Lock()
        self._resolved = False

    async def _resolve_models(self) -> None:
        if not self._resolved:
            self._resolved = True
            for m in self._pending_models:
                await self.add(m, brief=False)
            self._pending_models = []

    # -- who is in the room ------------------------------------------------------------------
    @property
    def turn(self) -> int:
        """How many messages have been answered by at least one model."""
        return sum(1 for t in self.turns if t.ok)

    async def _ep(self, model) -> Endpoint:
        return await self._hub.endpoints.get(model) if isinstance(model, str) else model

    async def add(self, model, *, brief: bool = True) -> "Chat":
        """Bring another model into the room from the next message on.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.
            brief: ``True`` shows the newcomer the lead model's transcript so far, with the earlier answers
                labelled as another model's. ``False`` gives it only the passages.

        Returns:
            This room. Pre-flight for the new model has run; nothing is sent."""
        await self._resolve_models()
        ep = await self._ep(model)
        if ep.path in self.active:
            return self
        lead = self.active[0] if self.active else None
        if ep.path not in self.transcripts:
            self.models.append(ep)
        self.active.append(ep.path)
        self.joined_at[ep.path] = self.turn + 1
        self.left_at[ep.path] = None
        if brief and lead and self.transcripts.get(lead):
            self.transcripts[ep.path] = list(self.transcripts[lead])
            self.briefed_with[ep.path] = lead
        else:
            self.transcripts.setdefault(ep.path, [])
            self.briefed_with[ep.path] = None
        await self.preflight()
        return self

    async def remove(self, model) -> "Chat":
        """Stop asking a model. Its tab and transcript stay readable.

        Args:
            model: The model as ``owner/slug`` or an ``Endpoint``.

        Returns:
            This room.

        Raises:
            InvalidState: When the model is not in the room."""
        await self._resolve_models()
        ep = await self._ep(model)
        if ep.path not in self.active:
            raise InvalidState(f"{ep.path} is not in this chat (asked: {', '.join(self.active) or 'nobody'})")
        self.active.remove(ep.path)
        self.left_at[ep.path] = self.turn
        await self.preflight()
        return self

    def fork(self) -> "Chat":
        """An independent copy of the room with the transcript so far. Use it to compare two views over one
        conversation, since the narrowing verbs change the room in place.

        Returns:
            A new ``Chat``."""
        c = Chat(self._hub, [], self.sources, via=self.via, limit=self.limit, fixed=self._fixed, include=self.include)
        c._resolved = True
        c.models, c.active = list(self.models), list(self.active)
        c.transcripts = {p: list(m) for p, m in self.transcripts.items()}
        c.joined_at, c.left_at, c.briefed_with = dict(self.joined_at), dict(self.left_at), dict(self.briefed_with)
        c._filters, c._top, c._last_results = dict(self._filters), self._top, self._last_results
        c.turns, c._rows = list(self.turns), dict(self._rows)
        return c

    @property
    def lead(self) -> Endpoint:
        """The lead model: the first one in the room that is still active.

        Raises:
            InvalidState: When no model is active."""
        if not self.active:
            raise InvalidState("no model in this chat: await chat.add(model)")
        return next(m for m in self.models if m.path == self.active[0])

    def endpoint(self, path: str) -> Endpoint:
        """The record of a model in this room.

        Args:
            path: The model as ``owner/slug``.

        Returns:
            Its ``Endpoint``."""
        return next(m for m in self.models if m.path == path)

    # -- pre-flight on the models -----------------------------------------------------------
    async def preflight(self) -> "Chat":
        """Run pre-flight for every active model: price per message, your balance, a verdict.

        Returns:
            This room."""
        await self._resolve_models()
        eps = [m for m in self.models if m.path in self.active]
        self._rows = {r.endpoint.path: r for r in await build_rows(self._hub, eps, limit=1)}
        return self

    @property
    def rows(self) -> dict[str, PlanRow]:
        """Each active model's pre-flight row, keyed by path."""
        return dict(self._rows)

    @property
    def pending(self) -> list[TopUp]:
        """One ``TopUp`` per wallet that pre-flight found short."""
        return pending_topups(self._rows.values())

    async def top_up(self, model: str | None = None, *, bundle: str) -> Invoice:
        """Buy a credit bundle for a model whose wallet is short.

        Args:
            model: The model as ``owner/slug``. Leave empty when only one model is short.
            bundle: The bundle id.

        Returns:
            The ``Invoice``. Pay at its ``checkout_url``, then just ``send``.

        Raises:
            InvalidState: When no model is short, or several are and none was named."""
        short = self.pending
        if not short:
            raise InvalidState("no model in this chat is short of credits")
        if model is None:
            if len(short) > 1:
                raise InvalidState("several models are short: name one, chat.top_up('owner/model', bundle=...)")
            return await short[0].buy(bundle)
        for t in short:
            if model in t.waiting or t.wallet.key == model:
                return await t.buy(bundle)
        raise InvalidState(f"{model} is not short of credits in this chat")

    # -- what goes to the models -------------------------------------------------------------
    @property
    def view(self) -> Results | None:
        """The ``Results`` the passages come from. For a chat that searches every message, the last message's."""
        return self._fixed if self._fixed is not None else self._last_results

    @property
    def history(self) -> list[Message]:
        """The lead model's transcript. Pass it to ``hub.search(history=...)`` to share the thread with Spaces."""
        return list(self.transcripts.get(self.active[0], [])) if self.active else []

    @property
    def context(self) -> Context:
        """What the next message will carry: the earlier turns per model, then the passages, with token counts."""
        return build_context(self.view, self.include, self.active, self.history,
                             {p: self.transcripts[p] for p in self.active})

    def use(self, view: Results, *, include: Include | str | None = None) -> "Chat":
        """Change which results the passages come from, keeping the conversation.

        Args:
            view: Any ``Results`` view, for example ``recent.top(3)`` or ``chat.view + more``.
            include: Passages, summaries, or both. Leave empty to keep the current setting.

        Returns:
            This room."""
        self._fixed = view
        if include is not None:
            self.include = Include(include)
        return self

    def filter(self, **filters: Any) -> "Chat":
        """Only use passages whose metadata matches.

        On a chat over fixed results this narrows the view. On a chat that searches every message the filter
        travels with each search, to the Space where it can and into this client otherwise.

        Args:
            **filters: Same syntax as ``SearchPlan.filter``.

        Returns:
            This room."""
        validate_filters(filters)
        if self._fixed is not None:
            return self.use(self._fixed.filter(**filters))
        self._filters.update(filters)
        return self

    def only(self, *paths: str) -> "Chat":
        """Keep only these sources in the view. Returns this room."""
        return self.use(self._fixed.only(*paths)) if self._fixed is not None else self

    def drop(self, *paths: str) -> "Chat":
        """Hide these sources from the view. Returns this room."""
        return self.use(self._fixed.drop(*paths)) if self._fixed is not None else self

    def top(self, k: int) -> "Chat":
        """Keep only the best passages. On a chat that searches every message, applies to each message's results.

        Args:
            k: How many passages to keep.

        Returns:
            This room."""
        if self._fixed is not None:
            return self.use(self._fixed.top(k))
        self._top = k
        return self

    def reset(self) -> "Chat":
        """Drop every model's earlier turns. The results view and the pre-flights stay.

        Returns:
            This room."""
        for p in self.transcripts:
            self.transcripts[p] = []
        return self

    # -- a turn -----------------------------------------------------------------------------
    async def send(self, prompt: str, *, max_tokens: int = 300) -> Replies:
        """Send a message to every active model.

        Each model gets the passages, its own transcript, and your message. A model whose wallet is short is
        not called at all: its reply is held with the top-up attached, and the others still answer.

        Args:
            prompt: Your message.
            max_tokens: How long an answer may be.

        Returns:
            ``Replies``, one per active model.

        Raises:
            InvalidState: When no model is in the room."""
        async with self._lock:
            await self._resolve_models()
            if not self.active:
                raise InvalidState("no model in this chat: await chat.add(model)")
            await self.preflight()
            results = self._fixed
            searched = self._fixed is None and bool(self.sources)
            if searched:
                plan = self._hub.search(prompt, sources=self.sources, limit=self.limit, history=self.history,
                                        filters=self._filters or None)
                results = await plan.execute()
                if self._top:
                    results = results.top(self._top)
                self._last_results = results
            ctx = build_context(results, self.include, self.active, self.history,
                                {p: self.transcripts[p] for p in self.active})
            cites = {i: p for i, (p, *_rest) in enumerate(ctx.items, 1)}
            context = "\n".join(f"[{i}] {t}" for i, (_, t, *_r) in enumerate(ctx.items, 1))
            turn = self.turn + 1

            async def one(path: str) -> Reply:
                ep = self.endpoint(path)
                row = self._rows[path]
                system: list[dict[str, str]] = []
                if ctx.items:
                    system.append({"role": "system", "content": "Answer using the numbered context. Cite as [n].\n" + context})
                if self.briefed_with.get(path) and self.transcripts[path]:
                    system.append({"role": "system", "content": f"Earlier answers in this conversation were given by "
                                                                f"{self.briefed_with[path]}; continue from them."})
                messages = system + [m.wire() for m in self.transcripts[path]] + [{"role": "user", "content": prompt}]
                if not row.send:
                    mr = SourceResult(endpoint=ep, outcome=Outcome.HELD, reason=row.hold_reason, predicted=True, note=row.note)
                    if row.hold_reason is Reason.NO_CREDITS and row.wallet is not None:
                        mr = mr.model_copy(update={"topup": TopUp(endpoint=ep, wallet=row.wallet, needed=row.estimate, waiting=(ep.path,))})
                else:
                    mr = await self._hub._query_source(ep, prompt, 1, 0.0, [], messages=messages, max_tokens=max_tokens)
                return Reply(ep, prompt, mr, cites, turn, ctx, searched)

            replies = await asyncio.gather(*(one(p) for p in list(self.active)))
            for r in replies:
                if r.ok:
                    self.transcripts[r.model.path] += [Message(role=Role.USER, content=prompt),
                                                       Message(role=Role.ASSISTANT, content=r.text or "")]
            out = Replies(prompt, turn, tuple(replies), results, searched, {})
            spent = total([*(v for t in self.turns for v in t.cost.values()), *out.cost.values()])
            out = Replies(prompt, turn, tuple(replies), results, searched, spent)
            self.turns.append(out)
            return out

    @property
    def last(self) -> Replies:
        """The replies to the most recent message.

        Raises:
            InvalidState: Before the first message."""
        if not self.turns:
            raise InvalidState("nothing has been sent yet")
        return self.turns[-1]

    @property
    def spent(self) -> dict[str, Money]:
        """What the whole room has cost so far, per currency. Never converted."""
        return total(v for t in self.turns for v in t.cost.values())

    def spent_by(self, path: str) -> dict[str, Money]:
        """One model's share of the room's spend.

        Args:
            path: The model as ``owner/slug``.

        Returns:
            Its spend so far, per currency."""
        return total(v for t in self.turns for r in t if r.model.path == path for v in r.cost.values())

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict of the room: models, transcripts and every turn."""
        return {"models": [m.path for m in self.models], "active": list(self.active), "via": self.via.value,
                "include": self.include.value, "turns": [t.to_dict() for t in self.turns],
                "transcripts": {p: [m.wire() for m in ms] for p, ms in self.transcripts.items()},
                "spent": {k: str(v.amount) for k, v in self.spent.items()}}

    def _repr_html_(self) -> str:
        from .notebook import render
        return render.chat_card(self)

    def __repr__(self) -> str:
        return f"Chat(models={self.active}, via={self.via.value}, turns={len(self.turns)})"
