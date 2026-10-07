"""HTML rendering for Jupyter (``_repr_html_``). Pure functions over the typed models; no widgets, no
IPython import. Loaded lazily by the models' display hooks, so the core never pays for it."""
from __future__ import annotations

import html
import uuid
from typing import TYPE_CHECKING, Iterable

from ..models import Health, Include, Money, Outcome, Rail, Reason, ReturnKind, TopUp, Verdict

if TYPE_CHECKING:  # pragma: no cover
    from ..models import Answer, Charge, Endpoint, Identity, Invoice, SourceResult
    from ..results import Results

CSS = """<style>
.sh{font:13px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1f2328}
.sh table{border-collapse:collapse;margin:.25em 0}
.sh th,.sh td{padding:4px 10px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}
.sh th{font-weight:600;color:#57606a;font-size:12px}
.sh .card{border:1px solid #d0d7de;border-radius:8px;padding:10px 14px;margin:6px 0;max-width:780px}
.sh .t{font-weight:600;font-size:14px;margin-bottom:4px}.sh .m{color:#57606a}
.sh .b{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:600;margin-right:4px}
.sh .ok{background:#dafbe1;color:#116329}.sh .warn{background:#fff8c5;color:#7d4e00}
.sh .bad{background:#ffebe9;color:#a40e26}.sh .info{background:#ddf4ff;color:#0550ae}.sh .mute{background:#eaeef2;color:#57606a}
.sh .doc{border-left:3px solid #d0d7de;padding:4px 10px;margin:4px 0}.sh .score{color:#57606a;font-size:11px}
.sh .ans{white-space:pre-wrap;background:#f6f8fa;border-radius:6px;padding:10px 12px;margin:6px 0}
.sh .cite{color:#0550ae;font-weight:600}.sh a{color:#0969da}.sh code{font-size:12px}
.sh .tabs{margin:6px 0}.sh .tabs>input{display:none}.sh .tabs>label{display:inline-block;padding:4px 12px;border:1px solid #d0d7de;border-bottom:none;border-radius:6px 6px 0 0;margin-right:2px;cursor:pointer;color:#57606a;font-size:12px;font-weight:600}
.sh .tabs>input:checked+label{background:#f6f8fa;color:#1f2328}.sh .tabs>.panel{display:none;border:1px solid #d0d7de;border-radius:0 6px 6px 6px;padding:8px 12px}
""" + "".join(f".sh .tabs>input:nth-of-type({i})::checked~.panel:nth-of-type({i}){{display:block}}" for i in range(1, 9)) + """
.sh .tabs>input:nth-of-type(1):checked~.panel:nth-of-type(1),.sh .tabs>input:nth-of-type(2):checked~.panel:nth-of-type(2),
.sh .tabs>input:nth-of-type(3):checked~.panel:nth-of-type(3),.sh .tabs>input:nth-of-type(4):checked~.panel:nth-of-type(4),
.sh .tabs>input:nth-of-type(5):checked~.panel:nth-of-type(5),.sh .tabs>input:nth-of-type(6):checked~.panel:nth-of-type(6){display:block}
</style>"""


def money(m: Money | None) -> str:
    return "-" if m is None else str(m)


def _e(s: object) -> str:
    return html.escape(str(s))


def badge(text: str, kind: str = "mute") -> str:
    return f'<span class="b {kind}">{_e(text)}</span>'


def tabs(panels: list[tuple[str, str]]) -> str:
    """``[(label_html, body_html), …]`` as CSS-only tabs. One panel renders without the tab strip."""
    if len(panels) == 1:
        return panels[0][1]
    g = uuid.uuid4().hex[:8]
    inputs = "".join(f'<input type="radio" name="t{g}" id="t{g}-{i}"{" checked" if i == 0 else ""}><label for="t{g}-{i}">{lab}</label>'
                     for i, (lab, _) in enumerate(panels))
    bodies = "".join(f'<div class="panel">{body}</div>' for _, body in panels)
    return f'<div class="tabs">{inputs}{bodies}</div>'


def wrap(body: str) -> str:
    return f'{CSS}<div class="sh">{body}</div>'


_REASON_KIND = {Reason.NO_CREDITS: "warn", Reason.OVER_BUDGET: "warn", Reason.RATE_LIMITED: "warn", Reason.BY_USER: "mute",
                Reason.CIRCUIT_OPEN: "warn"}
_VERDICT_KIND = {Verdict.READY: "ok", Verdict.WILL_ASK_TO_PAY: "info", Verdict.NEEDS_CREDITS: "warn", Verdict.OVER_BUDGET: "warn",
                 Verdict.ACCESS_DENIED: "bad", Verdict.UNHEALTHY: "warn", Verdict.CIRCUIT_OPEN: "warn"}


