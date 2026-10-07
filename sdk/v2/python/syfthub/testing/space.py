"""A fake Syft Space and the shared ``World`` behind every fake.

The Space speaks the shape of ``POST /api/v1/endpoints/{slug}/query``: one JSON body, a
``policy_metadata`` envelope on success and rejection, 402 only for MPP, 403 for everything else a
policy blocks. Time is simulated: ``World.now`` advances when the SDK sleeps, so rate-limit windows
and circuit-breaker cooldowns can be exercised in milliseconds."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import re
from typing import Any

from .._transport import Response
from ..models import EndpointType, PriceUnit, Rail, from_space_filters, match_metadata
from . import data as D


class World:
    """Shared mutable state behind all fakes: balances, invoices, outages, the clock.

    Use it from a notebook or a test to stand in for the outside world:

    - ``world.pay(invoice)``: the user paid at the checkout link and the provider's webhook fired.
    - ``world.space_down(path)`` / ``world.space_up(path)``: a Space goes offline or comes back.
    - ``world.now``: the simulated clock, in seconds; sleeps advance it instantly."""

    def __init__(self, *, time_scale: float = 0.01, latency: tuple[float, float] = (0.15, 0.6)) -> None:
        self.endpoints = {e.path: e for e in D.endpoints()}
        self.prepaid: dict[tuple[str, str], float] = {(w, D.USER["email"]): b for w, b in D.USER["prepaid"].items()}
        self.invoices: dict[str, dict] = {}
        self.down: set[str] = {"grace/archive"}
        self.tokens: dict[str, tuple[str, float]] = {}      # token -> (email, expires_at)
        self.paid_credentials: set[str] = set()
        self.hub_wallet = D.USER["hub_wallet"]
        self.now = 0.0
        self.time_scale = time_scale        # one simulated second costs this many real seconds
        self.latency = latency              # simulated per-call latency range (real seconds)
        self.rate_hits: dict[str, tuple[int, float]] = {"frank/registry": (2, 0.0)}   # path -> (count, window start)
        self.calls: list[dict[str, Any]] = []   # every Space call, for inspection
        self.jobs: dict[str, dict[str, Any]] = {}

    # -- controls for notebooks and tests ---------------------------------------------------
    def pay(self, invoice) -> None:
        """The user paid at the checkout link and the payment provider's webhook credited the wallet."""
        iid = invoice if isinstance(invoice, str) else invoice.id
        inv = self.invoices[iid]
        inv["status"] = "paid"
        self.credit(inv["wallet_id"], inv["user_email"], inv["amount"])

    def space_down(self, path: str) -> None:
        """Take a Space offline: connections to it are refused."""
        self.down.add(path)

    def space_up(self, path: str) -> None:
        """Bring a Space back."""
        self.down.discard(path)

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(seconds * self.time_scale)

    async def _latency(self) -> None:
        await asyncio.sleep(random.uniform(*self.latency) * (self.time_scale / 0.01))

    # -- lookups ------------------------------------------------------------------------------
    def endpoint_at(self, url: str, slug: str):
        for e in self.endpoints.values():
            if e.url == url and e.slug == slug:
                return e
        return None

    def mpp_address(self, slug: str) -> str:
        return "0x" + hashlib.md5(slug.encode()).hexdigest()[:20]

    def email_for(self, token: str) -> str | None:
        hit = self.tokens.get(token)
        if not hit or hit[1] < self.now:
            return None
        return hit[0]

    def balance(self, wallet_id: str | None, email: str) -> float:
        return self.prepaid.get((wallet_id or "", email), 0.0)

    def debit(self, wallet_id: str | None, email: str, amount: float) -> None:
        self.prepaid[(wallet_id or "", email)] = round(self.balance(wallet_id, email) - amount, 6)

    def credit(self, wallet_id: str, email: str, amount: float) -> None:
        self.prepaid[(wallet_id, email)] = round(self.balance(wallet_id, email) + amount, 6)

    def wallet_currency(self, wallet_id: str) -> str:
        for e in self.endpoints.values():
            if e.pricing.wallet_id == wallet_id:
                return e.pricing.currency
        return "USD"

    def bundle(self, wallet_id: str, name: str):
        for e in self.endpoints.values():
            if e.pricing.wallet_id == wallet_id:
                for b in e.pricing.bundles:
                    if b.id == name:
                        return b
        return None

    def new_invoice(self, wallet_id: str, email: str, bundle) -> dict:
        iid = f"inv-{random.randint(10**4, 10**5)}"
        inv = {"id": iid, "wallet_id": wallet_id, "endpoint_id": None, "user_email": email, "provider": "xendit",
               "client_reference": f"syft-{iid}", "checkout_url": f"https://checkout.example/pay/{iid}",
               "provider_session_id": f"sess_{iid}", "bundle_name": bundle.id, "amount": float(bundle.amount.amount),
               "currency": self.wallet_currency(wallet_id), "status": "pending", "paid_at": None,
               "created_at": "2026-10-07T09:00:00Z", "updated_at": "2026-10-07T09:00:00Z"}
        self.invoices[iid] = inv
        return inv

    def verify_payment(self, x_payment: str, amount: float) -> bool:
        return x_payment in self.paid_credentials

    def documents(self, path: str, limit: int, threshold: float, filters: dict | None = None) -> list[dict]:
        want = from_space_filters(filters or {})
        rows = D.CORPUS.get(path, [])
        out = []
        for i, row in enumerate(rows):
            c, s = row[0], row[1]
            meta = dict(row[2]) if len(row) > 2 else {}
            if s >= threshold and match_metadata(meta, want):
                out.append({"document_id": f"{path.split('/')[1]}-{i}", "content": c, "similarity_score": s,
                            "metadata": {"source": path, **meta}})
        return out[:limit]

    def complete(self, path: str, messages, max_tokens: int) -> dict:
        """A scripted model. It reads the numbered context in the system message and the earlier turns, and
        answers the last user message from them, citing only passages that are in context. Deterministic."""
        ctx_text, history, prompt = "", [], ""
        if isinstance(messages, list):
            ctx_text = next((m["content"] for m in messages if m["role"] == "system"), "")
            turns = [m for m in messages if m["role"] != "system"]
            history, prompt = turns[:-1], (turns[-1]["content"] if turns else "")
        else:
            prompt = str(messages or "")
        passages = re.findall(r"^\[(\d+)\] (.*)$", ctx_text, flags=re.M)

        def cite(*words: str) -> list[str]:
            return [n for n, t in passages if any(w in t.lower() for w in words)]

        def tag(ns: list[str]) -> str:
            return "".join(f"[{n}]" for n in ns)

        short = "gpt-mini" in path or "sahabat" in path
        terse = "sahabat" in path
        if "trials-assistant" in path:
            text = ("Across my curated corpus, grade 3+ neutropenia is the dominant phase 3 adverse event (28-41%), with "
                    "febrile neutropenia in 6-12% of patients; hepatic events stay under 2%.")
            return {"id": "cmpl-o", "model": path, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text, "tokens": 44},
                    "usage": {"prompt_tokens": 120, "completion_tokens": 44, "total_tokens": 164}}

        q = prompt.lower()
        followup = bool(history) and not any(w in q for w in ("adverse", "neutropenia", "trial"))
        lead = "Of the events we discussed: " if followup and not terse else ""
        if not passages:
            text = ("Generally: haematological toxicity, GI effects, fatigue. No retrieved context was provided." if short else
                    "I don't have retrieved context for this question, so I can only answer generally: phase 3 oncology "
                    "trials most often report haematological toxicity, gastrointestinal effects and fatigue.")
        elif any(w in q for w in ("fatal", "death", "died", "mortality")):
            d, nd = cite("death", "fatal"), cite("no treatment-related deaths")
            if nd:
                other = [n for n in d if n not in nd]
                text = lead + f"no treatment-related deaths were reported {tag(nd)}" + (
                    f"; the registry lists 3 deaths, all adjudicated unrelated to treatment {tag(other)}." if other else ".")
            elif d:
                text = lead + f"3 deaths were recorded but adjudicated unrelated to the drug {tag(d)}; no passage reports a treatment-related death."
            else:
                text = lead + "none of the passages in context mention deaths, so I cannot say."
        elif any(w in q for w in ("agree", "second opinion", "what would you add")):
            prev = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
            h, d = cite("hepat"), cite("discontinu")
            extra = (f" I would add that discontinuation for toxicity ran at twice the placebo rate {tag(d[:1])}." if d else
                     f" I would add that hepatic events stayed under 2% {tag(h[:1])}." if h else
                     " I have nothing to add from the passages in context.")
            agree = ("Broadly yes: the haematological picture and the SAE rate match the passages." if short else
                     "Yes, both points hold against the passages in context; the registry and the pooled analysis agree on the "
                     "SAE range and the dose-limiting toxicities.")
            text = ((agree if prev else "There is no earlier answer in my transcript to agree with; from the passages:") + extra)
        elif any(w in q for w in ("infection", "consortium", "change the picture", "cardiac")):
            inf, car = cite("infection"), cite("cardiac")
            if inf or car:
                text = lead + ("it adds an infection signal: " + (f"infection-related SAEs were 9.8% across six trials {tag(inf)}" if inf else "")
                               + ("; " if inf and car else "") + (f"cardiac events were rare (1.1%) and concentrated over age 70 {tag(car)}" if car else "")
                               + ". The haematological picture does not change.")
            else:
                text = lead + "nothing in context covers infection or cardiac events, so I cannot say whether the picture changes."
        elif any(w in q for w in ("bullet", "slide", "shorter", "one line", "tl;dr", "summarise that", "summarize that")):
            prev = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
            prev = re.sub(r"^((Of the events we discussed|In short): )+", "", prev)
            parts = [x.strip(" .") for x in re.split(r"[;.] (?=[A-Za-z0-9])", prev) if x.strip(" .")]
            if not parts:
                text = "Nothing to condense yet."
            elif any(w in q for w in ("bullet", "slide")):
                text = "\n".join("• " + x[0].upper() + x[1:] for x in parts[:3])
            else:
                text = parts[0][0].upper() + parts[0][1:] + ("; " + "; ".join(parts[1:2]) if len(parts) > 1 else "") + "."
        elif "discontinu" in q:
            c = cite("discontinu")
            text = lead + (f"discontinuation for toxicity was 12.4% vs 6.1% on placebo {tag(c)}." if c else
                           "no passage in context reports discontinuation rates.")
        elif any(w in q for w in ("hepat", "liver")):
            c = cite("hepat")
            text = lead + (f"hepatic events were infrequent, under 2% and reversible {tag(c)}." if c else
                           "no passage in context reports hepatic events.")
        elif any(w in q for w in ("registry", "registries", "nct")):
            sae, dlt = cite("sae rate"), cite("dose-limiting")
            text = lead + ((f"the registry puts the SAE rate at 21.7% vs 14.2% for the comparator {tag(sae)}" if sae else "") +
                           ("; " if sae and dlt else "") +
                           (f"dose-limiting toxicities were thrombocytopenia and rash {tag(dlt)}" if dlt else "") + "."
                           if sae or dlt else "there are no registry entries in the current context.")
        else:
            n, s_, d = cite("neutropenia"), cite("serious adverse", "sae"), cite("discontinu")
            text = (f"Neutropenia and febrile neutropenia dominated {tag(n[:2])}; SAEs ~22-23% {tag(s_[:2])}"
                    + (f"; discontinuations doubled vs placebo {tag(d[:1])}." if d else ".")) if short else (
                    f"Across the retrieved sources, the most frequently reported phase 3 adverse events were haematological: "
                    f"grade 3+ neutropenia and febrile neutropenia {tag(n[:2])}. Serious adverse events ran at roughly "
                    f"22-23% in the treatment arms {tag(s_[:2])}." + (f" Discontinuation due to toxicity was about twice the "
                    f"placebo rate {tag(d[:1])}." if d else ""))
        if terse and not text.startswith("•"):
            text = "In short: " + text[0].lower() + text[1:]
        ntok = max(12, len(text) // 4)
        hist_tok = sum(len(m["content"]) for m in history) // 4
        ptoks = 60 + len(ctx_text) // 4 + hist_tok + len(prompt) // 4
        return {"id": f"cmpl-{len(history) // 2 + 1}", "model": path, "finish_reason": "stop",
                "message": {"role": "assistant", "content": text, "tokens": ntok},
                "usage": {"prompt_tokens": ptoks, "completion_tokens": ntok, "total_tokens": ptoks + ntok}}


class FakeSpace:
    """One per Space URL. Serves the query route and the prepaid credit routes for its wallets."""

    def __init__(self, url: str, world: World) -> None:
        self.url, self.world = url, world

    # -- helpers ----------------------------------------------------------
    def _challenge(self, slug: str, amount: float) -> str:
        req = base64.urlsafe_b64encode(json.dumps(
            {"amount": f"{amount:.2f}", "currency": "pathUSD", "recipient": self.world.mpp_address(slug)}
        ).encode()).decode().rstrip("=")
        return f'Payment id="{hashlib.sha1(f"{slug}{self.world.now}{random.random()}".encode()).hexdigest()[:12]}", realm="{slug}", method="tempo", intent="charge", request="{req}"'

    @staticmethod
    def _entry(policy_type: str, status: str, **kw: Any) -> dict[str, Any]:
        e = {"policy_type": policy_type, "kind": "payment", "status": status, "amount": None,
             "currency": None, "recipient": None, "transaction": None,
             "reason_code": None, "reason": None, "details": {}}
        e.update(kw)
        return e

    def _reject(self, status: int, outcome: str, detail: str, entries: list[dict], headers=None) -> Response:
        return Response(status, {"detail": detail, "policy_metadata": {"outcome": outcome, "entries": entries}}, headers or {})

    # -- the one route ------------------------------------------------------
    async def query(self, slug: str, *, token: str, body: dict[str, Any], x_payment: str | None = None) -> Response:
        ep = self.world.endpoint_at(self.url, slug)
        self.world.calls.append({"url": self.url, "slug": slug, "body": body, "x_payment": bool(x_payment), "at": self.world.now})
        if ep is None:
            return Response(404, {"detail": f"Endpoint '{slug}' not found"})
        if ep.path in self.world.down:
            raise ConnectionError(f"{self.url}: connection refused")
        email = self.world.email_for(token)
        if not token.startswith("sat.") or email is None:
            return Response(401, {"detail": "Invalid or expired satellite token"})

        await self.world._latency()
        p = ep.pricing
        entries: list[dict] = []

        # access policy -----------------------------------------------------
        acc = ep.policy("access")
        if acc:
            return self._reject(403, "access_denied",
                                "Policy 'access' blocked request: {'allowed_users': [...]}",
                                [self._entry("access", "rejected", kind="access", reason_code="ACCESS_DENIED",
                                             reason="Sender is not on the allow list")])
        # rate limit ---------------------------------------------------------
        rl = ep.policy("rate_limit")
        if rl:
            limit, _, unit = rl.config["limit"].partition("/")
            window = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 60)
            n, start = self.world.rate_hits.get(ep.path, (0, self.world.now))
            if self.world.now - start >= window:
                n, start = 0, self.world.now
            n += 1
            self.world.rate_hits[ep.path] = (n, start)
            if n > int(limit):
                reset = max(1, int(window - (self.world.now - start)))
                return self._reject(403, "rate_limited",
                                    f"Policy 'rate_limit' blocked request: {{'limit': '{rl.config['limit']}', 'remaining': 0}}",
                                    [self._entry("rate_limit", "rejected", kind="rate_limit", reason_code="RATE_LIMITED",
                                                 reason="Rate limit exceeded",
                                                 details={"limit": rl.config["limit"], "remaining": 0, "reset_seconds": reset,
                                                          "scope": "per_user"})])
        # payment pre-hook ----------------------------------------------------
        limit = int(body.get("limit", 5))
        # PROPOSED: ``filters`` in the body, honoured for the fields this endpoint advertises as filterable,
        # applied before ``limit`` so only matching documents are returned (and billed).
        applied = {f: ops for f, ops in (body.get("filters") or {}).items() if f in ep.filterable}
        docs = self.world.documents(ep.path, limit, float(body.get("similarity_threshold", 0.5)), filters=applied)

        def _amount() -> float:
            return round(float(p.price.amount) * (len(docs) if p.unit is PriceUnit.DOCUMENT else 1), 6)

        if p.paid and p.rail is Rail.MPP:
            amount = _amount()
            if not (x_payment and self.world.verify_payment(x_payment, amount)):
                return self._reject(402, "payment_required",
                                    f"Payment of ${amount:.2f} required to query this endpoint",
                                    [self._entry(f"mpp_per_{p.unit.value}", "rejected", amount=amount, currency="USD",
                                                 reason_code="PAYMENT_REQUIRED", details={"documents": len(docs)})],
                                    headers={"WWW-Authenticate": self._challenge(slug, amount)})
            entries.append(self._entry(f"mpp_per_{p.unit.value}", "charged", amount=amount, currency="USD",
                                       recipient={"username": ep.owner_username, "wallet_address": self.world.mpp_address(slug)},
                                       transaction={"rail": "mpp", "id": "0x" + hashlib.sha256(x_payment.encode()).hexdigest()[:16],
                                                    "reference": None}))
        elif p.prepaid:
            bal = self.world.balance(p.wallet_id, email)
            need = _amount()
            if bal + 1e-9 < need:
                return self._reject(403, "policy_violation",
                                    f"Policy '{p.rail.value}_per_{p.unit.value}' blocked request: insufficient balance",
                                    [self._entry(f"{p.rail.value}_per_{p.unit.value}", "rejected", amount=need,
                                                 currency=p.currency, reason_code="INSUFFICIENT_BALANCE",
                                                 reason="Insufficient balance. Please purchase more credits.")])
            self.world.debit(p.wallet_id, email, need)
            entries.append(self._entry(f"{p.rail.value}_per_{p.unit.value}", "charged", amount=need, currency=p.currency,
                                       recipient={"username": ep.owner_username},
                                       transaction={"rail": p.rail.value, "id": f"ledger-{random.randint(10**5, 10**6)}"}))
        cost = sum(e["amount"] or 0 for e in entries)

        # RAG --------------------------------------------------------------------
        out: dict[str, Any] = {"summary": None, "references": None,
                               "cost": cost if p.paid else None, "currency": p.currency if p.paid else None,
                               "policy_metadata": {"outcome": "success", "entries": entries}}
        if ep.type.returns_references:
            out["references"] = {"documents": docs, "provider_info": {"search_engine": "chroma"}}
            if body.get("filters"):
                out["filters_applied"] = applied      # PROPOSED: echo what the Space actually filtered on
        if ep.type.returns_summary:
            out["summary"] = self.world.complete(ep.path, body.get("messages"), int(body.get("max_tokens", 100)))
        return Response(200, out)

    # -- prepaid credit routes (stripe/xendit on the Space, cluster on a station) --
    async def balance(self, wallet_id: str, *, token: str) -> Response:
        email = self.world.email_for(token)
        if email is None:
            return Response(401, {"detail": "Invalid or expired satellite token"})
        return Response(200, {"wallet_id": wallet_id, "user_email": email,
                              "balance": self.world.balance(wallet_id, email),
                              "currency": self.world.wallet_currency(wallet_id)})

    async def create_invoice(self, wallet_id: str, *, token: str, bundle_name: str) -> Response:
        email = self.world.email_for(token)
        if email is None:
            return Response(401, {"detail": "Invalid or expired satellite token"})
        bundle = self.world.bundle(wallet_id, bundle_name)
        if bundle is None:
            return Response(400, {"detail": f"Bundle '{bundle_name}' not found"})
        return Response(201, self.world.new_invoice(wallet_id, email, bundle))


