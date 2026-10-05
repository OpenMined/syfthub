"""HTML rendering (Jupyter ``_repr_html_``). Pure functions; no widgets."""
from __future__ import annotations

import html
import uuid
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:  # pragma: no cover
    from .models import Answer, Charge, Endpoint, Identity, SourceResult, TopUp
    from .results import Results

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
.sh .tabs>input:nth-of-type(1):checked~.panel:nth-of-type(1){display:block}.sh .tabs>input:nth-of-type(2):checked~.panel:nth-of-type(2){display:block}.sh .tabs>input:nth-of-type(3):checked~.panel:nth-of-type(3){display:block}.sh .tabs>input:nth-of-type(4):checked~.panel:nth-of-type(4){display:block}.sh .tabs>input:nth-of-type(5):checked~.panel:nth-of-type(5){display:block}.sh .tabs>input:nth-of-type(6):checked~.panel:nth-of-type(6){display:block}.sh .tabs>input:nth-of-type(7):checked~.panel:nth-of-type(7){display:block}.sh .tabs>input:nth-of-type(8):checked~.panel:nth-of-type(8){display:block}
</style>"""


def money(amount: float | None, currency: str | None = "USD") -> str:
    if amount is None:
        return "-"
    sym = {"USD": "$", "EUR": "€", "IDR": "Rp"}.get(currency or "USD", f"{currency} ")
    return f"{sym}{amount:,.0f}" if currency == "IDR" else f"{sym}{amount:,.2f}"


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


def outcome_badge(o, reason=None) -> str:
    from .models import Outcome, SkipReason
    if o is Outcome.SUCCESS:
        return badge("returned", "ok")
    if o is Outcome.PAYMENT_REQUIRED:
        return badge("payment required", "warn")
    kind = {SkipReason.NO_CREDITS: "warn", SkipReason.OVER_BUDGET: "warn", SkipReason.RATE_LIMITED: "warn",
            SkipReason.BY_USER: "mute"}.get(reason, "bad") if reason else "mute"
    return badge("skipped", "mute") + (badge(reason.value.replace("_", " "), kind) if reason else "")


def pricing_badge(p) -> str:
    from .models import Rail
    if not p.paid:
        return badge("free", "ok")
    return badge(p.label(), "info" if p.rail is Rail.MPP else "warn")


# ---------------------------------------------------------------- endpoints --
def selection_table(sel: Iterable["Endpoint"]) -> str:
    rows = []
    for e in sel:
        other = [badge(p.type, "mute") for p in e.policies if not p.is_payment]
        rows.append(f"<tr><td><b>{_e(e.path)}</b><div class='m'>{_e(e.name)}</div></td>"
                    f"<td>{badge(e.type, 'mute')}</td><td>{pricing_badge(e.pricing)}</td>"
                    f"<td>{''.join(other)}</td><td class='m'>{_e(e.description)}</td><td class='m'>{e.stars_count}</td></tr>")
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
    """Words, not a dict. One line per fact; the raw config stays behind a disclosure."""
    c = p.config
    facts: list[str] = []
    if p.is_payment:
        cur = c.get("currency", "USD")
        facts.append(f"<b>{money(c.get('price', c.get('price_per_request', 0)), cur)}</b> per {c.get('unit_type', 'request')}")
        if p.type == "mpp":
            facts.append("paid per query at request time over MPP <span class='m'>(experimental)</span>")
        else:
            facts.append(f"prepaid credits · wallet <code>{_e(c.get('wallet_id', '?'))}</code>"
                         + (f" · managed by <b>{_e(c['wallet_owner'])}</b>" if c.get("wallet_owner") else ""))
            if c.get("bundles"):
                facts.append("bundles: " + ", ".join(f"{b['name']} {money(b['amount'], cur)}" for b in c["bundles"]))
            if c.get("payment_url"):
                facts.append(f"<a href='{_e(c['payment_url'])}' target='_blank'>buy credits</a>"
                             + (f" · <a href='{_e(c['credits_url'])}' target='_blank'>balance</a>" if c.get("credits_url") else ""))
        facts.append(f"applies to {_e(_applies(c))}")
    elif p.type == "rate_limit":
        facts.append(f"<b>{_e(_rate_limit_words(c.get('limit', '?')))}</b>, {_e(c.get('scope', 'per_user').replace('_', ' '))}")
        facts.append(f"applies to {_e(_applies(c))}")
    elif p.type == "access":
        allowed = c.get("allowed_users") or []
        denied = c.get("denied_users") or []
        facts.append("allowed: " + (_e(", ".join(allowed)) if allowed else "everyone"))
        if denied:
            facts.append("denied: " + _e(", ".join(denied)))
    else:
        facts.extend(f"{_e(k)}: {_e(v)}" for k, v in c.items())
    raw = f"<details><summary class='m' style='cursor:pointer'>raw config</summary><code>{_e(c)}</code></details>"
    return "<div>" + "</div><div>".join(facts) + "</div>" + raw


def _policy_row(p) -> str:
    kind = "warn" if p.is_payment else "mute"
    return (f"<tr><td>{badge(p.type, kind)}</td><td class='m'>{_e(p.description)}</td>"
            f"<td>{_policy_summary(p)}</td></tr>")


def endpoint_card(e: "Endpoint") -> str:
    pol = "".join(_policy_row(p) for p in e.policies)
    policies = (f"<div class='m' style='margin-top:6px'>policies</div>"
                f"<table><tr><th>type</th><th>name</th><th>what it means</th></tr>{pol}</table>"
                if pol else "<div class='m' style='margin-top:6px'>no policies: free, open, unlimited</div>")
    conn = ", ".join(f"{c.type} {c.config.get('url', '')}" for c in e.connect)
    return wrap(f'<div class="card"><div class="t">{_e(e.name)} <span class="m">{_e(e.path)}</span> '
                f'{badge(e.type, "mute")}{pricing_badge(e.pricing)}</div>'
                f'<div class="m">{_e(e.description)}</div>'
                f"<table><tr><th>version</th><td>{_e(e.version)}</td><th>stars</th><td>{e.stars_count}</td>"
                f"<th>tags</th><td>{_e(', '.join(e.tags) or '-')}</td></tr>"
                f"<tr><th>connect</th><td colspan=5>{_e(conn)}</td></tr>"
                + (f"<tr><th>filters</th><td colspan=5>{_e(', '.join(e.filterable))} "
                   f"<span class='m'>· applied at the Space, before limit</span></td></tr>" if e.filterable else
                   (f"<tr><th>filters</th><td colspan=5><span class='m'>none advertised: filters apply here, after limit</span></td></tr>"
                    if "data_source" in e.type else ""))
                + f"</table>{policies}</div>")


def identity_card(me: "Identity") -> str:
    b = me.budget
    budget = f"{money(b.remaining, b.currency)} of {money(b.limit, b.currency)} left" if b else "none set"
    return wrap(f'<div class="card"><div class="t">Signed in as {_e(me.username)} <span class="m">{_e(me.email)}</span> '
                f'{badge(me.auth, "info")}</div><table><tr><th>session budget</th><td>{budget}</td>'
                f'<tr><th>Hub wallet</th><td>{money(me.hub_wallet_balance)} <span class="m">(MPP only, experimental)</span></td></tr></table></div>')


# --------------------------------------------------------------------- plan --
def filter_cell(to_space: dict, here: dict, ep) -> str:
    """Where each filter key lands for one source, for the pre-flight and results tables."""
    if not to_space and not here:
        return ""
    if "data_source" not in ep.type:
        return badge("not a data source", "mute")
    parts = []
    if to_space:
        parts.append(badge("at the Space", "ok") + " " + _e(", ".join(to_space)))
    if here:
        parts.append(badge("here, after limit", "warn") + " " + _e(", ".join(here)))
        if ep.pricing.paid and ep.pricing.unit == "document":
            parts.append("<span class='m'>pays for every returned document, matching or not</span>")
    return "<br>".join(parts)


def search_table(plan) -> str:
    rows = []
    fcol = bool(plan.filters)
    for r in plan.rows:
        kind = {"ready": "ok", "will ask to pay": "info", "needs credits": "warn",
                "over budget": "warn", "access denied": "bad"}.get(r.verdict, "mute")
        bal = money(r.wallet.balance, r.wallet.currency) if r.wallet else "-"
        warn = " ".join(badge(w, "mute") for w in r.warnings)
        fc = f"<td>{filter_cell(*plan.filters_for(r), r.endpoint)}</td>" if fcol else ""
        rows.append(f"<tr><td><b>{_e(r.endpoint.path)}</b></td><td>{pricing_badge(r.endpoint.pricing)}</td>"
                    f"<td>{money(r.estimate, r.endpoint.pricing.currency) if r.estimate else '-'}</td><td>{bal}</td>"
                    f"<td>{badge(r.verdict, kind)}{'' if r.send else badge('held', 'mute')}</td>{fc}"
                    f"<td class='m'>{_e(r.note or '')} {warn}</td></tr>")
    b = plan._hub.budget
    foot = (f"<div class='m' style='margin-top:6px'>{len(plan.sending)} of {len(plan.rows)} sources will be sent, in parallel · "
            f"estimated max spend <b>{' + '.join(money(v, k) for k, v in plan.total_estimate.items()) or 'free'}</b>"
            + (f" · budget remaining <b>{money(b.remaining)}</b>" if b else " · no session budget set")
            + " · nothing sent yet: <code>.execute()</code> to run</div>")
    pend = "".join(t._repr_html_().replace("results.top_up", "search.top_up").replace("results.retry()", "search.execute()")
                   for t in plan.pending)
    chips = "".join(badge(f"{k} {v}", "info") for k, v in plan.filters.items())
    fh = "<th>filters</th>" if fcol else ""
    return wrap(f'<div class="t">Search <span class="m">"{_e(plan.query)}"</span> {badge("pre-flight", "mute")} {chips}</div>'
                f"<table><tr><th>endpoint</th><th>pricing</th><th>max cost</th><th>your balance</th><th>pre-flight</th>{fh}<th></th></tr>"
                + "".join(rows) + "</table>" + foot + pend)


# ------------------------------------------------------------------ results --
def results_table(res: "Results") -> str:
    rows = []
    for r in res:
        if r.ok:
            parts = []
            if r.documents or r.returns in ("references", "both"):
                n = len(r.documents)
                parts.append(f"{n} document{'s' if n != 1 else ''}"
                             + (f" of {len(r.all_documents)} returned" if r.filters and n != len(r.all_documents) else "")
                             + (" · filtered at the Space" if r.space_filters else ""))
            if r.summary:
                parts.append(f"summary: {r.summary[:50]}…")
            what = " · ".join(parts) or "ok"
        else:
            what = r.detail or ""
        pred = badge("predicted, not sent", "mute") if r.predicted else ""
        ret = badge(r.returns if r.ok else {"data_source": "references", "model": "summary", "model_data_source": "both"}.get(r.endpoint.type, ""), "mute")
        rows.append(f"<tr><td><b>{_e(r.endpoint.path)}</b></td><td>{ret}</td><td>{outcome_badge(r.outcome, r.reason)}{pred}</td><td>{_e(what)}</td>"
                    f"<td>{money(r.cost, r.currency) if r.cost else '-'}</td><td class='m'>{r.latency_ms if not r.predicted else '-'} ms</td></tr>")
    pend = "".join(p._repr_html_() for p in res.pending)
    over = [r for r in res if r.reason is not None and r.reason.value == "over_budget"]
    if over:
        pend += wrap(f'<div class="card"><div class="t">{badge("over budget", "warn")} {_e(", ".join(r.endpoint.path for r in over))}</div>'
                     f"<div class='m'>{_e(over[0].note or '')}</div>"
                     f"<div class='m'>results.proceed() to send anyway · hub.set_budget(…) then results.retry()</div></div>")
    total = (f"<div class='m' style='margin-top:6px'>{res.ok_count} returned · {len(res.skipped)} skipped"
             f"{' · ' + str(len(res) - res.ok_count - len(res.skipped)) + ' waiting on you' if len(res) - res.ok_count - len(res.skipped) else ''}"
             f" · {len(res.documents)} documents · spent {money(res.spent)}</div>")
    charges = ""
    if res.charges:
        crow = "".join(
            f"<tr><td>{_e(c['source'])}</td><td>{_e(c['policy_type'])}</td>"
            f"<td>{badge(c['status'], 'ok' if c['status'] in ('charged', 'free') else 'warn')}</td>"
            f"<td>{money(c['amount'], c['currency']) if c['amount'] is not None else '-'}</td>"
            f"<td class='m'>{_e(c['wallet'] or c['rail'])}</td>"
            f"<td class='m'>{_e(c['transaction_id'] or '')}{(' · ' + _e(c['details'])) if c['details'] else ''}</td></tr>"
            for c in res.charges)
        tot = " · ".join(f"<b>{money(v, k)}</b> {k}" for k, v in res.cost.items()) or "nothing"
        est = (" · pre-flight estimated max " + " + ".join(money(v, k) for k, v in res.estimate.items())) if res.estimate else ""
        b = res._hub.budget
        bud = f" · budget remaining {money(b.remaining)}" if b else ""
        charges = (f"<div class='m' style='margin-top:8px'>charges</div>"
                   f"<table><tr><th>source</th><th>policy</th><th>status</th><th>amount</th><th>wallet / rail</th><th>transaction</th></tr>{crow}</table>"
                   f"<div class='m'>total {tot}{est}{bud}</div>")
    answers = ""
    if res.answers:
        answers = "".join(
            f"<div class='card'><div class='t'>{_e(p)} {badge('summary', 'info')}</div><div class='ans'>{_e(a)}</div>"
            f"<div class='m'>cost {money(res[p].cost, res[p].currency) if res[p].cost else 'free'} · "
            f"tokens {((res[p].raw.get('summary') or {}).get('usage') or {}).get('total_tokens', '-')}</div></div>"
            for p, a in res.answers.items())
    chips = "".join(badge(f"{k} {v}", "info") for k, v in res.filters.items())
    return wrap(f'<div class="t">Results <span class="m">"{_e(res.query)}"</span> {chips}</div>'
                f"<table><tr><th>endpoint</th><th>returns</th><th>outcome</th><th>result</th><th>cost</th><th>latency</th></tr>"
                + "".join(rows) + "</table>" + total + answers + charges + pend)


def source_card(r: "SourceResult") -> str:
    docs = "".join(f"<div class='doc'>{_e(d.content)}<div class='score'>similarity_score {d.similarity_score:.2f} · "
                   f"{_e(d.document_id)} · " + " · ".join(f"{_e(k)} {_e(v)}" for k, v in d.metadata.items() if k != "source") + "</div></div>"
                   for d in r.documents)
    if r.space_filters:
        docs += (f"<div class='m'>filtered at the Space by {_e(r.space_filters)}"
                 + (f" · Space confirms {_e(r.raw.get('filters_applied'))}" if r.raw.get("filters_applied") is not None else "") + "</div>")
    if r.filters and len(r.documents) != len(r.all_documents):
        docs += f"<div class='m'>{len(r.all_documents) - len(r.documents)} more returned (and billed), hidden here by {_e(r.filters)}</div>"
    if r.summary:
        docs += f"<div class='ans'>{_e(r.summary)}</div>"
    pm = r.policy_metadata
    ent = "".join(
        f"<tr><td>{_e(e.get('policy_type'))}</td><td>{badge(e.get('status'), 'ok' if e.get('status') in ('charged', 'free', 'applied') else 'warn')}</td>"
        f"<td>{money(e.get('amount'), e.get('currency')) if e.get('amount') is not None else '-'}</td>"
        f"<td class='m'>{_e((e.get('transaction') or {}).get('id') or e.get('reason_code') or '')}</td>"
        f"<td class='m'>{_e(e.get('reason') or e.get('details') or '')}</td></tr>" for e in pm.get("entries", []))
    envelope = (f"<div class='m' style='margin-top:6px'>policy_metadata · outcome <code>{_e(pm.get('outcome'))}</code></div>"
                f"<table><tr><th>policy_type</th><th>status</th><th>amount</th><th>transaction / reason_code</th><th></th></tr>{ent}</table>"
                if ent else "")
    head = f"HTTP {r.status_code}" if r.status_code else ("predicted client-side, not sent" if r.predicted else "no response")
    return wrap(f'<div class="card"><div class="t">{_e(r.endpoint.path)} {outcome_badge(r.outcome, r.reason)} '
                f'<span class="m">{head} · {r.latency_ms} ms · cost {money(r.cost, r.currency) if r.raw.get("cost") is not None else "n/a"}</span></div>'
                f"{('<div class=m>' + _e(r.detail) + '</div>') if r.detail and not r.ok else ''}{docs}{envelope}</div>")


def wallets_table(ws) -> str:
    rows = []
    for w in ws:
        bundles = ", ".join(f"{b['name']} {money(b['amount'], w.currency)}" for b in w.bundles)
        bal = money(w.balance, w.currency) if w.balance is not None else "…"
        kind = "ok" if (w.balance or 0) > 0 else "warn"
        rows.append(f"<tr><td><b>{_e(w.owner)}</b><div class='m'>{_e(w.key)}</div></td>"
                    f"<td>{badge(w.type.value, 'mute')}</td><td>{_e(w.currency)}</td>"
                    f"<td>{badge(bal, kind)}</td><td>{'<br>'.join(_e(p) for p in w.endpoints)}</td>"
                    f"<td class='m'>{_e(bundles)}</td></tr>")
    if not rows:
        return wrap('<div class="m">No prepaid wallets: none of the endpoints you can see bill via prepaid credits.</div>')
    return wrap("<div class='t'>Your wallets</div><table><tr><th>wallet owner</th><th>type</th><th>currency</th>"
                "<th>your balance</th><th>backs</th><th>bundles</th></tr>" + "".join(rows) + "</table>"
                "<div class='m'>one wallet per owner × type × currency; a top-up funds every endpoint it backs</div>")


def topup_card(t: "TopUp") -> str:
    bundles = " ".join(badge(f"{b['name']}: {money(b['amount'], t.currency)}", "mute") for b in t.bundles)
    inv = ""
    if t.invoice:
        inv = (f"<tr><th>checkout</th><td><a href='{_e(t.checkout_url)}' target='_blank'>{_e(t.checkout_url)}</a>"
               f" <span class='m'>invoice {_e(t.invoice['id'])} · {_e(t.invoice['status'])}</span></td></tr>")
    who = ", ".join(t.waiting) if t.waiting else t.endpoint.path
    return wrap(f'<div class="card"><div class="t">{badge("needs credits", "warn")} {_e(who)}</div>'
                f"<table><tr><th>wallet</th><td>{_e(t.wallet.owner)} · {badge(t.wallet.type.value, 'mute')} {_e(t.currency)}"
                f" <span class='m'>{_e(t.wallet.key)}"
                f"{' · also backs ' + _e(', '.join(p for p in t.wallet.endpoints if p != t.endpoint.path)) if len(t.wallet.endpoints) > 1 else ''}</span></td></tr>"
                f"<tr><th>your balance</th><td>{money(t.balance, t.currency)}"
                f"{' · needed ' + money(t.needed, t.currency) if t.needed is not None else ''}</td></tr>"
                f"<tr><th>bundles</th><td>{bundles}</td></tr>{inv}</table>"
                f"<div class='m'>results.top_up(\"{_e(t.endpoint.path)}\", bundle=\"starter\") → pay at the link → results.retry()</div></div>")


def charge_card(c: "Charge") -> str:
    return wrap(f'<div class="card"><div class="t">{badge("payment required", "info")} {_e(c.endpoint.path)} '
                f'<span class="m">MPP, experimental</span></div>'
                f"<table><tr><th>amount</th><td><b>{money(c.amount, c.currency)}</b> from your Hub wallet</td></tr>"
                f"<tr><th>challenge</th><td><code>{_e(c.www_authenticate[:70])}…</code></td></tr></table>"
                f"<div class='m'>results.approve(\"{_e(c.endpoint.path)}\") → retried with X-Payment</div></div>")


def answer_card(a: "Answer") -> str:
    cites = "".join(f"<tr><td class='cite'>[{n}]</td><td>{_e(p)}</td></tr>" for n, p in a.citations.items())
    rer = ""
    if a.reranked:
        rer = ("<div class='m' style='margin-top:6px'>reranked context from the aggregator</div>"
               + "".join(f"<div class='doc'>{_e(d.content[:120])}<div class='score'>{_e(p)} · {d.similarity_score:.2f}</div></div>"
                         for p, d in a.reranked[:5]))
    return wrap(f'<div class="card"><div class="t">Answer {badge(a.via, "info")} <span class="m">model {_e(a.model.path)}</span></div>'
                f"<div class='ans'>{_e(a.text)}</div><table>{cites}</table>{rer}"
                f"<div class='m'>model cost {money(a.cost, a.currency) if a.cost else 'free'} · "
                f"tokens {a.usage.get('total_tokens', '-')}</div></div>")


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
    head = ""
    if row is not None:
        kind = {"ready": "ok", "will ask to pay": "info", "needs credits": "warn", "over budget": "warn",
                "access denied": "bad"}.get(row.verdict, "mute")
        bal = money(row.wallet.balance, row.wallet.currency) if row.wallet else "-"
        head = (f"<table><tr><th>per message</th><td>{pricing_badge(p)}</td><th>your balance</th><td>{bal}</td>"
                f"<th>pre-flight</th><td>{badge(row.verdict, kind)}</td></tr></table><div class='m'>{_e(row.note or '')}</div>")
    else:
        head = f"<div class='m'>{pricing_badge(p)} not asked any more</div>"
    joined = chat.joined_at.get(path, 1)
    brief = chat.briefed_with.get(path)
    life = []
    if joined > 1:
        life.append(f"joined at turn {joined}" + (f", briefed with {_e(brief)}'s transcript" if brief else ", no earlier turns"))
    if chat.left_at.get(path):
        life.append(f"left at turn {chat.left_at[path]}")
    sp = " ".join(money(v, k) for k, v in chat.spent_by(path).items()) or "nothing"
    life.append(f"spent {sp}")
    turns = "".join(_turn_block(t.prompt, t[path]) for t in chat.turns if path in t.models)
    pend = "".join(t._repr_html_().replace("results.top_up(\"" + _e(path) + "\", ", f"chat.top_up(\"{_e(path)}\", ")
                   .replace("results.retry()", "chat.send(...)") for t in chat.pending if path in t.waiting)
    label = _e(path) + ("" if active else " <span class='m'>(left)</span>")
    return label, head + f"<div class='m'>{' · '.join(life)}</div>" + turns + pend


def chat_card(chat) -> str:
    about = (f"about the {len(chat._fixed)} sources of \"{_e(chat._fixed.query)}\"" if chat._fixed is not None
             else f"searching {len(chat.sources or [])} sources each turn" if chat.sources else "no sources, models only")
    ctx = chat.context
    c = ctx.counts
    src = (f"{c['references']} passages + {c['summaries']} summar{'y' if c['summaries'] == 1 else 'ies'} "
           f"(~{ctx.source_tokens:,} tokens)" if ctx.items else "no passages")
    hist = (f"{ctx.turns} earlier turn{'s' if ctx.turns != 1 else ''} (~{ctx.history_tokens:,} tokens"
            + (", each model its own answers" if len(chat.active) > 1 else "") + ")" if ctx.history else "no earlier turns")
    ctx_line = f"{hist} + {src}" + (f" · ~{ctx.tokens:,} tokens together" if ctx.history and ctx.items else "")
    spent = " ".join(money(v, k) for k, v in chat.spent.items()) or "nothing"
    who = ", ".join(chat.active) or "nobody"
    title = f"Chat with {_e(who)}" if len(chat.active) <= 1 else f"Chat with {len(chat.active)} models"
    panels = [_model_tab(chat, ep) for ep in chat.models]
    return wrap(f'<div class="card"><div class="t">{title} {badge(chat.via, "info")} <span class="m">{about}</span></div>'
                f"<table><tr><th>next message carries</th><td>{_e(ctx_line)} "
                f"<span class='m'>· chat.context to see it, chat.use(view) to change the passages, chat.reset() to drop the turns</span></td></tr>"
                f"<tr><th>spent so far</th><td>{spent} over {chat.turn} turn{'s' if chat.turn != 1 else ''}"
                f"{' · chat.add(model) / chat.remove(model) change who answers' if True else ''}</td></tr></table>"
                f"{tabs(panels)}</div>")


def reply_card(reply) -> str:
    return wrap(f'<div class="card">{reply_body(reply)}</div>')


def reply_body(reply, *, with_prompt: bool = True) -> str:
    mr = reply.model_result
    if not reply.ok:
        pend = "".join(t._repr_html_().replace("results.top_up(\"" + _e(reply.model.path) + "\", ", "reply.top_up(")
                       .replace("results.retry()", "chat.send(...)") for t in reply.pending)
        return (f'<div class="t">{_e(reply.model.path)} {outcome_badge(mr.outcome, mr.reason)}'
                f'{badge("predicted, not sent", "mute") if mr.predicted else ""}</div>'
                f"<div class='m'>{_e(mr.detail or '')}</div>" + pend)
    cites = "".join(f"<tr><td class='cite'>[{n}]</td><td>{_e(p)}</td></tr>" for n, p in reply.citations.items()
                    if f"[{n}]" in (reply.text or ""))
    ch = ""
    if reply.charges:
        ch = "<div class='m' style='margin-top:6px'>charges · " + " · ".join(
            f"{_e(c['source'])} {money(c['amount'], c['currency'])} {badge(c['status'], 'ok' if c['status'] in ('charged', 'free') else 'warn')}"
            for c in reply.charges if c["amount"]) + "</div>"
    usage = ((mr.raw.get("summary") or {}).get("usage") or {}).get("total_tokens", "-")
    text = _e(reply.text or "").replace("\n", "<br>")
    you = f'<div class="doc"><b>you</b> {_e(reply.prompt)}</div>' if with_prompt else ""
    return (f"{you}<div class='ans'>{text}</div><table>{cites}</table>"
            f"<div class='m'>{_e(reply.model.path)} · turn {reply.turn} · tokens {usage}</div>{ch}")


def replies_card(rs) -> str:
    total = " ".join(money(v, k) for k, v in rs.chat.spent.items()) or "free"
    this = " ".join(money(v, k) for k, v in rs.cost.items()) or "free"
    search = ""
    if rs.searched and rs.results is not None:
        search = f" · searched {len(rs.results)} sources ({len(rs.results.documents)} documents)"
    foot = f"<div class='m' style='margin-top:6px'>this turn {this}{search} · conversation so far {total}</div>"
    if len(rs) == 1:
        return wrap(f'<div class="card">{reply_body(rs[0])}{foot}</div>')
    panels = [(_e(r.model.path) + (" " + outcome_badge(r.outcome, r.reason) if not r.ok else ""), reply_body(r, with_prompt=False))
              for r in rs]
    return wrap(f'<div class="card"><div class="doc"><b>you</b> {_e(rs.prompt)}</div>{tabs(panels)}{foot}</div>')


def context_card(ctx) -> str:
    c = ctx.counts
    def _trows(msgs, who="model"):
        return "".join(
            f"<tr><td class='cite'>{'you' if m['role'] == 'user' else who}</td>"
            f"<td colspan=4>{_e(m['content'][:140])}{'…' if len(m['content']) > 140 else ''}</td></tr>"
            for m in msgs)
    hist = ""
    if ctx.history or any(ctx.transcripts.values()):
        if len(ctx.transcripts) > 1:
            panels = [(_e(p), f"<table>{_trows(msgs, 'model')}</table>" if msgs else "<div class='m'>no earlier turns for this model</div>")
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
               f"~{ctx.source_tokens:,} tokens, include={_e(ctx.include)}{filt} · chat.use(view) changes them</span></th></tr>"
               f"<tr><th></th><th>kind</th><th>from</th><th>score</th><th>text</th></tr>{rows}")
    else:
        src = "<tr><th colspan=5>passages <span class='m'>none: the model answers from its own knowledge</span></th></tr>"
    return wrap(f"<div class='t'>What the next message carries <span class='m'>~{ctx.tokens:,} tokens besides the prompt</span></div>"
                f"<table>{hist}{src}</table>")
