"""Where does the time go? Profile the SDK against a real Hub and its Spaces.

    export SYFTHUB_TOKEN=...            # and SYFTHUB_URL for another Hub
    python examples/profile_hub.py [--repeat 3] [--sources owner/slug ...] [--http2] [--out report.md]

Every HTTP request the SDK sends is timed through httpx's event hooks and httpcore's trace events,
so each one is split into connection setup (TCP + TLS), the wait for the server's first byte, and
the body read. Every SDK operation is timed as a whole, and the part of its wall time not covered
by any in-flight request is the client's own cost: parsing, pre-flight rules, loop scheduling.
The report says, per operation and per route, whether the lag is the Hub, a Space, the network,
or this process.
"""

from __future__ import annotations

import argparse
import asyncio
import contextvars
import os
import re
import statistics
import sys
import time
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

import syfthub
from syfthub import AsyncHub, Options
from syfthub._transport.client import KEEPALIVE_SECONDS

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_HEX = re.compile(r"^[0-9a-f]{16,}$", re.I)
current_op: contextvars.ContextVar[str] = contextvars.ContextVar("current_op", default="-")


class Sample(BaseModel):
    """One HTTP request, with the phases httpcore reported."""

    op: str
    method: str
    host: str
    route: str
    status: int | None = None
    started: float
    ended: float = 0.0
    connect_ms: float = 0.0  # TCP connect; 0 when the pooled connection was reused
    tls_ms: float = 0.0
    ttfb_ms: float = 0.0  # request headers sent -> response headers received: network + server
    body_ms: float = 0.0
    error: str | None = None

    @property
    def total_ms(self) -> float:
        return (self.ended - self.started) * 1000

    @property
    def reused(self) -> bool:
        return self.connect_ms == 0.0


class Operation(BaseModel):
    """One SDK call as the caller sees it."""

    name: str
    started: float
    ended: float
    note: str = ""

    @property
    def wall_ms(self) -> float:
        return (self.ended - self.started) * 1000


class Recorder(BaseModel):
    """Collects samples through httpx hooks and attributes them to the current operation."""

    hub_host: str
    http2: bool = False
    samples: list[Sample] = Field(default_factory=list)
    operations: list[Operation] = Field(default_factory=list)
    _open: dict[int, Sample] = {}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_open", {})

    def client(self) -> httpx.AsyncClient:
        t = Options().timeout  # the SDK's own defaults, so the profile measures what users get
        return httpx.AsyncClient(
            timeout=httpx.Timeout(t.total, connect=t.connect, read=t.read),
            limits=httpx.Limits(keepalive_expiry=KEEPALIVE_SECONDS),
            http2=self.http2,
            event_hooks={"request": [self.on_request], "response": [self.on_response]},
        )

    async def on_request(self, request: httpx.Request) -> None:
        sample = Sample(
            op=current_op.get(),
            method=request.method,
            host=request.url.host or "?",
            route=self.route_of(request.url),
            started=time.perf_counter(),
        )
        self._open[id(request)] = sample
        marks: dict[str, float] = {}

        async def trace(name: str, _info: dict[str, Any]) -> None:
            now = time.perf_counter()
            if name.endswith("connect_tcp.started"):
                marks["tcp"] = now
            elif name.endswith("connect_tcp.complete"):
                sample.connect_ms = (now - marks.pop("tcp", now)) * 1000
            elif name.endswith("start_tls.started"):
                marks["tls"] = now
            elif name.endswith("start_tls.complete"):
                sample.tls_ms = (now - marks.pop("tls", now)) * 1000
            elif name.endswith("send_request_headers.started"):
                marks["sent"] = now
            elif name.endswith("receive_response_headers.complete"):
                sample.ttfb_ms = (now - marks.get("sent", sample.started)) * 1000
            elif name.endswith("receive_response_body.started"):
                marks["body"] = now
            elif name.endswith("receive_response_body.complete"):
                sample.body_ms = (now - marks.pop("body", now)) * 1000

        request.extensions["trace"] = trace

    async def on_response(self, response: httpx.Response) -> None:
        sample = self._open.pop(id(response.request), None)
        if sample is None:
            return
        await response.aread()
        sample.status = response.status_code
        sample.ended = time.perf_counter()
        self.samples.append(sample)

    def fail_open(self) -> None:
        """Requests that never produced a response (timeouts, refused) still count."""
        for sample in self._open.values():
            sample.ended = time.perf_counter()
            sample.error = "no response"
            self.samples.append(sample)
        self._open.clear()

    def route_of(self, url: httpx.URL) -> str:
        path = url.path
        if url.host == self.hub_host:
            path = re.sub(
                r"^/api/v1/endpoints/public/by-owner/[^/]+$",
                "/api/v1/endpoints/public/by-owner/{owner}",
                path,
            )
            path = re.sub(
                r"^/api/v1/endpoints/public/[^/]+/[^/]+$",
                "/api/v1/endpoints/public/{owner}/{slug}",
                path,
            )
            return f"hub {path}"
        path = re.sub(r"^/api/v1/endpoints/[^/]+/query$", "/api/v1/endpoints/{slug}/query", path)
        path = _UUID.sub("{id}", path)
        path = "/".join("{id}" if _HEX.match(p) else p for p in path.split("/"))
        return f"space {url.host} {path}"

    @asynccontextmanager
    async def op(self, name: str, note: str = "") -> AsyncIterator[None]:
        token = current_op.set(name)
        started = time.perf_counter()
        try:
            yield
        finally:
            self.fail_open()
            self.operations.append(
                Operation(name=name, started=started, ended=time.perf_counter(), note=note)
            )
            current_op.reset(token)

    # ── aggregation ────────────────────────────────────────────────────────

    def for_op(self, name: str, started: float, ended: float) -> list[Sample]:
        return [s for s in self.samples if s.op == name and started <= s.started <= ended]

    @staticmethod
    def covered_ms(samples: Iterable[Sample]) -> float:
        """Wall time during which at least one request was in flight."""
        spans = sorted((s.started, s.ended) for s in samples)
        total, cur_start, cur_end = 0.0, None, None
        for start, end in spans:
            if cur_end is None or start > cur_end:
                if cur_end is not None and cur_start is not None:
                    total += cur_end - cur_start
                cur_start, cur_end = start, end
            else:
                cur_end = max(cur_end, end)
        if cur_end is not None and cur_start is not None:
            total += cur_end - cur_start
        return total * 1000


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def fmt(ms: float) -> str:
    return f"{ms:,.1f}" if ms < 10 else f"{ms:,.0f}"


