"""The Aggregator client. The route is proposed, not built; both forms the design leaves open are here
so the SDK surface is settled whichever the platform chooses:

- ``from_results``: the client already fanned out; documents go to the Aggregator (option 2).
- ``from_sources``: the Aggregator fans out with the client's satellite tokens and forwards any payment
  it hits as ``Answer.pending`` plus a ``job_id`` to ``resume`` (option 1)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .errors import AggregatorError
from .models import Answer, Charge, Document, Endpoint, Money, Outcome, Reason, SourceResult, TopUp

if TYPE_CHECKING:  # pragma: no cover
    from .hub import AsyncHub
    from .results import Results


class AggregatorClient:
    def __init__(self, hub: "AsyncHub") -> None:
        self._hub = hub

    @property
    def url(self) -> str:
        return self._hub.options.aggregator_url or f"{self._hub.url}/aggregator/api/v1"

    async def _model(self, model: Endpoint | str) -> Endpoint:
        return await self._hub.endpoints.get(model) if isinstance(model, str) else model

    async def _post(self, payload: dict[str, Any]):
        try:
            resp = await self._hub._t.aggregate(self.url, payload)
        except ConnectionError as e:
            raise AggregatorError(f"Aggregator at {self.url} unreachable: {e}") from None
        if resp.status == 404:
            raise AggregatorError(f"Aggregator route not found at {self.url}: {resp.body.get('detail')}", status=404)
        if resp.status >= 400 and resp.status != 402:
            raise AggregatorError(f"Aggregator failed: HTTP {resp.status} {resp.body.get('detail')}", status=resp.status)
        return resp

    async def _parse(self, resp, model: Endpoint, request: dict[str, Any]) -> Answer:
        b = resp.body
        per_source: list[SourceResult] = []
        pending: list[TopUp | Charge] = []
        for path, r in (b.get("per_source") or {}).items():
            ep = await self._hub.endpoints.get(path)
            if r["status"] == 0:
                row = SourceResult(endpoint=ep, outcome=Outcome.FAILED, reason=Reason.UNREACHABLE, error=r["body"].get("detail"))
            else:
                row = await self._hub._row(ep, r["status"], r["body"], r.get("headers") or {}, elapsed_ms=0, attempts=1)
            per_source.append(row)
            if row.topup and not any(isinstance(p, TopUp) and p.wallet.key == row.topup.wallet.key for p in pending):
                pending.append(row.topup)
            if row.charge:
                pending.append(row.charge)
        if resp.status == 402:
            ans = Answer(text=None, model=model, per_source=tuple(per_source), pending=tuple(pending),
                         job_id=b.get("job_id"), raw=b)
        else:
            rer = tuple((d["path"], Document(document_id=d["document_id"], content=d["content"],
                                             similarity_score=d["similarity_score"], metadata=d.get("metadata") or {}))
                        for d in b.get("reranked", []))
            cost = Money.of(b["cost"], b.get("currency")) if b.get("cost") is not None else None
            if cost:
                self._hub._spend(cost)
            ans = Answer(text=b["response"], model=model, citations={int(k): v for k, v in b.get("citations", {}).items()},
                         reranked=rer, usage=b.get("usage", {}), cost=cost, per_source=tuple(per_source),
                         job_id=b.get("job_id"), raw=b)
        ans._hub, ans._request = self._hub, request
        return ans

    async def from_results(self, results: "Results", model: Endpoint | str, prompt: str) -> Answer:
        m = await self._model(model)
        docs = [{"path": p, "document_id": d.document_id, "content": d.content, "similarity_score": d.similarity_score,
                 "metadata": d.metadata} for p, d in results.documents]
        payload = {"prompt": prompt, "documents": docs, "model": m.path, "model_token": await self._hub._token_for(m),
                   "top_k": results.limit}
        return await self._parse(await self._post(payload), m, payload)

    async def from_sources(self, query: str, sources: list[Endpoint], model: Endpoint | str, *, limit: int) -> Answer:
        m = await self._model(model)
        tokens = {ep.path: await self._hub._token_for(ep) for ep in sources}
        payload = {"prompt": query, "sources": [ep.path for ep in sources], "source_tokens": tokens, "model": m.path,
                   "model_token": await self._hub._token_for(m), "top_k": limit, "limit": limit}
        return await self._parse(await self._post(payload), m, payload)

    async def resume(self, answer: Answer, *, payments: dict[str, str] | None = None) -> Answer:
        payload: dict[str, Any] = {"job_id": answer.job_id}
        if payments:
            payload["payments"] = payments          # X-Payment credentials per source, for MPP challenges it forwarded
        return await self._parse(await self._post(payload), answer.model, payload)
