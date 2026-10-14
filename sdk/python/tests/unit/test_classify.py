"""One Space response -> one ``SourceResult``; pure."""

from __future__ import annotations

from typing import Any

import httpx

from syfthub import Money, Outcome, Rail, Reason, SearchPlan, Source, Wallet
from syfthub.classify import classify, mpp_charge, parse_challenge, query_body


def response(
    status: int, json: Any = None, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status, json=json, headers=headers, request=httpx.Request("POST", "http://x")
    )


def entry(**fields: Any) -> dict[str, Any]:
    base = {
        "policy_type": "stripe_per_request",
        "kind": "payment",
        "status": "charged",
        "amount": 0.05,
        "currency": "USD",
        "recipient": {"username": "erin", "email": "e@e", "wallet_address": None},
        "transaction": {"rail": "stripe", "id": "tx-1", "reference": None},
        "reason_code": None,
        "reason": None,
        "details": {},
    }
    base.update(fields)
    return base


def test_query_body_has_exactly_the_four_documented_fields() -> None:
    plan = SearchPlan(query="hello", limit=3, similarity_threshold=0.7, include_metadata=False)
    assert query_body(plan) == {
        "messages": "hello",
        "similarity_threshold": 0.7,
        "limit": 3,
        "include_metadata": False,
    }


def test_success_with_documents_summary_cost_and_charges(
    paid_source: Source, wallet: Wallet
) -> None:
    body = {
        "summary": {"message": {"role": "assistant", "content": "Sixteen weeks."}},
        "references": {
            "documents": [
                {
                    "document_id": "d1",
                    "content": "16 weeks",
                    "metadata": {"title": "HB"},
                    "similarity_score": 0.83,
                },
                {"document_id": "d2", "content": "x", "metadata": None, "similarity_score": 0.6},
            ]
        },
        "cost": 0.05,
        "currency": "USD",
        "policy_metadata": {"outcome": "success", "entries": [entry()]},
    }
    row = classify(
        paid_source,
        response(200, body),
        wallet=wallet,
        request={"url": "u"},
        attempts=1,
        elapsed_ms=12,
    )
    assert row.ok and row.outcome is Outcome.RETURNED and row.status_code == 200
    assert [d.id for d in row.documents] == ["d1", "d2", "summary"]
    assert row.chunks[0].title == "HB" and row.chunks[1].metadata == {}
    assert row.summaries[0].content == "Sixteen weeks." and row.summary == "Sixteen weeks."
    assert row.cost == Money.of("0.05") and row.paid_from == wallet.key and row.rail is Rail.STRIPE
    assert row.charges[0].charged and row.charges[0].transaction_id == "tx-1"
    assert row.raw == body and row.request == {"url": "u"} and row.elapsed_ms == 12


def test_success_without_cost_and_plain_string_summary(free_source: Source) -> None:
    row = classify(
        free_source, response(200, {"summary": "plain", "references": {"documents": []}})
    )
    assert row.ok and row.cost is None and row.paid_from is None and row.rail is None
    assert row.summary == "plain" and len(row.documents) == 1 and row.documents[0].is_summary


def test_prepaid_402_is_rejected_no_credits_with_a_topup(
    paid_source: Source, wallet: Wallet
) -> None:
    body = {
        "detail": "Insufficient balance: 0.02 USD available, 0.05 USD required",
        "policy_metadata": {
            "outcome": "payment_required",
            "entries": [
                entry(
                    status="rejected",
                    reason_code="INSUFFICIENT_BALANCE",
                    details={"wallet_id": "w-erin", "balance": 0.02},
                )
            ],
        },
    }
    row = classify(paid_source, response(402, body), wallet=wallet, estimate=Money.of("0.05"))
    assert row.outcome is Outcome.REJECTED and row.reason is Reason.NO_CREDITS and row.retryable
    assert row.topup is not None and row.topup.shortfall == Money.of("0.03")
    assert row.topup.suggested is not None and row.topup.suggested.id == "starter"
    assert row.topup.wallet is wallet and row.error.startswith("Insufficient balance")  # type: ignore[union-attr]
    no_wallet = classify(paid_source, response(402, body), estimate=Money.of("0.05"))
    assert no_wallet.topup is None and no_wallet.reason is Reason.NO_CREDITS