def outcome_badge(o: Outcome, reason: Reason | None = None) -> str:
    if o is Outcome.RETURNED:
        return badge("returned", "ok")
    if o is Outcome.PAYMENT_REQUIRED:
        return badge("payment required", "info")
    main = badge(o.value, {"held": "mute", "rejected": "bad", "failed": "bad"}[o.value])
    return main + (badge(reason.value.replace("_", " "), _REASON_KIND.get(reason, "bad")) if reason else "")


def verdict_badge(v: Verdict) -> str:
    return badge(v.label, _VERDICT_KIND.get(v, "mute"))


def pricing_badge(p) -> str:
    if not p.paid:
        return badge("free", "ok")
    return badge(p.label, "info" if p.rail is Rail.MPP else "warn")


def _sum(d: dict[str, Money]) -> str:
    return " + ".join(str(v) for v in d.values()) or "free"


# ---------------------------------------------------------------- endpoints --
def endpoint_table(sel: Iterable["Endpoint"]) -> str:
    rows = []
    for e in sel:
        other = [badge(p.type.value, "mute") for p in e.policies if not p.is_payment]
        health = badge("unhealthy", "warn") if e.health is Health.UNHEALTHY else ""
        rows.append(f"<tr><td><b>{_e(e.path)}</b><div class='m'>{_e(e.name)}</div></td>"
                    f"<td>{badge(e.type.value, 'mute')}</td><td>{pricing_badge(e.pricing)}</td>"
                    f"<td>{''.join(other)}{health}</td><td class='m'>{_e(e.description)}</td><td class='m'>{e.stars_count}</td></tr>")
    if not rows:
        return wrap('<div class="m">No endpoints.</div>')
    return wrap("<table><tr><th>endpoint</th><th>type</th><th>pricing</th><th>policies</th><th>about</th><th>★</th></tr>"
                + "".join(rows) + "</table>")


def _applies(cfg) -> str:
    who = cfg.get("applied_to") or ["*"]
    return "everyone" if who == ["*"] else ", ".join(who)


def _rate_limit_words(limit: str) -> str:
    n, _, unit = limit.partition("/")
    per = {"s": "second", "m": "minute", "h": "hour", "d": "day"}.get(unit, unit)
    return f"{n} requests per {per}"


def _policy_summary(p) -> str:
    c = p.config
    facts: list[str] = []
    if p.is_payment:
        cur = c.get("currency", "USD")
        facts.append(f"<b>{money(Money.of(c.get('price', c.get('price_per_request', 0)), cur))}</b> per {c.get('unit_type', 'request')}")
        if p.type.value == "mpp":
            facts.append("paid per query at request time over MPP <span class='m'>(experimental)</span>")
        else:
            facts.append(f"prepaid credits · wallet <code>{_e(c.get('wallet_id', '?'))}</code>"
                         + (f" · managed by <b>{_e(c['wallet_owner'])}</b>" if c.get("wallet_owner") else ""))
            if c.get("bundles"):
                facts.append("bundles: " + ", ".join(f"{b['name']} {money(Money.of(b['amount'], cur))}" for b in c["bundles"]))
            if c.get("payment_url"):
                facts.append(f"<a href='{_e(c['payment_url'])}' target='_blank'>buy credits</a>"
                             + (f" · <a href='{_e(c['credits_url'])}' target='_blank'>balance</a>" if c.get("credits_url") else ""))
        facts.append(f"applies to {_e(_applies(c))}")
    elif p.type.value == "rate_limit":
        facts.append(f"<b>{_e(_rate_limit_words(c.get('limit', '?')))}</b>, {_e(c.get('scope', 'per_user').replace('_', ' '))}")
        facts.append(f"applies to {_e(_applies(c))}")
    elif p.type.value == "access":
        allowed = c.get("allowed_users") or []
        denied = c.get("denied_users") or []
        facts.append("allowed: " + (_e(", ".join(allowed)) if allowed else "everyone"))
        if denied:
            facts.append("denied: " + _e(", ".join(denied)))
    else:
        facts.extend(f"{_e(k)}: {_e(v)}" for k, v in c.items())
    raw = f"<details><summary class='m' style='cursor:pointer'>raw config</summary><code>{_e(c)}</code></details>"
    return "<div>" + "</div><div>".join(facts) + "</div>" + raw


