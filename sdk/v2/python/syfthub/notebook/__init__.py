"""Notebook skin: HTML cards and optional ipywidgets buttons. The core never imports this eagerly; the
models' ``_repr_html_`` hooks load ``render`` on first display."""
from . import render  # noqa: F401

__all__ = ["render"]
