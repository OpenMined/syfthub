"""Interactive layer, on only when ``connect(..., interactive=True)``.
Buttons call the same public methods a script calls. Needs a live kernel with
the ipywidgets frontend; otherwise you get the static HTML."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .results import Results


def available() -> bool:
    try:
        import ipywidgets  # noqa: F401
        return True
    except Exception:
        return False


def results_card(res: "Results"):
    from IPython.display import HTML
    if not available():
        return HTML(res._repr_html_())
    import ipywidgets as w
    from IPython.display import display

    out = w.Output()
    box = w.HBox()

    def refresh(*_):
        out.clear_output(wait=True)
        with out:
            display(HTML(res._repr_html_()))
        box.children = tuple(_buttons())

    def _buttons():
        btns = []
        for p in res.pending:
            path = p.endpoint.path
            if hasattr(p, "bundles"):                      # TopUp
                for b in p.bundles:
                    btn = w.Button(description=f"Buy {b['name']} ({b['amount']:.0f}) · {path}", button_style="warning", icon="credit-card")
                    def _buy(_, path=path, name=b["name"]):
                        t = res.top_up(path, bundle=name)
                        res._hub._simulate_checkout_paid(t.invoice["id"])   # mock: the user pays + webhook fires
                        refresh()
                    btn.on_click(_buy)
                    btns.append(btn)
            else:                                          # Charge (MPP)
                btn = w.Button(description=f"Approve {path}", button_style="info", icon="check")
                btn.on_click(lambda _, path=path: (res.approve(path), refresh()))
                btns.append(btn)
            s = w.Button(description=f"Skip {path}", icon="forward")
            s.on_click(lambda _, path=path: (res.skip(path), refresh()))
            btns.append(s)
        if any(getattr(p, "invoice", None) for p in res.pending):
            r = w.Button(description="Paid, retry", button_style="success", icon="refresh")
            r.on_click(lambda _: (res.retry(), refresh()))
            btns.append(r)
        return btns

    refresh()
    return w.VBox([out, box])