def endpoint_card(e: "Endpoint") -> str:
    pol = "".join(f"<tr><td>{badge(p.type.value, 'warn' if p.is_payment else 'mute')}</td><td class='m'>{_e(p.description)}</td>"
                  f"<td>{_policy_summary(p)}</td></tr>" for p in e.policies)
    policies = (f"<div class='m' style='margin-top:6px'>policies</div>"
                f"<table><tr><th>type</th><th>name</th><th>what it means</th></tr>{pol}</table>"
                if pol else "<div class='m' style='margin-top:6px'>no policies: free, open, unlimited</div>")
    conn = ", ".join(f"{c.type} {c.config.get('url', '')}" for c in e.connect)
    hk = {"healthy": "ok", "unhealthy": "warn"}.get(e.health.value, "mute")
    return wrap(f'<div class="card"><div class="t">{_e(e.name)} <span class="m">{_e(e.path)}</span> '
                f'{badge(e.type.value, "mute")}{pricing_badge(e.pricing)}{badge(e.health.value, hk)}</div>'
                f'<div class="m">{_e(e.description)}</div>'
                f"<table><tr><th>version</th><td>{_e(e.version)}</td><th>stars</th><td>{e.stars_count}</td>"
                f"<th>tags</th><td>{_e(', '.join(e.tags) or '-')}</td></tr>"
                f"<tr><th>connect</th><td colspan=5>{_e(conn)}</td></tr>"
                + (f"<tr><th>filters</th><td colspan=5>{_e(', '.join(e.filterable))} "
                   f"<span class='m'>· applied at the Space, before limit</span></td></tr>" if e.filterable else
                   (f"<tr><th>filters</th><td colspan=5><span class='m'>none advertised: filters apply here, after limit</span></td></tr>"
                    if e.type.returns_references else ""))
                + f"</table>{policies}</div>")


def identity_card(me: "Identity") -> str:
    return wrap(f'<div class="card"><div class="t">Signed in as {_e(me.username)} <span class="m">{_e(me.email)}</span> '
                f'{badge(me.auth.value, "info")}</div><table>'
                f'<tr><th>Hub wallet</th><td>{money(me.hub_wallet_balance)} <span class="m">(MPP only, experimental)</span></td></tr></table></div>')


# --------------------------------------------------------------------- plan --
def filter_cell(split, ep) -> str:
    if not split.remote and not split.local:
        return ""
    if not ep.type.returns_references:
        return badge("not a data source", "mute")
    parts = []
    if split.remote:
        parts.append(badge("at the Space", "ok") + " " + _e(", ".join(split.remote)))
    if split.local:
        parts.append(badge("here, after limit", "warn") + " " + _e(", ".join(split.local)))
        if ep.pricing.paid and ep.pricing.unit.value == "document":
            parts.append("<span class='m'>pays for every returned document, matching or not</span>")
    return "<br>".join(parts)


def plan_table(plan) -> str:
    chips = "".join(badge(f"{k} {v}", "info") for k, v in plan.filters.items())
    head = f'<div class="t">{plan.kind.title()} <span class="m">"{_e(plan.query)}"</span> {badge("pre-flight", "mute")} {chips}</div>'
    if not plan.ready:
        srcs = (", ".join(str(s) if not hasattr(s, "path") else s.path for s in plan._sources)
                if plan._sources is not None else "free endpoints the Hub ranks for the query")
        return wrap(head + f"<div class='m'>composed, nothing sent, pre-flight not run yet · sources: {_e(srcs)}"
                           f" · <code>await plan.preflight()</code> to see costs and balances, <code>await plan.execute()</code> to run</div>")
    rows = []
    fcol = bool(plan.filters)
    for r in plan.rows:
        bal = money(r.wallet.balance) if r.wallet else "-"
        warn = " ".join(badge(w, "mute") for w in r.warnings)
        fc = f"<td>{filter_cell(plan.filters_for(r), r.endpoint)}</td>" if fcol else ""
        rows.append(f"<tr><td><b>{_e(r.endpoint.path)}</b></td><td>{pricing_badge(r.endpoint.pricing)}</td>"
                    f"<td>{money(r.estimate) if r.estimate else '-'}</td><td>{bal}</td>"
                    f"<td>{verdict_badge(r.verdict)}{'' if r.send else badge('held', 'mute')}</td>{fc}"
                    f"<td class='m'>{_e(r.note or '')} {warn}</td></tr>")
    b = plan._hub.budget
    foot = (f"<div class='m' style='margin-top:6px'>{len(plan.sending)} of {len(plan.rows)} sources will be sent, in parallel · "
            f"estimated max spend <b>{_sum(plan.estimate)}</b>"
            + (f" · budget remaining <b>{money(b.remaining)}</b>" if b else " · no session budget set")
            + " · nothing sent yet: <code>await plan.execute()</code> to run"
            + (f"<br>{_e(plan.note)}" if plan.note else "") + "</div>")
    pend = "".join(topup_card(t, where="plan") for t in plan.pending)
    fh = "<th>filters</th>" if fcol else ""
    return wrap(head + f"<table><tr><th>endpoint</th><th>pricing</th><th>max cost</th><th>your balance</th><th>pre-flight</th>{fh}<th></th></tr>"
                + "".join(rows) + "</table>" + foot + pend)


