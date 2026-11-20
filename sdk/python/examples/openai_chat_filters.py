"""A chat app where the user narrows the search by metadata, in words or with controls.

Run::

    export SYFTHUB_TOKEN=... OPENAI_API_KEY=...
    python examples/openai_chat_filters.py nasa/news "Artemis launches since October, tagged moon"

The source's published filter schema is the single source of truth three times over: it
generates the OpenAI tool the model fills in, it validates what the model extracted, and it is
what the Space enforces. Nothing here hard-codes a field name. A refused filter is fed back to
the model once as the tool result, so it repairs its own mistake before the user sees anything.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from typing import Any

import syfthub
from syfthub import F

JSON_TYPE: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "datetime": {"type": "string", "description": "ISO 8601"},
    "string[]": {"type": "string"},
    "number[]": {"type": "number"},
}
EXTRACT = (
    "Today is {today}. Turn the user's request into a search: the query text and the metadata "
    "conditions it implies. Use only the fields and operators the tool offers. A list operator "
    "takes a list value."
)
ANSWER = "Answer from the numbered context only. Cite passages as [n]."


def search_tool(spec: syfthub.FilterSchema) -> dict[str, Any]:
    """The published schema as an OpenAI tool: one condition shape per filterable field, so a
    field or operator the Space does not offer fails at the tool schema, not at the Space."""
    conditions = [
        {
            "type": "object",
            "properties": {
                "field": {"const": name},
                "op": {"type": "string", "enum": list(field.ops)},
                "value": {
                    "anyOf": [
                        JSON_TYPE[field.type],
                        {"type": "array", "items": JSON_TYPE[field.type]},
                    ]
                },
            },
            "required": ["field", "op", "value"],
            "additionalProperties": False,
        }
        for name, field in spec.fields.items()
    ]
    return {
        "type": "function",
        "function": {
            "name": "search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "logic": {"type": "string", "enum": list(spec.logic)},
                    "conditions": {"type": "array", "items": {"anyOf": conditions}},
                },
                "required": ["query", "logic", "conditions"],
                "additionalProperties": False,
            },
        },
    }


def to_filter(spec: syfthub.FilterSchema, args: dict[str, Any]) -> syfthub.Filter | None:
    """Model output becomes a validated filter, or raises ``FilterError(field, reason)``."""
    leaves = [F(c["field"]).op(c["op"], c["value"]) for c in args["conditions"]]
    if not leaves:
        return None
    f = F.all(*leaves) if args["logic"] == "and" else F.any(*leaves)
    spec.validate(f)
    return f


async def extract(spec: syfthub.FilterSchema, request: str) -> dict[str, Any]:
    """Query, logic, conditions and the validated filter; one repair round on a refusal."""
    try:
        from openai import AsyncOpenAI
    except ImportError:  # keep the example runnable without the dependency
        return {"query": request, "logic": "and", "conditions": [], "filter": None}
    client = AsyncOpenAI()
    tool = search_tool(spec)
    messages: list[Any] = [
        {"role": "system", "content": EXTRACT.format(today=date.today())},
        {"role": "user", "content": request},
    ]
    error: syfthub.FilterError | None = None
    for _ in range(2):
        completion = await client.chat.completions.create(
            model="gpt-4o", messages=messages, tools=[tool], tool_choice="required"
        )
        message = completion.choices[0].message
        call = message.tool_calls[0]
        args = json.loads(call.function.arguments)
        try:
            return {**args, "filter": to_filter(spec, args)}
        except syfthub.FilterError as e:
            error = e
            messages += [
                message,
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": f"rejected: {e.field}: {e.reason}",
                },
            ]
    assert error is not None
    raise error


async def answer(h: syfthub.AsyncHub, path: str, request: str) -> dict[str, Any]:
    source = await h.sources.get(path)
    spec = source.filter_schema
    if spec is None:
        return {"error": f"{path} does not accept query filters"}
    extracted = await extract(spec, request)
    f = extracted["filter"]
    plan = h.search(extracted["query"], [source if f is None else source.where(f)], limit=5)
    results = await plan.execute()
    context = "\n\n".join(
        f"[{i}] ({p}) {doc.content}" for i, (p, doc) in enumerate(results.documents, 1)
    )
    return {
        "query": extracted["query"],
        "applied": None if f is None else f.to_wire(),  # what narrowed the search, for the chat UI
        "answer": await ask_openai(extracted["query"], context),
        "unavailable": [
            {"path": r.path, "reason": r.reason.value if r.reason else None, "error": r.error}
            for r in results.failed  # a filter the Space still refuses lands here, never silently
        ],
    }


async def ask_openai(question: str, context: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return f"(openai not installed)\n\n{context}"
    client = AsyncOpenAI()
    completion = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": ANSWER},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
    )
    return completion.choices[0].message.content or ""


async def main(argv: list[str]) -> None:
    async with syfthub.AsyncHub(token=os.environ["SYFTHUB_TOKEN"]) as h:
        print(json.dumps(await answer(h, argv[0], argv[1]), indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
