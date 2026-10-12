"""A chat app on OpenAI with SyftHub as retrieval: the reference example from the design doc.

Run::

    export SYFTHUB_TOKEN=... OPENAI_API_KEY=...
    python examples/openai_chat.py "adverse events in phase 3" erin/trials carol/papers

The flow: pre-flight, drop sources the SDK says it cannot send, hand a top-up back to the user
(here: print the checkout URL and save the plan to a JSON file), execute, and compose the answer
from the numbered context. ``resume`` picks the saved plan up after the invoice is paid.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import syfthub

STORE = Path(".syfthub-jobs")  # the app's own store; the SDK never decides where dicts live
SYSTEM = (
    "Answer from the numbered context only. Cite passages as [n]. "
    "If the context does not answer, say so."
)


def hub() -> syfthub.AsyncHub:
    return syfthub.AsyncHub(token=os.environ["SYFTHUB_TOKEN"], budget=1.00)  # USD per process


async def retrieve(plan: syfthub.SearchPlan) -> syfthub.Results | syfthub.TopUp:
    pre = await plan.preflight()
    for action in pre.actions:
        match action:
            case syfthub.TopUp():
                return action  # needs the user; see answer() and resume()
            case syfthub.OverBudget() | syfthub.AccessDenied() | syfthub.CircuitOpen():
                plan = plan.skip(*action.paths)  # drop the source, keep going
    return await plan.execute()  # MPP charges within budget are paid on the way


async def answer(
    h: syfthub.AsyncHub, question: str, sources: list[str], job_id: str
) -> dict[str, Any]:
    plan = h.search(question, sources, limit=5, similarity_threshold=0.6)
    outcome = await retrieve(plan)
    if isinstance(outcome, syfthub.TopUp):
        invoice = await outcome.top_up()  # the suggested bundle; PENDING, nothing charged yet
        save(job_id, {"question": question, "plan": plan.to_dict(), "invoice": invoice.to_dict()})
        return {
            "payment_required": {
                "url": invoice.checkout_url,
                "amount": str(invoice.amount),
                "job_id": job_id,
            }
        }
    return await compose(question, outcome)


async def resume(h: syfthub.AsyncHub, job_id: str) -> dict[str, Any]:
    saved = load(job_id)
    invoice = syfthub.Invoice.from_dict(h, saved["invoice"])
    invoice = await invoice.refresh()  # or trust the provider webhook that called this route
    if not invoice.paid:
        return {"payment_required": {"url": invoice.checkout_url, "status": invoice.status.value}}
    plan = syfthub.SearchPlan.from_dict(h, saved["plan"])
    outcome = await retrieve(plan)  # pre-flight again: the paid wallet now passes
    if isinstance(outcome, syfthub.TopUp):
        return {"payment_required": {"url": None, "status": "still short"}}
    return await compose(saved["question"], outcome)


async def compose(question: str, results: syfthub.Results) -> dict[str, Any]:
    context = "\n\n".join(
        f"[{i}] ({path}) {doc.content}" for i, (path, doc) in enumerate(results.documents, 1)
    )
    text = await ask_openai(question, context)
    return {
        "answer": text,
        "sources": [
            {"path": path, "title": doc.title, "score": doc.score}
            for path, doc in results.documents
        ],
        "cost": {cur: str(m) for cur, m in results.cost.items()},
        "unavailable": [
            {"path": r.path, "reason": r.reason.value if r.reason else None} for r in results.failed
        ],
    }


async def ask_openai(question: str, context: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:  # keep the example runnable without the dependency
        return f"(openai not installed)\n\n{context}"
    client = AsyncOpenAI()
    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return completion.choices[0].message.content or ""


def save(job_id: str, d: dict[str, Any]) -> None:
    STORE.mkdir(exist_ok=True)
    (STORE / f"{job_id}.json").write_text(json.dumps(d))


def load(job_id: str) -> dict[str, Any]:
    return json.loads((STORE / f"{job_id}.json").read_text())  # type: ignore[no-any-return]


async def main(argv: list[str]) -> None:
    async with hub() as h:
        if argv[:1] == ["resume"]:
            print(json.dumps(await resume(h, argv[1]), indent=2))
            return
        question, sources = argv[0], argv[1:]
        print(json.dumps(await answer(h, question, sources, job_id="job-1"), indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