# ------------------------------------------------------------------ results --
def results_table(res: "Results") -> str:
    rows = []
    for r in res:
        if r.ok:
            parts = []
            if r.documents or r.kind in (ReturnKind.REFERENCES, ReturnKind.BOTH):
                n = len(r.documents)
                parts.append(f"{n} document{'s' if n != 1 else ''}"
                             + (f" of {len(r.all_documents)} returned" if r.local_filters and n != len(r.all_documents) else "")
                             + (" · filtered at the Space" if r.remote_filters else ""))
            if r.summary:
                parts.append(f"summary: {r.summary[:50]}…")
            what = " · ".join(parts) or "ok"
        else:
            what = r.detail or ""
            if r.rate_limit and r.rate_limit.reset_seconds:
                what += f" · resets in {r.rate_limit.reset_seconds}s"
            if r.attempts > 1:
                what += f" · {r.attempts} attempts"
        pred = badge("predicted, not sent", "mute") if r.predicted else ""
        kind = r.kind.value if r.ok else {"data_source": "references", "model": "summaries", "model_data_source": "both"}[r.endpoint.type.value]
        rows.append(f"<tr><td><b>{_e(r.endpoint.path)}</b></td><td>{badge(kind, 'mute')}</td><td>{outcome_badge(r.outcome, r.reason)}{pred}</td>"
                    f"<td>{_e(what)}</td><td>{money(r.cost) if r.cost else '-'}</td>"
                    f"<td class='m'>{r.elapsed_ms if not r.predicted else '-'} ms</td></tr>")
    pend = "".join(p._repr_html_() for p in res.pending)
    over = [r for r in res if r.reason is Reason.OVER_BUDGET]
    if over:
        pend += wrap(f'<div class="card"><div class="t">{badge("over budget", "warn")} {_e(", ".join(r.endpoint.path for r in over))}</div>'
                     f"<div class='m'>{_e(over[0].note or '')}</div>"
                     f"<div class='m'><code>await results.retry(ignore_budget=True)</code> to send anyway · <code>hub.set_budget(…)</code> then <code>await results.retry()</code></div></div>")
    waiting = sum(r.outcome is Outcome.PAYMENT_REQUIRED for r in res)
    total_line = (f"<div class='m' style='margin-top:6px'>{res.ok_count} returned · {len(res.skipped) - waiting} not answered"
                  f"{' · ' + str(waiting) + ' waiting on you' if waiting else ''}"
                  f" · {len(res.documents)} documents · charged {_sum(res.cost) if res.cost else 'nothing'}"
                  + (f"<br>{_e(res.note)}" if res.note else "") + "</div>")
    charges = ""
    if res.charges:
        crow = "".join(
            f"<tr><td>{_e(c.source)}</td><td>{_e(c.policy_type)}</td>"
            f"<td>{badge(c.status, 'ok' if c.status in ('charged', 'free') else 'warn')}</td>"
            f"<td>{money(c.amount)}</td><td class='m'>{_e(c.wallet or c.rail)}</td>"
            f"<td class='m'>{_e(c.transaction_id or '')}{(' · ' + _e(c.details)) if c.details else ''}</td></tr>"
            for c in res.charges)
        est = (" · pre-flight estimated max " + _sum(res.estimate)) if res.estimate else ""
        b = res._hub.budget
        bud = f" · budget remaining {money(b.remaining)}" if b else ""
        charges = (f"<div class='m' style='margin-top:8px'>charges</div>"
                   f"<table><tr><th>source</th><th>policy</th><th>status</th><th>amount</th><th>wallet / rail</th><th>transaction</th></tr>{crow}</table>"
                   f"<div class='m'>total <b>{_sum(res.cost)}</b>{est}{bud}</div>")
    answers = ""
    if res.answers:
        answers = "".join(
            f"<div class='card'><div class='t'>{_e(p)} {badge('summary', 'info')}</div><div class='ans'>{_e(a)}</div>"
            f"<div class='m'>cost {money(res[p].cost) if res[p].cost else 'free'} · tokens {res[p].usage.get('total_tokens', '-')}</div></div>"
            for p, a in res.answers.items())
    chips = "".join(badge(f"{k} {v}", "info") for k, v in res.filters.items())
    return wrap(f'<div class="t">Results <span class="m">"{_e(res.query)}"</span> {chips}</div>'
                f"<table><tr><th>endpoint</th><th>returns</th><th>outcome</th><th>result</th><th>cost</th><th>latency</th></tr>"
                + "".join(rows) + "</table>" + total_line + answers + charges + pend)