def test_403_variants(free_source: Source) -> None:
    def forbidden(outcome: str, **extra: Any) -> httpx.Response:
        return response(
            403,
            {
                "detail": f"{outcome}!",
                "policy_metadata": {
                    "outcome": outcome,
                    "entries": [entry(kind=outcome, status="rejected", **extra)],
                },
            },
            headers={"Retry-After": "7"},
        )

    limited = classify(
        free_source,
        forbidden(
            "rate_limited",
            reason_code="RATE_LIMITED",
            details={"retry_after_seconds": 41, "remaining": 0, "limit": "20/m"},
        ),
    )
    assert limited.reason is Reason.RATE_LIMITED and limited.retryable
    assert limited.rate_limit is not None and limited.rate_limit.reset_seconds == 41
    assert limited.rate_limit.limit == "20/m" and limited.rate_limit.remaining == 0
    assert classify(free_source, forbidden("access_denied")).reason is Reason.ACCESS_DENIED
    assert classify(free_source, forbidden("policy_violation")).reason is Reason.BLOCKED
    assert classify(free_source, forbidden("not_published")).reason is Reason.NOT_PUBLISHED
    tier = classify(free_source, forbidden("payment_required", reason_code="NO_PRICING_TIER"))
    assert tier.reason is Reason.NO_PRICING_TIER and not tier.retryable
    plain = classify(free_source, response(403, {"detail": "Endpoint not published"}))
    assert plain.reason is Reason.NOT_PUBLISHED
    assert classify(free_source, response(403, {"detail": "no"})).reason is Reason.BLOCKED


def test_failures(free_source: Source) -> None:
    assert classify(free_source, response(404, {"detail": "nope"})).reason is Reason.NOT_FOUND
    assert classify(free_source, response(401, {"detail": "bad"})).reason is Reason.AUTH
    boom = classify(free_source, response(503, "down"))
    assert boom.outcome is Outcome.FAILED and boom.reason is Reason.SERVER_ERROR and boom.retryable
    odd = classify(free_source, response(422, {"detail": [{"msg": "x"}]}))
    assert odd.outcome is Outcome.FAILED and odd.reason is None and not odd.retryable
    assert odd.error.startswith("[{") and odd.raw == {"detail": [{"msg": "x"}]}  # type: ignore[union-attr]


def test_mpp_challenge_parsing_and_payment_required(free_source: Source) -> None:
    header = 'Payment id="abc", realm="kim", amount="0.02", currency=USD, request="eyJ..."'
    assert parse_challenge(header) == {
        "id": "abc",
        "realm": "kim",
        "amount": "0.02",
        "currency": "USD",
        "request": "eyJ...",
    }
    challenge = response(402, {"detail": "pay"}, headers={"WWW-Authenticate": header})
    charge = mpp_charge(free_source, challenge, fallback=Money.of("0.01"))
    assert charge.amount == Money.of("0.02") and charge.www_authenticate == header
    bare = response(402, None, headers={"WWW-Authenticate": "Payment realm=kim"})
    assert mpp_charge(free_source, bare, fallback=Money.of("0.01")).amount == Money.of("0.01")
    still = classify(free_source, response(402, {"detail": "invalid credential"}), charge=charge)
    assert still.outcome is Outcome.PAYMENT_REQUIRED and still.charge is charge
    assert still.error == "invalid credential" and not still.retryable
    paid = classify(free_source, response(200, {"references": {"documents": []}}), charge=charge)
    assert paid.ok and paid.cost == Money.of("0.02") and paid.charge is charge


def test_a_bare_429_is_a_retryable_rate_limit(free_source: Source) -> None:
    """A Space's own throttle answers 429 with a plain detail and no policy entry."""
    throttled = classify(
        free_source,
        response(429, {"detail": "Too many requests. Please slow down."}, {"Retry-After": "9"}),
    )
    assert throttled.outcome is Outcome.REJECTED and throttled.reason is Reason.RATE_LIMITED
    assert throttled.retryable and throttled.rate_limit is not None
    assert throttled.rate_limit.reset_seconds == 9 and "slow down" in (throttled.error or "")
