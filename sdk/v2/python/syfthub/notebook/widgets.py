"""Buttons for pending payments, for a live kernel with ipywidgets. Every button calls the same public
method a script would; the widget holds the latest ``Results`` and re-renders it. Needs ``syfthub[notebook]``."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..results import Results


def available() -> bool:
    try:
        import ipywidgets  # noqa: F401
        return True
    except Exception:
        return False


def results_card(results: "Results", *, on_update=None):
    """A results table with Buy, Approve, Skip and Retry buttons.

    Args:
        results: The results to show.
        on_update: Called with each new ``Results`` after a button acts, so your own variable can follow.

    Returns:
        An ipywidgets box, or plain HTML when ipywidgets is missing."""
    from IPython.display import HTML, display
    if not available():
        return HTML(results._repr_html_())
    import ipywidgets as w

    state = {"res": results}
    out, box = w.Output(), w.HBox()

    def refresh() -> None:
        out.clear_output(wait=True)
        with out:
            display(HTML(state["res"]._repr_html_()))
        box.children = tuple(_buttons())
        if on_update:
            on_update(state["res"])

    def run(coro) -> None:
        asyncio.ensure_future(_apply(coro))

    async def _apply(coro) -> None:
        state["res"] = await coro
        refresh()

    def _buttons():
        from ..models import TopUp
        btns = []
        for p in state["res"].pending:
            if isinstance(p, TopUp):
                for b in p.bundles:
                    btn = w.Button(description=f"Buy {b.id} ({b.amount}) · {p.wallet.key}", button_style="warning", icon="credit-card")
                    btn.on_click(lambda _, key=p.wallet.key, bid=b.id: asyncio.ensure_future(state["res"].top_up(key, bid)))
                    btns.append(btn)
            else:
                btn = w.Button(description=f"Approve {p.endpoint.path}", button_style="info", icon="check")
                btn.on_click(lambda _, path=p.endpoint.path: run(state["res"].approve(path)))
                btns.append(btn)
        if any(r.retryable for r in state["res"]):
            r = w.Button(description="Retry", button_style="success", icon="refresh")
            r.on_click(lambda _: run(state["res"].retry()))
            btns.append(r)
        return btns

    refresh()
    return w.VBox([out, box])