def source_card(r: "SourceResult") -> str:
    docs = "".join(f"<div class='doc'>{_e(d.content)}<div class='score'>similarity_score {d.similarity_score:.2f} · "
                   f"{_e(d.document_id)} · " + " · ".join(f"{_e(k)} {_e(v)}" for k, v in d.metadata.items() if k != "source") + "</div></div>"
                   for d in r.documents)
    if r.remote_filters:
        docs += (f"<div class='m'>filtered at the Space by {_e(r.remote_filters)}"
                 + (f" · Space confirms {_e(r.raw.get('filters_applied'))}" if r.raw.get("filters_applied") is not None else "") + "</div>")
    if r.local_filters and len(r.documents) != len(r.all_documents):
        docs += f"<div class='m'>{len(r.all_documents) - len(r.documents)} more returned (and billed), hidden here by {_e(r.local_filters)}</div>"
    if r.summary:
        docs += f"<div class='ans'>{_e(r.summary)}</div>"
    pm = r.policy_metadata
    ent = "".join(
        f"<tr><td>{_e(e.get('policy_type'))}</td><td>{badge(e.get('status'), 'ok' if e.get('status') in ('charged', 'free', 'applied') else 'warn')}</td>"
        f"<td>{money(Money.of(e['amount'], e.get('currency'))) if e.get('amount') is not None else '-'}</td>"
        f"<td class='m'>{_e((e.get('transaction') or {}).get('id') or e.get('reason_code') or '')}</td>"
        f"<td class='m'>{_e(e.get('reason') or e.get('details') or '')}</td></tr>" for e in pm.get("entries", []))
    envelope = (f"<div class='m' style='margin-top:6px'>policy_metadata · outcome <code>{_e(pm.get('outcome'))}</code></div>"
                f"<table><tr><th>policy_type</th><th>status</th><th>amount</th><th>transaction / reason_code</th><th></th></tr>{ent}</table>"
                if ent else "")
    head = f"HTTP {r.status_code}" if r.status_code else ("predicted client-side, not sent" if r.predicted else "no response")
    extra = f" · {r.attempts} attempts" if r.attempts > 1 else ""
    rl = f"<div class='m'>rate limit {_e(r.rate_limit.limit)} · resets in {r.rate_limit.reset_seconds}s</div>" if r.rate_limit else ""
    return wrap(f'<div class="card"><div class="t">{_e(r.endpoint.path)} {outcome_badge(r.outcome, r.reason)} '
                f'<span class="m">{head} · {r.elapsed_ms} ms{extra} · cost {money(r.cost) if r.cost is not None else "n/a"}</span></div>'
                f"{('<div class=m>' + _e(r.detail) + '</div>') if r.detail and not r.ok else ''}{rl}{docs}{envelope}</div>")


# ------------------------------------------------------------------ wallets --
def wallets_table(ws) -> str:
    rows = []
    for w in ws:
        bundles = ", ".join(f"{b.id} {money(b.amount)}" for b in w.bundles)
        bal = money(w.balance) if w.balance is not None else "…"
        kind = "ok" if w.balance else "warn"
        rows.append(f"<tr><td><b>{_e(w.owner)}</b><div class='m'>{_e(w.key)}</div></td>"
                    f"<td>{badge(w.rail.value, 'mute')}</td><td>{_e(w.currency)}</td>"
                    f"<td>{badge(bal, kind)}</td><td>{'<br>'.join(_e(p) for p in w.endpoints)}</td>"
                    f"<td class='m'>{_e(bundles)}</td></tr>")
    if not rows:
        return wrap('<div class="m">No prepaid wallets: none of these endpoints bill via prepaid credits.</div>')
    return wrap("<div class='t'>Your wallets</div><table><tr><th>wallet owner</th><th>rail</th><th>currency</th>"
                "<th>your balance</th><th>backs</th><th>bundles</th></tr>" + "".join(rows) + "</table>"
                "<div class='m'>one wallet per owner × rail × currency; a top-up funds every endpoint it backs</div>")


