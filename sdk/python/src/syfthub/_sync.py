"""``Hub``: the sync twin of ``AsyncHub``.

The async package is the source. ``Hub`` runs it on a private event loop in a background thread,
and every sync call blocks the caller until the coroutine finishes. So it also works where a loop
is already running (Jupyter, an ASGI handler), as long as the caller is not the loop's own thread.

Every object that comes out of a ``Hub`` is a ``Sync`` face over the async object: attribute reads
pass through, coroutine methods run on the loop, and ``isinstance`` and ``match`` see the real
type. ``Wallet.balance`` and friends still update in place.

Type checkers cannot see through the proxy, so ``_sync.pyi`` declares the sync faces. It is
generated from the async package by ``scripts/gen_sync_stub.py``; regenerate it after changing a
public coroutine method or anything it returns.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable, Coroutine, Iterator
from typing import Any, TypeVar

from .hub import AsyncHub, BudgetLike
from .models.base import Bound
from .models.session import Options

T = TypeVar("T")

_PASSTHROUGH_MODULES = frozenset(
    {"syfthub.models.money", "syfthub.models.enums", "syfthub.models.session"}
)


class _Loop:
    """One event loop on one daemon thread, started on demand and stopped on ``close``."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._serve, name="syfthub-sync", daemon=True)
        self._started = threading.Event()
        self.thread.start()
        self._started.wait()

    def _serve(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.call_soon(self._started.set)
        self.loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        if threading.current_thread() is self.thread:
            coro.close()
            raise RuntimeError(
                "syfthub.Hub was called from its own event-loop thread (a callback or a coroutine "
                "the SDK is running); use AsyncHub there"
            )
        if self.loop.is_closed():
            coro.close()
            raise RuntimeError("syfthub.Hub is closed")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def close(self) -> None:
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()
        self.loop.close()


Runner = Callable[[Coroutine[Any, Any, Any]], Any]


def _is_sdk(value: object) -> bool:
    module = getattr(type(value), "__module__", "")
    return isinstance(module, str) and (module == "syfthub" or module.startswith("syfthub."))


def _unwrap(value: Any) -> Any:
    if isinstance(value, Sync):
        return object.__getattribute__(value, "_target")
    if isinstance(value, tuple):
        return tuple(_unwrap(v) for v in value)
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def _wrap(value: Any, run: Runner) -> Any:
    if isinstance(value, Sync):
        return value
    if inspect.iscoroutinefunction(value):

        def blocking(*args: Any, **kwargs: Any) -> Any:
            return _wrap(run(value(*_unwrap(args), **_unwrap(kwargs))), run)

        blocking.__name__ = getattr(value, "__name__", "call")
        blocking.__doc__ = getattr(value, "__doc__", None)
        return blocking
    if callable(value) and not isinstance(value, type):

        def passthrough(*args: Any, **kwargs: Any) -> Any:
            return _wrap(value(*_unwrap(args), **_unwrap(kwargs)), run)

        passthrough.__name__ = getattr(value, "__name__", "call")
        passthrough.__doc__ = getattr(value, "__doc__", None)
        return passthrough
    if isinstance(value, tuple):
        return tuple(_wrap(v, run) for v in value)
    if isinstance(value, dict):
        return {k: _wrap(v, run) for k, v in value.items()}
    if _is_sdk(value) and type(value).__module__ not in _PASSTHROUGH_MODULES:
        return Sync(value, run)
    return value


class Sync:
    """The sync face of one SDK object. Reads pass through; coroutine methods block."""

    __slots__ = ("_target", "_run")

    def __init__(self, target: Any, run: Runner) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_run", run)

    @property  # type: ignore[misc]
    def __class__(self) -> type:  # isinstance() and match-case see the real type
        return type(object.__getattribute__(self, "_target"))

    def __getattr__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_target")
        return _wrap(getattr(target, name), object.__getattribute__(self, "_run"))

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_target"), name, _unwrap(value))

    def __dir__(self) -> list[str]:
        return dir(object.__getattribute__(self, "_target"))

    def __repr__(self) -> str:
        return repr(object.__getattribute__(self, "_target"))

    def __str__(self) -> str:
        return str(object.__getattribute__(self, "_target"))

    def __eq__(self, other: object) -> bool:
        return bool(object.__getattribute__(self, "_target") == _unwrap(other))

    def __hash__(self) -> int:
        return hash(object.__getattribute__(self, "_target"))

    def __bool__(self) -> bool:  # without this, truthiness falls through to __len__
        return bool(object.__getattribute__(self, "_target"))

    def __len__(self) -> int:
        return len(object.__getattribute__(self, "_target"))

    def __iter__(self) -> Iterator[Any]:
        run = object.__getattribute__(self, "_run")
        return (_wrap(v, run) for v in object.__getattribute__(self, "_target"))

    def __contains__(self, item: object) -> bool:
        return _unwrap(item) in object.__getattribute__(self, "_target")

    def __getitem__(self, key: Any) -> Any:
        target = object.__getattribute__(self, "_target")
        return _wrap(target[_unwrap(key)], object.__getattribute__(self, "_run"))

    def __add__(self, other: Any) -> Any:
        target = object.__getattribute__(self, "_target")
        return _wrap(target + _unwrap(other), object.__getattribute__(self, "_run"))


class Hub(Sync):
    """Sync twin of ``AsyncHub``: same names, no ``await``.

    The ``AsyncHub`` and its HTTP client are created on the private loop, and every call runs
    there. Use ``with Hub() as hub:`` or call ``close()`` to stop the loop.
    """

    __slots__ = ("_loop",)

    def __init__(
        self,
        url: str | None = None,
        *,
        token: str | None = None,
        budget: BudgetLike = None,
        options: Options | None = None,
    ) -> None:
        loop = _Loop()
        object.__setattr__(self, "_loop", loop)

        async def make() -> AsyncHub:
            return AsyncHub(url, token=token, budget=budget, options=options)

        try:
            target = loop.run(make())
        except BaseException:
            loop.close()
            raise
        super().__init__(target, loop.run)

    @property
    def async_hub(self) -> AsyncHub:
        """The ``AsyncHub`` underneath, for code that already runs on an event loop."""
        hub: AsyncHub = object.__getattribute__(self, "_target")
        return hub

    def load(self, cls: type[Bound], d: dict[str, Any]) -> Any:
        """``cls.from_dict(hub, d)`` with the sync face: ``hub.load(syfthub.SearchPlan, saved)``."""
        return _wrap(cls.from_dict(self.async_hub, d), object.__getattribute__(self, "_run"))

    def close(self) -> None:
        loop: _Loop = object.__getattribute__(self, "_loop")
        if loop.loop.is_closed():
            return
        try:
            loop.run(self.async_hub.aclose())
        finally:
            loop.close()

    def __enter__(self) -> Hub:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return repr(self.async_hub).replace("AsyncHub(", "Hub(", 1)