class FakeHub:
    """A fake SyftHub: identity, paged discovery, satellite-token minting, MPP wallet pay."""

    TOKEN_TTL = 3600.0

    def __init__(self, world: World) -> None:
        self.world = world
        self.user: dict[str, Any] | None = None

    async def login(self, method: str, **kw: Any) -> dict[str, Any]:
        if method == "password" and (kw.get("username") != D.USER["username"] or kw.get("password") != "secret"):
            raise PermissionError("Invalid username or password")
        if method == "token" and kw.get("token") != D.USER["pat"]:
            raise PermissionError("Unknown personal access token")
        self.user = dict(D.USER, auth=method)
        return self.user

    async def logout(self) -> None:
        self.user = None

    def _all(self, type_: str | None, owner: str | None) -> list:
        eps = [e for e in self.world.endpoints.values()
               if type_ in (None, e.type.value) and owner in (None, e.owner_username)]
        return sorted(eps, key=lambda e: -e.stars_count)

    async def list(self, type_: str | None, owner: str | None, offset: int, limit: int) -> tuple[list, int]:
        eps = self._all(type_, owner)
        return eps[offset: offset + limit], len(eps)

    async def search(self, text: str, type_: str | None) -> list:
        q = text.lower().split()
        eps = self._all(type_, None)
        scored = [(sum(w in (e.name + " " + e.description + " " + e.slug + " " + " ".join(e.tags)).lower() for w in q), e) for e in eps]
        hits = [e for s, e in sorted(scored, key=lambda t: -t[0]) if s]
        return hits or eps[:4]

    async def get(self, path: str):
        return self.world.endpoints.get(path)

    async def collective(self, slug: str) -> list[str]:
        return D.COLLECTIVES.get(slug, [])

    async def satellite_token(self, owner: str, resource: str, *, guest: bool) -> tuple[str, float]:
        email = "guest@example.com" if guest or not self.user else self.user["email"]
        tok = "sat." + hashlib.sha1(f"{owner}|{resource}|{email}|{self.world.now}".encode()).hexdigest()[:16]
        self.world.tokens[tok] = (email, self.world.now + self.TOKEN_TTL)
        return tok, self.TOKEN_TTL

    async def wallet_pay(self, www_authenticate: str, slug: str, amount: float) -> str:
        if self.world.hub_wallet + 1e-9 < amount:
            raise ValueError(f"Hub wallet has {self.world.hub_wallet:.2f}, needs {amount:.2f}")
        self.world.hub_wallet = round(self.world.hub_wallet - amount, 6)
        cred = "Payment " + hashlib.sha256(www_authenticate.encode()).hexdigest()[:24]
        self.world.paid_credentials.add(cred)
        return cred