def topup_card(t: TopUp, where: str = "results") -> str:
    bundles = " ".join(badge(f"{b.id}: {money(b.amount)}", "mute") for b in t.bundles)
    who = ", ".join(t.waiting) if t.waiting else t.endpoint.path
    after = {"plan": "await plan.execute()", "results": "await results.retry()", "chat": "await chat.send(...)"}[where]
    obj = {"plan": "plan", "results": "results", "chat": "chat"}[where]
    return wrap(f'<div class="card"><div class="t">{badge("needs credits", "warn")} {_e(who)}</div>'
                f"<table><tr><th>wallet</th><td>{_e(t.wallet.owner)} · {badge(t.wallet.rail.value, 'mute')} {_e(t.wallet.currency)}"
                f" <span class='m'>{_e(t.wallet.key)}"
                f"{' · also backs ' + _e(', '.join(p for p in t.wallet.endpoints if p not in t.waiting)) if len(t.wallet.endpoints) > len(t.waiting) else ''}</span></td></tr>"
                f"<tr><th>your balance</th><td>{money(t.balance)}"
                f"{' · needed ' + money(t.needed) if t.needed is not None else ''}</td></tr>"
                f"<tr><th>bundles</th><td>{bundles}</td></tr></table>"
                f"<div class='m'><code>invoice = await {obj}.top_up(\"{_e(t.waiting[0] if t.waiting else t.endpoint.path)}\", \"starter\")</code>"
                f" → pay at invoice.checkout_url → <code>{after}</code></div></div>")


def invoice_card(inv: "Invoice") -> str:
    kind = "ok" if inv.paid else "warn"
    return wrap(f'<div class="card"><div class="t">Invoice {_e(inv.id)} {badge(inv.status.value, kind)}</div>'
                f"<table><tr><th>wallet</th><td>{_e(inv.wallet_key)}</td></tr>"
                f"<tr><th>bundle</th><td>{_e(inv.bundle)} · <b>{money(inv.amount)}</b></td></tr>"
                + (f"<tr><th>checkout</th><td><a href='{_e(inv.checkout_url)}' target='_blank'>{_e(inv.checkout_url)}</a></td></tr>" if inv.checkout_url else "")
                + f"</table><div class='m'>{'credited: the wallet has the new balance' if inv.paid else 'pay at the link; the provider webhook credits the wallet · <code>await invoice.wait_paid()</code> in a script'}</div></div>")


def charge_card(c: "Charge") -> str:
    return wrap(f'<div class="card"><div class="t">{badge("payment required", "info")} {_e(c.endpoint.path)} '
                f'<span class="m">MPP, experimental</span></div>'
                f"<table><tr><th>amount</th><td><b>{money(c.amount)}</b> from your Hub wallet</td></tr>"
                f"<tr><th>challenge</th><td><code>{_e(c.www_authenticate[:40])}…</code> <span class='m'>(redacted)</span></td></tr></table>"
                f"<div class='m'><code>await results.approve(\"{_e(c.endpoint.path)}\")</code> → retried with X-Payment</div></div>")


def answer_card(a: "Answer") -> str:
    per = ""
    if a.per_source:
        per = ("<div class='m' style='margin-top:6px'>per source (the Aggregator fanned out)</div><table>" + "".join(
            f"<tr><td><b>{_e(r.endpoint.path)}</b></td><td>{outcome_badge(r.outcome, r.reason)}</td>"
            f"<td class='m'>{len(r.documents)} documents · {money(r.cost) if r.cost else 'free'}</td></tr>" for r in a.per_source) + "</table>")
    if not a.ok:
        pend = "".join(p._repr_html_() for p in a.pending)
        from ..models import Charge
        how = ("<code>await answer.approve()</code> pays the MPP charges from your Hub wallet and resumes the job"
               if any(isinstance(p, Charge) for p in a.pending) else
               "buy the bundle (<code>await answer.pending[0].buy(\"starter\")</code>), pay at the link, then <code>await answer.resume()</code>")
        return wrap(f'<div class="card"><div class="t">Answer {badge("pending", "warn")} <span class="m">job {_e(a.job_id)}</span></div>'
                    f"<div class='m'>the Aggregator stopped at sources that need paying · {how}</div>{per}{pend}</div>")
    cites = "".join(f"<tr><td class='cite'>[{n}]</td><td>{_e(p)}</td></tr>" for n, p in a.citations.items())
    rer = ""
    if a.reranked:
        rer = ("<div class='m' style='margin-top:6px'>reranked context from the Aggregator</div>"
               + "".join(f"<div class='doc'>{_e(d.content[:120])}<div class='score'>{_e(p)} · {d.similarity_score:.2f}</div></div>"
                         for p, d in a.reranked[:5]))
    return wrap(f'<div class="card"><div class="t">Answer {badge("aggregator", "info")} <span class="m">model {_e(a.model.path)}</span></div>'
                f"<div class='ans'>{_e(a.text)}</div><table>{cites}</table>{rer}{per}"
                f"<div class='m'>model cost {money(a.cost) if a.cost else 'free'} · tokens {a.usage.get('total_tokens', '-')}</div></div>")


