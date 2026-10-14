from __future__ import annotations

from typing import Any

import pytest

from syfthub import (
    Document,
    Money,
    Outcome,
    Reason,
    Results,
    ReturnKind,
    SearchPlan,
    Source,
    SourceResult,
    StaleSnapshot,
    TopUp,
)
from syfthub.models import ChargeEntry, RateLimit


def doc(path: str, content: str, score: float | None, id: str = "") -> Document:
    return Document(id=id or content, content=content, score=score, source=path)


@pytest.fixture
def results(free_source: Source, paid_source: Source, model_source: Source) -> Results:
    plan = SearchPlan(query="q", sources=(free_source.path, paid_source.path, model_source.path))
    rows = (
        SourceResult(
            source=free_source,
            outcome=Outcome.RETURNED,
            status_code=200,
            documents=(doc("alice/free-docs", "low", 0.4), doc("alice/free-docs", "high", 0.9)),
        ),
        SourceResult(
            source=paid_source,
            outcome=Outcome.RETURNED,
            status_code=200,
            documents=(doc("erin/trials", "mid", 0.7),),
            cost=Money.of("0.05"),
            paid_from="erin/xendit/USD",
        ),
        SourceResult(
            source=model_source,
            outcome=Outcome.RETURNED,
            status_code=200,
            documents=(doc("kim/assistant", "an answer", None),),
            summary="an answer",
            cost=Money.of("0.01"),
        ),
    )
    return Results(rows=rows, plan=plan)


def test_document_aliases_keep_wire_names() -> None:
    d = Document.from_dict(
        {"document_id": "d1", "content": "c", "similarity_score": 0.5, "metadata": {"title": "T"}}
    )
    assert d.id == "d1" and d.score == 0.5 and d.title == "T" and not d.is_summary
    assert d.to_dict()["document_id"] == "d1" and d.to_dict()["similarity_score"] == 0.5


def test_documents_order_chunks_then_summaries(results: Results) -> None:
    order = [(p, d.content) for p, d in results.documents]
    assert order == [
        ("alice/free-docs", "high"),
        ("erin/trials", "mid"),
        ("alice/free-docs", "low"),
        ("kim/assistant", "an answer"),
    ]
    assert [d.content for _, d in results.chunks] == ["high", "mid", "low"]
    assert results.answers == {"kim/assistant": "an answer"}
    assert results.kind is ReturnKind.BOTH


def test_top_trims_chunks_only(results: Results) -> None:
    top = results.top(1)
    assert [(p, d.content) for p, d in top.documents] == [
        ("alice/free-docs", "high"),
        ("kim/assistant", "an answer"),
    ]
    assert results.top(0).kind is ReturnKind.SUMMARIES
    assert len(results.documents) == 4  # original untouched


def test_views_and_lookup(results: Results) -> None:
    assert results.only("erin/trials").paths == ("erin/trials",)
    assert results.drop("erin/trials").paths == ("alice/free-docs", "kim/assistant")
    assert results["kim/assistant"].summary == "an answer" and "kim/assistant" in results
    with pytest.raises(KeyError):
        results["nobody/x"]
    assert results.cost == {"USD": Money.of("0.06")}
    assert set(results.raw) == set(results.paths)


def test_add_replaces_rows_by_path(results: Results, paid_source: Source) -> None:
    fresh = Results(
        rows=(SourceResult(source=paid_source, outcome=Outcome.FAILED, reason=Reason.TIMEOUT),),
        plan=results.plan,
    )
    merged = results + fresh
    assert merged["erin/trials"].outcome is Outcome.FAILED and len(merged) == 3
    assert merged.kind is ReturnKind.BOTH and merged.cost == {"USD": Money.of("0.01")}


def test_outcome_buckets_and_retryable(
    free_source: Source, paid_source: Source, model_source: Source
) -> None:
    def row(src: Source, outcome: Outcome, reason: Reason | None = None) -> SourceResult:
        return SourceResult(source=src, outcome=outcome, reason=reason)

    plan = SearchPlan(query="q")
    r = Results(
        rows=(
            row(free_source, Outcome.REJECTED, Reason.RATE_LIMITED),
            row(paid_source, Outcome.HELD, Reason.NO_CREDITS),
            row(model_source, Outcome.FAILED, Reason.NOT_FOUND),
        ),
        plan=plan,
    )
    assert [x.path for x in r.failed] == ["alice/free-docs", "kim/assistant"]
    assert [x.path for x in r.held] == ["erin/trials"]
    assert [x.path for x in r.retryable] == ["alice/free-docs"]
    assert r.ok == () and r.kind is ReturnKind.NOTHING and r.cost == {}


def test_results_snapshot_roundtrip_binds_nested(results: Results, paid_source: Source) -> None:
    from syfthub import Rail, Wallet

    wallet = Wallet(id="w", key="erin/xendit/USD", owner="erin", rail=Rail.XENDIT, currency="USD")
    topup = TopUp(wallet=wallet, shortfall=Money.of(1), affects=(paid_source,))
    held = results + Results(
        rows=(
            SourceResult(
                source=paid_source, outcome=Outcome.HELD, reason=Reason.NO_CREDITS, topup=topup
            ),
        ),
        plan=results.plan,
        actions=(topup,),
    )
    d = held.to_dict()
    assert "_hub" not in d and d["plan"]["version"]
    hub = object()
    back = Results.from_dict(hub, d)
    assert back.plan._hub is hub
    assert isinstance(back.actions[0], TopUp) and back.actions[0].wallet._hub is hub
    assert back["erin/trials"].topup is not None and back["erin/trials"].topup.wallet._hub is hub
    assert back.rows == held.rows
    with pytest.raises(StaleSnapshot):
        Results.from_dict(hub, {**d, "plan": {**d["plan"], "version": "9.0.0"}})


def test_charge_entry_from_space_body() -> None:
    body: dict[str, Any] = {
        "policy_type": "xendit",
        "kind": "payment",
        "status": "charged",
        "amount": 0.05,
        "currency": "USD",
        "transaction": {"rail": "xendit", "id": "tx-1"},
        "recipient": {"wallet_address": "0xabc"},
        "details": {"documents": 3},
    }
    e = ChargeEntry.from_space("erin/trials", body)
    assert e.charged and e.amount == Money.of("0.05") and e.transaction_id == "tx-1"
    assert e.rail is not None and e.rail.value == "xendit" and e.wallet == "0xabc" and e.raw == body
    rejected = ChargeEntry.from_space(
        "erin/trials", {"status": "rejected", "reason_code": "INSUFFICIENT_BALANCE"}
    )
    assert not rejected.charged and rejected.reason_code == "INSUFFICIENT_BALANCE"
    assert RateLimit(reset_seconds=30).to_dict()["reset_seconds"] == 30
