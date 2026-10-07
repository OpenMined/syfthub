"""A fake Aggregator for the route this design needs. It does not exist on the platform yet; the
shapes here are the proposal, in both forms the low-level design leaves open:

- option 2: ``documents`` supplied, the Aggregator reranks, prompts the model and answers;
- option 1: ``sources`` supplied, the Aggregator fans out itself with the client's satellite tokens,
  returns the per-Space payment envelopes plus a ``job_id`` when any Space wants paying, and finishes
  the job on ``resume``."""
from __future__ import annotations

import uuid
from typing import Any

from .._transport import Response
from .space import FakeSpace, World


class FakeAggregator:
    def __init__(self, world: World) -> None:
        self.world = world

    async def _answer(self, *, prompt: str, documents: list[dict], model_path: str, model_token: str, top_k: int) -> Response:
        rescored = sorted(documents, key=lambda d: -(d["similarity_score"] * (1.05 if "phase 3" in d["content"].lower() else 1.0)))
        kept = rescored[:top_k]
        context = "\n".join(f"[{i}] {d['content']}" for i, d in enumerate(kept, 1))
        ep = self.world.endpoints[model_path]
        resp = await FakeSpace(ep.url, self.world).query(
            ep.slug, token=model_token,
            body={"messages": [{"role": "system", "content": "Answer with citations.\n" + context},
                               {"role": "user", "content": prompt}], "max_tokens": 300})
        if resp.status != 200:
            return Response(resp.status, resp.body, resp.headers)
        return Response(200, {
            "response": resp.body["summary"]["message"]["content"],
            "usage": resp.body["summary"]["usage"],
            "reranked": [dict(d) for d in kept],
            "citations": {str(i): d["path"] for i, d in enumerate(kept, 1)},
            "policy_metadata": resp.body["policy_metadata"],
            "cost": resp.body["cost"], "currency": resp.body["currency"],
        })

    async def handle(self, payload: dict[str, Any]) -> Response:
        await self.world._latency()
        if payload.get("job_id"):
            return await self._resume(payload["job_id"], payload.get("payments") or {})
        if "documents" in payload:                       # option 2
            return await self._answer(prompt=payload["prompt"], documents=payload["documents"],
                                      model_path=payload["model"], model_token=payload["model_token"],
                                      top_k=payload.get("top_k", 5))
        # option 1: fan out here ---------------------------------------------------------------
        job = {"id": f"job-{uuid.uuid4().hex[:8]}", "prompt": payload["prompt"], "model": payload["model"],
               "model_token": payload["model_token"], "top_k": payload.get("top_k", 5), "limit": payload.get("limit", 5),
               "per_source": {}, "tokens": payload["source_tokens"]}
        self.world.jobs[job["id"]] = job
        return await self._run(job, payload["sources"])

    async def _run(self, job: dict[str, Any], sources: list[str], payments: dict[str, str] | None = None) -> Response:
        for path in sources:
            ep = self.world.endpoints[path]
            body = {"messages": [{"role": "user", "content": job["prompt"]}], "limit": job["limit"], "similarity_threshold": 0.5}
            try:
                r = await FakeSpace(ep.url, self.world).query(ep.slug, token=job["tokens"][path], body=body,
                                                              x_payment=(payments or {}).get(path))
                job["per_source"][path] = {"status": r.status, "body": r.body, "headers": r.headers}
            except ConnectionError as e:
                job["per_source"][path] = {"status": 0, "body": {"detail": str(e)}, "headers": {}}
        pending = [p for p, r in job["per_source"].items() if r["status"] in (402, 403)
                   and any(e.get("reason_code") in ("INSUFFICIENT_BALANCE", "PAYMENT_REQUIRED")
                           for e in (r["body"].get("policy_metadata") or {}).get("entries", []))]
        if pending:
            return Response(402, {"job_id": job["id"], "pending": pending, "per_source": job["per_source"],
                                  "detail": "Some sources need payment; pay, then resume the job"})
        docs = [dict(d, path=p) for p, r in job["per_source"].items() if r["status"] == 200
                for d in ((r["body"].get("references") or {}).get("documents") or [])]
        out = await self._answer(prompt=job["prompt"], documents=docs, model_path=job["model"],
                                 model_token=job["model_token"], top_k=job["top_k"])
        out.body["per_source"] = job["per_source"]
        out.body["job_id"] = job["id"]
        return out

    async def _resume(self, job_id: str, payments: dict[str, str]) -> Response:
        job = self.world.jobs.get(job_id)
        if job is None:
            return Response(404, {"detail": f"job {job_id} not found"})
        retry = [p for p, r in job["per_source"].items() if r["status"] != 200]
        return await self._run(job, retry, payments)