# ------------------------------------------------------------------- chat --
def _turn_block(prompt: str, r) -> str:
    if r.ok:
        return f"<div class='doc'><b>you</b> {_e(prompt)}</div><div class='ans'>{_e(r.text).replace(chr(10), '<br>')}</div>"
    return f"<div class='doc'><b>you</b> {_e(prompt)}</div><div class='m'>{outcome_badge(r.outcome, r.reason)} not sent</div>"


def _model_tab(chat, ep) -> tuple[str, str]:
    path = ep.path
    active = path in chat.active
    row = chat.rows.get(path)
    p = ep.pricing
    if row is not None:
        bal = money(row.wallet.balance) if row.wallet else "-"
        head = (f"<table><tr><th>per message</th><td>{pricing_badge(p)}</td><th>your balance</th><td>{bal}</td>"
                f"<th>pre-flight</th><td>{verdict_badge(row.verdict)}</td></tr></table><div class='m'>{_e(row.note or '')}</div>")
    else:
        head = f"<div class='m'>{pricing_badge(p)} not asked any more</div>"
    joined = chat.joined_at.get(path, 1)
    brief = chat.briefed_with.get(path)
    life = []
    if joined > 1:
        life.append(f"joined at turn {joined}" + (f", briefed with {_e(brief)}'s transcript" if brief else ", no earlier turns"))
    if chat.left_at.get(path):
        life.append(f"left at turn {chat.left_at[path]}")
    life.append(f"spent {_sum(chat.spent_by(path)) if chat.spent_by(path) else 'nothing'}")
    turns = "".join(_turn_block(t.prompt, t[path]) for t in chat.turns if path in t.models)
    pend = "".join(topup_card(t, where="chat") for t in chat.pending if path in t.waiting)
    label = _e(path) + ("" if active else " <span class='m'>(left)</span>")
    return label, head + f"<div class='m'>{' · '.join(life)}</div>" + turns + pend


def chat_card(chat) -> str:
    if not chat._resolved:
        who = ", ".join(str(m) if not hasattr(m, "path") else m.path for m in chat._pending_models)
        return wrap(f'<div class="card"><div class="t">Chat with {_e(who)} {badge(chat.via.value, "info")}</div>'
                    f"<div class='m'>composed, nothing sent · <code>await chat.preflight()</code> to see price per message and balances, "
                    f"<code>await chat.send(prompt)</code> to talk</div></div>")
    about = (f"about the {len(chat._fixed)} sources of \"{_e(chat._fixed.query)}\"" if chat._fixed is not None
             else f"searching {len(chat.sources or [])} sources each turn" if chat.sources else "no sources, models only")
    ctx = chat.context
    c = ctx.counts
    src = (f"{c['references']} passages + {c['summaries']} summar{'y' if c['summaries'] == 1 else 'ies'} "
           f"(~{ctx.source_tokens:,} tokens)" if ctx.items else "no passages")
    hist = (f"{ctx.turns} earlier turn{'s' if ctx.turns != 1 else ''} (~{ctx.history_tokens:,} tokens"
            + (", each model its own answers" if len(chat.active) > 1 else "") + ")" if ctx.history else "no earlier turns")
    ctx_line = f"{hist} + {src}" + (f" · ~{ctx.tokens:,} tokens together" if ctx.history and ctx.items else "")
    who = ", ".join(chat.active) or "nobody"
    title = f"Chat with {_e(who)}" if len(chat.active) <= 1 else f"Chat with {len(chat.active)} models"
    panels = [_model_tab(chat, ep) for ep in chat.models]
    return wrap(f'<div class="card"><div class="t">{title} {badge(chat.via.value, "info")} <span class="m">{about}</span></div>'
                f"<table><tr><th>next message carries</th><td>{_e(ctx_line)} "
                f"<span class='m'>· chat.context to see it, chat.use(view) to change the passages, chat.reset() to drop the turns</span></td></tr>"
                f"<tr><th>spent so far</th><td>{_sum(chat.spent) if chat.spent else 'nothing'} over {chat.turn} turn{'s' if chat.turn != 1 else ''}"
                f" · chat.add(model) / chat.remove(model) change who answers · chat.fork() branches</td></tr></table>"
                f"{tabs(panels) if panels else ''}</div>")


def reply_card(reply) -> str:
    return wrap(f'<div class="card">{reply_body(reply)}</div>')


