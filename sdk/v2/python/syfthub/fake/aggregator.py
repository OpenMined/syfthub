"""A fake Aggregator with the *new* route this design needs: take documents the
client already retrieved, rerank them across sources, build a cited prompt,
call the model, return answer + reranked context. It never fans out itself."""
from __future__ import annotations

import time
from typing import Any

from .space import World


class FakeAggregator:
    def __init__(self, world: World, url: str = "https://hub.example.com/aggregator/api/v1") -> None:
        self.world = world
        self.url = url

    def aggregate(self, *, prompt: str, documents: list[tuple[str, dict]], model_path: str,
                  model_token: str, x_payment: str | None, top_k: int) -> dict[str, Any]:
        time.sleep(0.4)
        # "central re-embedding": here, a stable cross-source rescore
        rescored = sorted(documents, key=lambda pd: -(pd[1]["similarity_score"] * (1.05 if "phase 3" in pd[1]["content"].lower() else 1.0)))
        kept = rescored[:top_k]
        context = "\n".join(f"[{i}] {d['content']}" for i, (_, d) in enumerate(kept, 1))
        ep = self.world.endpoints[model_path]
        space_url = ep.url
        from .space import FakeSpace
        resp = FakeSpace(space_url, self.world).query(
            ep.slug, token=model_token, x_payment=x_payment,
            body={"messages": [{"role": "system", "content": "Answer with citations.\n" + context},
                               {"role": "user", "content": prompt}], "max_tokens": 300})
        if resp.status != 200:
            return {"status": resp.status, "body": resp.body, "headers": resp.headers}
        return {"status": 200, "body": {
            "response": resp.body["summary"]["message"]["content"],
            "usage": resp.body["summary"]["usage"],
            "reranked": [{"path": p, **d} for p, d in kept],
            "citations": {i: p for i, (p, _) in enumerate(kept, 1)},
            "policy_metadata": resp.body["policy_metadata"],
            "cost": resp.body["cost"], "currency": resp.body["currency"],
        }}
