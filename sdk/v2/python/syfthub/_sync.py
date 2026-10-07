"""The synchronous face. In the real SDK this package is generated from the async one with ``unasync``
at build time. The mock stands it in with a proxy: every coroutine the async object returns is run on
a private event loop in a background thread, so it works in scripts, REPLs and notebooks alike."""
from __future__ import annotations

import asyncio
import enum
import inspect
import threading
from typing import Any

from pydantic import BaseModel


class _Loop:
    _instance: "_Loop | None" = None

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True, name="syfthub-sync").start()

    @classmethod
    def get(cls) -> "_Loop":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


def _is_sdk(obj: Any) -> bool:
    mod = type(obj).__module__ or ""
    return mod.startswith("syfthub.") and not isinstance(obj, (enum.Enum, BaseModel)) or (
        isinstance(obj, BaseModel) and any(inspect.iscoroutinefunction(getattr(type(obj), n, None))
                                          for n in ("top_up", "refresh", "wait_paid", "buy", "resume")))


def wrap(obj: Any) -> Any:
    if inspect.iscoroutine(obj):
        return wrap(_Loop.get().run(obj))
    if inspect.isasyncgen(obj):
        def gen():
            loop = _Loop.get()
            while True:
                try:
                    yield wrap(loop.run(obj.__anext__()))
                except StopAsyncIteration:
                    return
        return gen()
    if isinstance(obj, SyncProxy):
        return obj
    if _is_sdk(obj):
        return SyncProxy(obj)
    if isinstance(obj, list) and obj and _is_sdk(obj[0]) and type(obj) is list:
        return [wrap(x) for x in obj]
    if isinstance(obj, tuple) and obj and _is_sdk(obj[0]):
        return tuple(wrap(x) for x in obj)
    return obj


def unwrap(obj: Any) -> Any:
    if isinstance(obj, SyncProxy):
        return obj._target
    if isinstance(obj, (list, tuple)):
        return type(obj)(unwrap(x) for x in obj)
    return obj


class SyncProxy:
    """Wraps one async SDK object. Attribute access returns wrapped values; coroutines are awaited for you."""

    def __init__(self, target: Any) -> None:
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> Any:
        v = getattr(self._target, name)
        if callable(v) and not isinstance(v, type):
            def call(*a, **kw):
                return wrap(v(*[unwrap(x) for x in a], **{k: unwrap(x) for k, x in kw.items()}))
            call.__doc__ = v.__doc__
            return call
        return wrap(v)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._target, name, unwrap(value))

    def __getitem__(self, key):
        return wrap(self._target[unwrap(key)])

    def __iter__(self):
        return (wrap(x) for x in iter(self._target))

    def __len__(self) -> int:
        return len(self._target)

    def __add__(self, other):
        return wrap(self._target + unwrap(other))

    def __enter__(self):
        wrap(self._target.__aenter__())
        return self

    def __exit__(self, *exc):
        wrap(self._target.__aexit__(*exc))

    def __repr__(self) -> str:
        return repr(self._target)

    def _repr_html_(self) -> str:
        return self._target._repr_html_()

    def __dir__(self):
        return dir(self._target)


def Hub(*args: Any, **kwargs: Any) -> SyncProxy:
    """The synchronous ``AsyncHub``. Same methods, no ``await``; use ``with syfthub.Hub() as hub:``.

    Args:
        *args: As ``AsyncHub``.
        **kwargs: As ``AsyncHub``.

    Returns:
        A synchronous session."""
    from .hub import AsyncHub
    return SyncProxy(AsyncHub(*args, **kwargs))
