"""Turn one Space response into one ``SourceResult``. Pure: no network, no clock.

The Space's status code and ``policy_metadata`` are authoritative; this module only names what
they say in the SDK's enums and keeps the body verbatim in ``raw``.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .models.enums import Outcome, Rail, Reason
from .models.money import Money
from .models.results import Document, SourceResult
from .models.search import SearchPlan, TopUp
from .models.sources import Source
from .models.wallets import Charge, ChargeEntry, RateLimit, Wallet

_FORBIDDEN: dict[str, Reason] = {
    "rate_limited": Reason.RATE_LIMITED,
    "access_denied": Reason.ACCESS_DENIED,
    "not_published": Reason.NOT_PUBLISHED,
    "policy_violation": Reason.BLOCKED,
}
_REASON_CODES: dict[str, Reason] = {
    "RATE_LIMITED": Reason.RATE_LIMITED,
    "ACCESS_DENIED": Reason.ACCESS_DENIED,
    "NO_PRICING_TIER": Reason.NO_PRICING_TIER,
    "INSUFFICIENT_BALANCE": Reason.NO_CREDITS,
    "PAYMENT_REQUIRED": Reason.NO_CREDITS,
}
_CHALLENGE_PARAM = re.compile(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(?:"([^"]*)"|([^,\s]+))')


def query_body(plan: SearchPlan) -> dict[str, Any]:
    """The request body: the four fields the Space documents, nothing else."""
    return {
        "messages": plan.query,
        "similarity_threshold": plan.similarity_threshold,
        "limit": plan.limit,
        "include_metadata": plan.include_metadata,
    }


def body_of(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def detail_of(response: httpx.Response) -> str:
    """The ``detail`` of a FastAPI error body, else a short slice of the text."""
    detail = body_of(response).get("detail")
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return str(detail)[:200]
    return response.text[:200]


def entries_of(source: Source, body: dict[str, Any]) -> tuple[ChargeEntry, ...]:
    meta = body.get("policy_metadata")
    raw = meta.get("entries") if isinstance(meta, dict) else None
    if not isinstance(raw, list):
        return ()
    return tuple(ChargeEntry.from_space(source.path, e) for e in raw if isinstance(e, dict))


def outcome_of(body: dict[str, Any]) -> str | None:
    meta = body.get("policy_metadata")
    value = meta.get("outcome") if isinstance(meta, dict) else None
    return value if isinstance(value, str) else None


def parse_challenge(header: str) -> dict[str, str]:
    """``key=value`` pairs of a ``WWW-Authenticate`` challenge, scheme dropped, keys lowered."""
    _, _, params = header.strip().partition(" ")
    return {m.group(1).lower(): m.group(2) or m.group(3) for m in _CHALLENGE_PARAM.finditer(params)}


def mpp_charge(source: Source, response: httpx.Response, fallback: Money) -> Charge:
    """The ``Charge`` a 402 challenge asks for. The amount comes from the challenge when it names
    one, else from the published price."""
    header = response.headers.get("www-authenticate", "")
    params = parse_challenge(header)
    amount = fallback
    raw_amount = params.get("amount") or params.get("price")
    if raw_amount is not None:
        try:
            amount = Money.of(raw_amount, params.get("currency") or fallback.currency)
        except ValueError:
            amount = fallback
    return Charge(source=source.path, amount=amount, www_authenticate=header, raw=body_of(response))


def _summary_text(body: dict[str, Any]) -> str | None:
    summary = body.get("summary")
    if isinstance(summary, str):
        return summary if summary.strip() else None
    if isinstance(summary, dict):
        message = summary.get("message")
        content = message.get("content") if isinstance(message, dict) else summary.get("content")
        if isinstance(content, str) and content.strip():
            return content
    return None


def _documents(source: Source, body: dict[str, Any]) -> tuple[tuple[Document, ...], str | None]:
    refs = body.get("references")
    raw = refs.get("documents") if isinstance(refs, dict) else None
    documents = [Document.from_space(source.path, d) for d in raw or () if isinstance(d, dict)]
    summary = _summary_text(body)
    if summary:
        documents.append(Document.summary(source.path, summary))
    return tuple(documents), summary


def _cost(body: dict[str, Any], currency: str) -> Money | None:
    raw = body.get("cost")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return Money.of(raw, str(body.get("currency") or currency))
    except ValueError:
        return None


def _rejected_entry(entries: tuple[ChargeEntry, ...]) -> ChargeEntry | None:
    for entry in entries:
        if entry.status == "rejected":
            return entry
    return None


def topup_for(
    source: Source, wallet: Wallet | None, required: Money, entry: ChargeEntry | None
) -> TopUp | None:
    """The ``TopUp`` a prepaid 402 asks for: the Space's own balance figure when it gives one."""
    if wallet is None:
        return None
    balance = Money.zero(required.currency)
    if entry is not None:
        raw = entry.details.get("balance")
        if raw is not None and not isinstance(raw, bool):
            try:
                balance = Money.of(raw, required.currency)
            except ValueError:
                balance = Money.zero(required.currency)
    shortfall = required - balance if required > balance else required
    suggested = wallet.suggest(shortfall)
    return TopUp(
        wallet=wallet,
        shortfall=shortfall,
        bundles=wallet.bundles,
        suggested=suggested,
        affects=(source,),
        steps=topup_steps(wallet, suggested),
    )