def reply_body(reply, *, with_prompt: bool = True) -> str:
    mr = reply.result
    if not reply.ok:
        pend = "".join(p._repr_html_() if not isinstance(p, TopUp) else topup_card(p, where="chat") for p in reply.pending)
        return (f'<div class="t">{_e(reply.model.path)} {outcome_badge(mr.outcome, mr.reason)}'
                f'{badge("predicted, not sent", "mute") if mr.predicted else ""}</div>'
                f"<div class='m'>{_e(mr.detail or '')}</div>" + pend)
    cites = "".join(f"<tr><td class='cite'>[{n}]</td><td>{_e(p)}</td></tr>" for n, p in reply.citations.items()
                    if f"[{n}]" in (reply.text or ""))
    ch = ""
    if reply.charges:
        ch = "<div class='m' style='margin-top:6px'>charges · " + " · ".join(
            f"{_e(c.source)} {money(c.amount)} {badge(c.status, 'ok' if c.status in ('charged', 'free') else 'warn')}"
            for c in reply.charges if c.amount) + "</div>"
    text = _e(reply.text or "").replace("\n", "<br>")
    you = f'<div class="doc"><b>you</b> {_e(reply.prompt)}</div>' if with_prompt else ""
    return (f"{you}<div class='ans'>{text}</div><table>{cites}</table>"
            f"<div class='m'>{_e(reply.model.path)} · turn {reply.turn} · tokens {mr.usage.get('total_tokens', '-')}</div>{ch}")


def replies_card(rs) -> str:
    this = _sum(rs.cost) if rs.cost else "free"
    so_far = _sum(rs.spent_so_far) if rs.spent_so_far else "free"
    search = f" · searched {len(rs.results)} sources ({len(rs.results.documents)} documents)" if rs.searched and rs.results is not None else ""
    foot = f"<div class='m' style='margin-top:6px'>this turn {this}{search} · conversation so far {so_far}</div>"
    if len(rs) == 1:
        return wrap(f'<div class="card">{reply_body(rs[0])}{foot}</div>')
    panels = [(_e(r.model.path) + (" " + outcome_badge(r.outcome, r.reason) if not r.ok else ""), reply_body(r, with_prompt=False))
              for r in rs]
    return wrap(f'<div class="card"><div class="doc"><b>you</b> {_e(rs.prompt)}</div>{tabs(panels)}{foot}</div>')


def context_card(ctx) -> str:
    c = ctx.counts

    def _trows(msgs, who="model"):
        return "".join(
            f"<tr><td class='cite'>{'you' if m.role.value == 'user' else who}</td>"
            f"<td colspan=4>{_e(m.content[:140])}{'…' if len(m.content) > 140 else ''}</td></tr>" for m in msgs)

    if ctx.history or any(ctx.transcripts.values()):
        if len(ctx.transcripts) > 1:
            panels = [(_e(p), f"<table>{_trows(msgs)}</table>" if msgs else "<div class='m'>no earlier turns for this model</div>")
                      for p, msgs in ctx.transcripts.items()]
            hist = (f"<tr><th colspan=5>earlier turns <span class='m'>shared questions, each model its own answers · "
                    f"~{ctx.history_tokens:,} tokens for the first · chat.reset() drops them</span></th></tr>"
                    f"<tr><td colspan=5>{tabs(panels)}</td></tr>")
        else:
            hist = (f"<tr><th colspan=5>earlier turns <span class='m'>{ctx.turns}, ~{ctx.history_tokens:,} tokens · "
                    f"chat.reset() drops them</span></th></tr>{_trows(ctx.history)}")
    else:
        hist = "<tr><th colspan=5>earlier turns <span class='m'>none</span></th></tr>"
    filt = ""
    if ctx.view is not None and ctx.view.filters:
        filt = " · filters " + "".join(badge(f"{k} {v}", "info") for k, v in ctx.view.filters.items())
    if ctx.items:
        rows = "".join(
            f"<tr><td class='cite'>[{i}]</td><td>{badge(kind, 'info' if kind == 'summary' else 'mute')}</td>"
            f"<td>{_e(p)}</td><td>{f'{sc:.2f}' if sc is not None else '-'}</td><td>{_e(t[:110])}{'…' if len(t) > 110 else ''}</td></tr>"
            for i, (p, t, sc, kind) in enumerate(ctx.items, 1))
        src = (f"<tr><th colspan=5>passages <span class='m'>{c['references']} references, {c['summaries']} summaries, "
               f"~{ctx.source_tokens:,} tokens, include={_e(ctx.include.value)}{filt} · chat.use(view) changes them</span></th></tr>"
               f"<tr><th></th><th>kind</th><th>from</th><th>score</th><th>text</th></tr>{rows}")
    else:
        src = "<tr><th colspan=5>passages <span class='m'>none: the model answers from its own knowledge</span></th></tr>"
    return wrap(f"<div class='t'>What the next message carries <span class='m'>~{ctx.tokens:,} tokens besides the prompt</span></div>"
                f"<table>{hist}{src}</table>")