def report(rec: Recorder, hub_url: str, results: list[syfthub.Results]) -> str:
    out: list[str] = [
        f"# SDK latency profile\n\nHub: `{hub_url}`  \nRequests: {len(rec.samples)}  \n"
    ]

    # 1. operations: where the wall time went
    out.append("## Per operation: wall time split\n")
    out.append(
        "Client = wall time with no request in flight: parsing, pre-flight rules, scheduling, and "
        "the backoff sleeps between retries.\n"
    )
    out.append(
        "| operation | wall ms | requests | hub ms | space ms | in flight ms | client ms | client % |"
    )
    out.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    totals = {"wall": 0.0, "hub": 0.0, "space": 0.0, "client": 0.0}
    for op in rec.operations:
        samples = rec.for_op(op.name, op.started, op.ended)
        hub_ms = sum(s.total_ms for s in samples if s.host == rec.hub_host)
        space_ms = sum(s.total_ms for s in samples if s.host != rec.hub_host)
        covered = rec.covered_ms(samples)
        client = max(op.wall_ms - covered, 0.0)
        totals["wall"] += op.wall_ms
        totals["hub"] += hub_ms
        totals["space"] += space_ms
        totals["client"] += client
        share = client / op.wall_ms * 100 if op.wall_ms else 0.0
        name = f"{op.name} {op.note}".strip()
        out.append(
            f"| {name} | {fmt(op.wall_ms)} | {len(samples)} | {fmt(hub_ms)} | {fmt(space_ms)} | "
            f"{fmt(covered)} | {fmt(client)} | {share:.0f}% |"
        )
    out.append(
        f"| **total** | **{fmt(totals['wall'])}** | {len(rec.samples)} | {fmt(totals['hub'])} | "
        f"{fmt(totals['space'])} | | **{fmt(totals['client'])}** | "
        f"**{totals['client'] / totals['wall'] * 100 if totals['wall'] else 0:.0f}%** |\n"
    )
    out.append(
        "`hub ms` and `space ms` are summed across requests, so parallel requests count more than "
        "once; `in flight ms` is the union, which is what the caller waited for.\n"
    )

    # 2. routes: server vs network
    out.append("## Per route: what each request cost\n")
    out.append(
        "`ttfb` is from the request headers leaving to the response headers arriving: one network "
        "round trip plus the server's own time. `connect`+`tls` is paid only on a new connection; "
        "`reused` says how many requests rode an existing one.\n"
    )
    out.append(
        "| route | n | status | ttfb p50 | ttfb p95 | ttfb max | body p50 | connect avg | tls avg | reused |"
    )
    out.append("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    by_route: dict[str, list[Sample]] = {}
    for s in rec.samples:
        by_route.setdefault(s.route, []).append(s)
    for route, samples in sorted(
        by_route.items(), key=lambda kv: -pct([s.ttfb_ms for s in kv[1]], 0.5)
    ):
        ttfb = [s.ttfb_ms for s in samples]
        body = [s.body_ms for s in samples]
        fresh = [s for s in samples if not s.reused]
        statuses = sorted({str(s.status) if s.status else (s.error or "?") for s in samples})
        out.append(
            f"| `{route}` | {len(samples)} | {','.join(statuses)} | {fmt(pct(ttfb, 0.5))} | "
            f"{fmt(pct(ttfb, 0.95))} | {fmt(max(ttfb))} | {fmt(pct(body, 0.5))} | "
            f"{fmt(statistics.mean(s.connect_ms for s in fresh) if fresh else 0)} | "
            f"{fmt(statistics.mean(s.tls_ms for s in fresh) if fresh else 0)} | "
            f"{len(samples) - len(fresh)}/{len(samples)} |"
        )
    out.append("")

    # 3. sources: the query itself
    out.append("## Per source: the query as the SDK saw it\n")
    out.append("| source | runs | outcome | elapsed p50 | elapsed max | documents | cost |")
    out.append("|---|---:|---|---:|---:|---:|---|")
    rows: dict[str, list[syfthub.SourceResult]] = {}
    for res in results:
        for r in res:
            rows.setdefault(r.path, []).append(r)
    for path, rs in sorted(rows.items(), key=lambda kv: -pct([r.elapsed_ms for r in kv[1]], 0.5)):
        elapsed = [float(r.elapsed_ms) for r in rs]
        outcomes = sorted(
            {r.outcome.value + (f":{r.reason.value}" if r.reason else "") for r in rs}
        )
        docs = statistics.mean(len(r.documents) for r in rs)
        costs = sorted({str(r.cost) for r in rs if r.cost})
        out.append(
            f"| `{path}` | {len(rs)} | {','.join(outcomes)} | {fmt(pct(elapsed, 0.5))} | "
            f"{fmt(max(elapsed))} | {docs:.0f} | {', '.join(costs) or '-'} |"
        )
    out.append("")

    # 4. verdict
    hub_s = [s for s in rec.samples if s.host == rec.hub_host]
    space_s = [s for s in rec.samples if s.host != rec.hub_host]
    out.append("## Verdict\n")
    bullets = []
    if hub_s:
        bullets.append(
            f"- Hub: {len(hub_s)} requests, ttfb p50 {fmt(pct([s.ttfb_ms for s in hub_s], 0.5))} ms, "
            f"p95 {fmt(pct([s.ttfb_ms for s in hub_s], 0.95))} ms."
        )
    if space_s:
        slow = max(space_s, key=lambda s: s.ttfb_ms)
        bullets.append(
            f"- Spaces: {len(space_s)} requests, ttfb p50 {fmt(pct([s.ttfb_ms for s in space_s], 0.5))} ms, "
            f"p95 {fmt(pct([s.ttfb_ms for s in space_s], 0.95))} ms; slowest `{slow.route}` at {fmt(slow.ttfb_ms)} ms."
        )
    fresh = [s for s in rec.samples if not s.reused]
    if fresh:
        bullets.append(
            f"- Network setup: {len(fresh)} new connections, connect+tls avg "
            f"{fmt(statistics.mean(s.connect_ms + s.tls_ms for s in fresh))} ms each."
        )
    share = totals["client"] / totals["wall"] * 100 if totals["wall"] else 0
    bullets.append(
        f"- Client: {fmt(totals['client'])} ms of {fmt(totals['wall'])} ms wall ({share:.0f}%)."
    )
    out += bullets
    return "\n".join(out) + "\n"


async def run(args: argparse.Namespace) -> str:
    url = (os.environ.get("SYFTHUB_URL") or syfthub.hub.DEFAULT_URL).rstrip("/")
    token = os.environ.get("SYFTHUB_TOKEN")
    if not token:
        sys.exit("set SYFTHUB_TOKEN")
    rec = Recorder(hub_host=urlsplit(url).hostname or url, http2=args.http2)
    results: list[syfthub.Results] = []
    async with AsyncHub(url, token=token, options=Options(http_client=rec.client())) as hub:
        async with rec.op("auth.whoami"):
            me = await hub.auth.whoami()
        async with rec.op("sources.list"):
            listing = await hub.sources.list()
        async with rec.op("sources.list(owner=)"):
            await hub.sources.list(owner=me.username)
        if listing:
            async with rec.op("sources.get"):
                await hub.sources.get(listing[0].path)
        async with rec.op("sources.search"):
            await hub.sources.search(args.query, top_k=5)
        async with rec.op("wallets.list", "parallel balance reads"):
            await hub.wallets.list()
        sources = args.sources or None
        for i in range(args.repeat):
            plan = hub.search(args.query, sources, limit=3)
            async with rec.op("plan.preflight", f"#{i + 1}"):
                pre = await plan.preflight()
            plan = plan.skip(*(row.path for row in pre.held))
            async with rec.op("plan.execute", f"#{i + 1}, {len(pre.sending)} sources"):
                results.append(await plan.execute())
    return report(rec, url, results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--query", default="What are the main findings?")
    parser.add_argument(
        "--sources", nargs="*", help="owner/slug paths; default lets the Hub pick free ones"
    )
    parser.add_argument("--repeat", type=int, default=3, help="pre-flight + execute rounds")
    parser.add_argument("--out", help="write the Markdown report here as well as to stdout")
    parser.add_argument(
        "--http2", action="store_true", help="as Options(http2=True); needs syfthub-sdk[http2]"
    )
    args = parser.parse_args()
    text = asyncio.run(run(args))
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)


if __name__ == "__main__":
    main()