def topup_steps(wallet: Wallet, suggested: Any) -> tuple[str, ...]:
    buy = (
        f"await action.top_up() buys the {suggested.id} bundle ({suggested.amount})"
        if suggested is not None
        else "await action.top_up(bundle) with a bundle from action.bundles"
    )
    return (
        f"{buy} on wallet {wallet.key}",
        "pay at invoice.checkout_url, then await invoice.wait_paid()",
        "plan.execute() again: pre-flight reads the new balance",
    )


def classify(
    source: Source,
    response: httpx.Response,
    *,
    wallet: Wallet | None = None,
    estimate: Money | None = None,
    charge: Charge | None = None,
    request: dict[str, Any] | None = None,
    attempts: int = 1,
    elapsed_ms: int = 0,
) -> SourceResult:
    """One row from the final response of a query. ``charge`` is the MPP challenge that was paid
    (or not) before this response; a 402 after paying is ``PAYMENT_REQUIRED``."""
    status = response.status_code
    body = body_of(response)
    entries = entries_of(source, body)
    estimate = estimate if estimate is not None else Money()
    pricing = source.pricing
    currency = pricing.currency if pricing else estimate.currency
    rail: Rail | None = pricing.rail if pricing and not pricing.free else None
    base: dict[str, Any] = {
        "source": source,
        "status_code": status,
        "charges": entries,
        "rail": rail,
        "attempts": attempts,
        "elapsed_ms": elapsed_ms,
        "request": request or {},
        "raw": body,
    }
    if 200 <= status < 300:
        documents, summary = _documents(source, body)
        charged = [e for e in entries if e.charged]
        if charged and charged[0].rail is not None:
            base["rail"] = charged[0].rail
        return SourceResult(
            outcome=Outcome.RETURNED,
            documents=documents,
            summary=summary,
            cost=_cost(body, currency) or (charge.amount if charge else None),
            paid_from=wallet.key if wallet is not None and charged else None,
            charge=charge,
            **base,
        )
    detail = detail_of(response)
    rejected = _rejected_entry(entries)
    if status == 402:
        if charge is not None:
            return SourceResult(
                outcome=Outcome.PAYMENT_REQUIRED,
                charge=charge,
                error=detail or "the Space did not accept the payment",
                **base,
            )
        required = estimate
        if rejected is not None and rejected.amount is not None:
            required = rejected.amount
        return SourceResult(
            outcome=Outcome.REJECTED,
            reason=Reason.NO_CREDITS,
            topup=topup_for(source, wallet, required, rejected),
            error=detail,
            **base,
        )
    if status == 403:
        outcome = outcome_of(body)
        reason = _FORBIDDEN.get(outcome or "")
        if reason is None and rejected is not None:
            reason = _REASON_CODES.get(rejected.reason_code or "")
        if reason is None and "not published" in detail.lower():
            reason = Reason.NOT_PUBLISHED
        details = rejected.details if rejected is not None else {}
        return SourceResult(
            outcome=Outcome.REJECTED,
            reason=reason or Reason.BLOCKED,
            rate_limit=(
                RateLimit.from_entry(details, dict(response.headers))
                if (reason or Reason.BLOCKED) is Reason.RATE_LIMITED
                else None
            ),
            error=detail,
            **base,
        )
    if (
        status == 429
    ):  # the Space's own throttle, outside its policy engine: no entry, no body shape
        return SourceResult(
            outcome=Outcome.REJECTED,
            reason=Reason.RATE_LIMITED,
            rate_limit=RateLimit.from_entry({}, dict(response.headers)),
            error=detail,
            **base,
        )
    failed: Reason | None
    if status == 404:
        failed = Reason.NOT_FOUND
    elif status == 401:
        failed = Reason.AUTH
    elif status >= 500:
        failed = Reason.SERVER_ERROR
    else:
        failed = None
    return SourceResult(outcome=Outcome.FAILED, reason=failed, error=detail, **base)
