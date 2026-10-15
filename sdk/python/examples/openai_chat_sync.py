"""The same chat app with the sync twin: ``syfthub.Hub``, no ``await``, the OpenAI sync client.

Run::

    export SYFTHUB_TOKEN=... OPENAI_API_KEY=...
    python examples/openai_chat_sync.py "adverse events in phase 3" erin/trials carol/papers
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import syfthub

SYSTEM = (
    "Answer from the numbered context only. Cite passages as [n]. "
    "If the context does not answer, say so."
)


def retrieve(plan: syfthub.SearchPlan) -> syfthub.Results | syfthub.TopUp:
    pre = plan.preflight()
    for action in pre.actions:
        match action:
            case syfthub.TopUp():
                return action
            case syfthub.OverBudget() | syfthub.AccessDenied() | syfthub.CircuitOpen():
                plan = plan.skip(*action.paths)
    return plan.execute()


def answer(hub: syfthub.Hub, question: str, sources: list[str]) -> dict[str, Any]:
    outcome = retrieve(hub.search(question, sources, limit=5, similarity_threshold=0.6))
    if isinstance(outcome, syfthub.TopUp):
        invoice = outcome.top_up()
        return {"payment_required": {"url": invoice.checkout_url, "amount": str(invoice.amount)}}
    context = "\n\n".join(
        f"[{i}] ({path}) {doc.content}" for i, (path, doc) in enumerate(outcome.documents, 1)
    )
    return {
        "answer": ask_openai(question, context),
        "cost": {cur: str(m) for cur, m in outcome.cost.items()},
        "unavailable": [r.path for r in outcome.failed],
    }


def ask_openai(question: str, context: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return f"(openai not installed)\n\n{context}"
    completion = OpenAI().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return completion.choices[0].message.content or ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    with syfthub.Hub(token=os.environ["SYFTHUB_TOKEN"]) as hub:
        print(json.dumps(answer(hub, sys.argv[1], sys.argv[2:]), indent=2))
