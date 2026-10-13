#!/usr/bin/env python3
"""Generate the typed face of the sync ``Hub``.

``syfthub.Hub`` is a runtime proxy over ``AsyncHub``: attribute reads go through ``__getattr__``
and coroutine methods block on a private loop. A type checker sees ``Any`` through it. This script
reads the async package and writes two files that give the sync side the same types:

* ``src/syfthub/_sync.pyi``: for every class a ``Hub`` can hand out that has a coroutine method,
  or carries an object that has one, a subclass of the real class whose coroutine methods are
  declared as plain calls returning what the proxy returns. Fields and non-coroutine methods are
  inherited; only what changes is redeclared. ``Hub`` itself is declared in full.
* ``src/syfthub/sync.py``: the public names for annotating sync code. At runtime they are the real
  classes, because a proxied object answers to its real type; under a type checker they are the
  faces from the stub.

Run ``uv run python scripts/gen_sync_stub.py`` after changing the async surface.
``tests/unit/test_sync_stub.py`` fails until the files on disk match.
"""

from __future__ import annotations

import collections.abc
import inspect
import subprocess
import sys
import types
import typing
from pathlib import Path
from typing import Any, ForwardRef, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict
from pydantic_core import PydanticUndefined

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import syfthub  # noqa: E402
import syfthub.auth  # noqa: E402
import syfthub.models  # noqa: E402
import syfthub.sources  # noqa: E402
import syfthub.wallets  # noqa: E402
from syfthub._sync import _PASSTHROUGH_MODULES  # noqa: E402
from syfthub.hub import AsyncHub  # noqa: E402
from syfthub.models.base import Bound  # noqa: E402

# Types the proxy hands back untouched; the stub names them by their real module.
PASSTHROUGH = set(_PASSTHROUGH_MODULES) | {"syfthub.errors", "syfthub.models.base"}
# Dunders the proxy delegates and a twin may need to retype.
DUNDERS = ("__iter__", "__len__", "__getitem__", "__contains__", "__add__")
# AsyncHub members the sync Hub does not present: the async lifecycle and the internal ports
# the models call back through.
HUB_SKIP = {
    "aclose",
    "preflight",
    "execute",
    "wallet_balance",
    "wallet_top_up",
    "wallet_invoices",
    "invoice_refresh",
}
# Names that modules import only under TYPE_CHECKING still have to resolve.
NAMES: dict[str, Any] = {
    **{k: v for k, v in vars(syfthub.models).items() if not k.startswith("_")},
    **{k: v for k, v in vars(syfthub).items() if not k.startswith("_")},
    "AsyncHub": AsyncHub,
    "AuthNamespace": syfthub.auth.AuthNamespace,
    "SourcesNamespace": syfthub.sources.SourcesNamespace,
    "WalletsNamespace": syfthub.wallets.WalletsNamespace,
}

Kind = Literal["field", "property", "method", "classmethod", "staticmethod"]


class Member(BaseModel):
    """One public member of a class: a field, a property or a callable."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    kind: Kind
    coroutine: bool = False
    has_default: bool = False
    annotation: Any = None  # fields and properties: the output type
    signature: inspect.Signature | None = None  # callables

    @property
    def output(self) -> Any:
        if self.signature is not None:
            return self.signature.return_annotation
        return self.annotation


def is_sdk(t: Any) -> bool:
    return isinstance(t, type) and t.__module__.startswith("syfthub")


def is_wrapped(t: Any) -> bool:
    """A class the proxy puts a ``Sync`` face on."""
    return is_sdk(t) and t.__module__ not in PASSTHROUGH


def classes_in(t: Any) -> set[type]:
    """Wrapped SDK classes mentioned anywhere in a type expression."""
    if isinstance(t, type):
        return {t} if is_wrapped(t) else set()
    found: set[type] = set()
    for arg in get_args(t):
        found |= classes_in(arg)
    return found


def defining_class(cls: type, name: str) -> type | None:
    for base in cls.__mro__:
        if name in vars(base):
            return base
    return None


def surface(cls: type) -> list[Member]:
    """The public members of ``cls`` that the SDK defines, inherited ones included."""
    members: list[Member] = []
    fields = getattr(cls, "model_fields", None)
    if fields:
        for name, info in fields.items():
            if name.startswith("_"):
                continue
            has_default = info.default is not PydanticUndefined or info.default_factory is not None
            members.append(
                Member(name=name, kind="field", annotation=info.annotation, has_default=has_default)
            )
    else:
        for name, annotation in typing.get_type_hints(cls, localns=NAMES).items():
            if not name.startswith("_"):
                members.append(Member(name=name, kind="field", annotation=annotation))
    for name in sorted(dir(cls)):
        if name.startswith("_") and name not in DUNDERS:
            continue
        owner = defining_class(cls, name)
        if owner is None or not owner.__module__.startswith("syfthub"):
            continue
        raw = vars(owner)[name]
        if isinstance(raw, property) and raw.fget is not None:
            hints = typing.get_type_hints(raw.fget, localns=NAMES)
            members.append(Member(name=name, kind="property", annotation=hints.get("return", Any)))
            continue
        kind: Kind
        if isinstance(raw, classmethod):
            fn, kind = raw.__func__, "classmethod"
        elif isinstance(raw, staticmethod):
            fn, kind = raw.__func__, "staticmethod"
        elif inspect.isfunction(raw):
            fn, kind = raw, "method"
        else:
            continue
        if not fn.__module__.startswith("syfthub"):
            continue  # pydantic plants helpers such as model_post_init on each model class
        signature = inspect.signature(fn, eval_str=True, locals=NAMES)
        members.append(
            Member(
                name=name,
                kind=kind,
                coroutine=inspect.iscoroutinefunction(fn),
                signature=signature,
            )
        )
    return members


def mentions(t: Any, classes: set[type]) -> bool:
    return bool(classes_in(t) & classes)


def reachable_from(root: type) -> list[type]:
    """Wrapped classes reachable from ``root`` through member types, in discovery order."""
    seen: list[type] = []
    queue = [root]
    while queue:
        cls = queue.pop(0)
        for member in surface(cls):
            found = classes_in(member.output)
            if member.signature is not None:
                for p in member.signature.parameters.values():
                    found |= classes_in(p.annotation)
            for c in sorted(found, key=lambda c: c.__qualname__):
                if c is not root and c not in seen:
                    seen.append(c)
                    queue.append(c)
    return seen


def twins_among(classes: list[type]) -> list[type]:
    """Classes that need a sync face: a coroutine method of their own, or an output that carries
    one. Computed to a fixed point."""
    surfaces = {c: surface(c) for c in classes}
    twins = {c for c, members in surfaces.items() if any(m.coroutine for m in members)}
    while True:
        more = {
            c
            for c, members in surfaces.items()
            if c not in twins and any(mentions(m.output, twins) for m in members)
        }
        if not more:
            break
        twins |= more
    names = [c.__name__ for c in classes if c in twins]
    assert len(names) == len(set(names)), f"twin names collide: {names}"
    return [c for c in classes if c in twins]


class Renderer(BaseModel):
    """Turns type objects into stub text, collecting the modules the text needs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    twins: set[type]
    imports: set[str] = set()
    typing_names: set[str] = set()

    def qualified(self, t: type) -> str:
        if t.__module__ == "builtins":
            return t.__qualname__
        self.imports.add(t.__module__)
        return f"{t.__module__}.{t.__qualname__}"

    def render(self, t: Any, *, out: bool) -> str:
        """``out`` names twins by their face; inputs name the real class, which the face extends,
        so a sync face passes wherever the async class is accepted."""
        if t is inspect.Signature.empty or t is inspect.Parameter.empty or t is Any:
            self.typing_names.add("Any")
            return "Any"
        if t is None or t is type(None):
            return "None"
        if t is Ellipsis:
            return "..."
        if isinstance(t, typing.TypeVar):
            self.typing_names.add("Any")
            return "Any"
        if isinstance(t, ForwardRef):
            return self.render(eval(t.__forward_arg__, NAMES), out=out)
        if isinstance(t, str):
            return self.render(eval(t, NAMES), out=out)
        origin, args = get_origin(t), get_args(t)
        if origin is typing.Union or isinstance(t, types.UnionType):
            return " | ".join(self.render(a, out=out) for a in args)
        if origin is Literal:
            self.typing_names.add("Literal")
            return "Literal[" + ", ".join(repr(a) for a in args) + "]"
        if origin is collections.abc.Callable:
            self.imports.add("collections.abc")
            params, ret = args
            inner = (
                "..."
                if params is Ellipsis
                else "[" + ", ".join(self.render(p, out=out) for p in params) + "]"
            )
            return f"collections.abc.Callable[{inner}, {self.render(ret, out=out)}]"
        if origin is not None:
            return f"{self.qualified(origin)}[{', '.join(self.render(a, out=out) for a in args)}]"
        if isinstance(t, type):
            if out and t in self.twins:
                return t.__name__
            return self.qualified(t)
        raise TypeError(f"cannot render {t!r}")

    def params(self, signature: inspect.Signature, *, skip_first: bool) -> str:
        parts: list[str] = []
        params = list(signature.parameters.values())
        if skip_first:
            params = params[1:]
        star_seen = False
        for i, p in enumerate(params):
            if p.kind is inspect.Parameter.KEYWORD_ONLY and not star_seen:
                parts.append("*")
                star_seen = True
            if p.kind is inspect.Parameter.VAR_POSITIONAL:
                star_seen = True
                text = f"*{p.name}"
            elif p.kind is inspect.Parameter.VAR_KEYWORD:
                text = f"**{p.name}"
            else:
                text = p.name
            if p.annotation is not inspect.Parameter.empty:
                text += f": {self.render(p.annotation, out=False)}"
            if p.default is not inspect.Parameter.empty:
                text += " = ..."
            parts.append(text)
            if p.kind is inspect.Parameter.POSITIONAL_ONLY and (
                i + 1 == len(params) or params[i + 1].kind is not inspect.Parameter.POSITIONAL_ONLY
            ):
                parts.append("/")
        return ", ".join(parts)

    def member(self, m: Member) -> list[str]:
        if m.kind == "field":
            default = " = ..." if m.has_default else ""
            return [f"    {m.name}: {self.render(m.annotation, out=True)}{default}"]
        if m.kind == "property":
            return [
                "    @property",
                f"    def {m.name}(self) -> {self.render(m.annotation, out=True)}: ...",
            ]
        assert m.signature is not None
        lines: list[str] = []
        first = {"method": "self", "classmethod": "cls", "staticmethod": None}[m.kind]
        if m.kind != "method":
            lines.append(f"    @{m.kind}")
        params = self.params(m.signature, skip_first=first is not None)
        joined = ", ".join(p for p in (first, params) if p)
        ret = self.render(m.signature.return_annotation, out=True)
        lines.append(f"    def {m.name}({joined}) -> {ret}: ...")
        return lines


def render_twin(cls: type, r: Renderer) -> list[str]:
    """A subclass of the real class redeclaring only what the proxy changes."""
    lines = [f"class {cls.__name__}({r.qualified(cls)}):"]
    body: list[str] = []
    for m in surface(cls):
        if m.coroutine or mentions(m.output, r.twins):
            body += r.member(m)
    lines += body or ["    ..."]
    return lines


def render_hub(r: Renderer, twins: list[type]) -> list[str]:
    init = inspect.signature(AsyncHub.__init__, eval_str=True, locals=NAMES)
    lines = [
        "class Hub:",
        f"    def __init__(self, {r.params(init, skip_first=True)}) -> None: ...",
    ]
    for m in surface(AsyncHub):
        if m.name not in HUB_SKIP:
            lines += r.member(m)
    lines += ["    @property", f"    def async_hub(self) -> {r.qualified(AsyncHub)}: ..."]
    r.typing_names.add("overload")
    r.typing_names.add("Any")
    for cls in twins:
        if issubclass(cls, Bound):
            lines += [
                "    @overload",
                f"    def load(self, cls: type[{r.qualified(cls)}], d: dict[str, Any]) -> {cls.__name__}: ...",
            ]
    lines += [
        "    @overload",
        f"    def load(self, cls: type[{r.qualified(Bound)}], d: dict[str, Any]) -> Any: ...",
        "    def close(self) -> None: ...",
        "    def __enter__(self) -> Hub: ...",
        "    def __exit__(self, *exc: object) -> None: ...",
        "    def __repr__(self) -> str: ...",
    ]
    return lines


HEADER = f"# Generated by scripts/{Path(__file__).name}; do not edit. See the note in _sync.py."
# Every override in the stub is the point of the stub: a coroutine declared as a plain call, or a
# field narrowed to a sync face. Say so once instead of on every line.
STUB_PRAGMA = '# mypy: disable-error-code="override"'


def stub_text(twins: list[type]) -> str:
    r = Renderer(twins=set(twins))
    classes = [render_twin(cls, r) for cls in twins]
    hub = render_hub(r, twins)
    sync_cls = [
        "class Sync:",
        "    def __init__(self, target: Any, run: Any) -> None: ...",
    ]
    r.typing_names.add("Any")
    imports = [f"import {m}" for m in sorted(r.imports)]
    imports.append(f"from typing import {', '.join(sorted(r.typing_names))}")
    blocks = [HEADER + "\n" + STUB_PRAGMA, "\n".join(imports), "\n".join(sync_cls)]
    blocks += ["\n".join(c) for c in classes]
    blocks.append("\n".join(hub))
    return "\n\n".join(blocks) + "\n"


def sync_module_text(twins: list[type]) -> str:
    by_module: dict[str, list[str]] = {}
    for cls in twins:
        by_module.setdefault(cls.__module__.removeprefix("syfthub"), []).append(cls.__name__)
    names = sorted(c.__name__ for c in twins)
    runtime = "\n".join(
        f"    from {mod} import {', '.join(sorted(ns))}" for mod, ns in sorted(by_module.items())
    )
    exported = ", ".join(f'"{n}"' for n in ["Hub", *names])
    return f'''"""Names for annotating code that uses the sync ``Hub``.

{HEADER.removeprefix("# ")}

    from syfthub import sync

    def review(pre: sync.Preflight) -> sync.SearchPlan: ...

At runtime every name here is the real class, because an object that comes out of a ``Hub``
answers to its real type. Under a type checker the names are the sync faces declared in
``_sync.pyi``: the same classes with their coroutine methods declared as plain calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._sync import Hub

if TYPE_CHECKING:
    from ._sync import {", ".join(names)}
else:
{runtime}

__all__ = [{exported}]
'''


def ruff_format(text: str, filename: str) -> str:
    """Import order and formatting as the repo's ruff config wants them, so the generated text is
    what pre-commit would leave behind."""
    for args in (["check", "--fix", "--select", "I", "--quiet"], ["format"]):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", *args, "--stdin-filename", filename, "-"],
            input=text,
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        )
        text = result.stdout
    return text


def generate() -> dict[str, str]:
    """``{relative path: content}`` for the two generated files."""
    twins = twins_among(reachable_from(AsyncHub))
    return {
        "src/syfthub/_sync.pyi": ruff_format(stub_text(twins), "_sync.pyi"),
        "src/syfthub/sync.py": ruff_format(sync_module_text(twins), "sync.py"),
    }


def main() -> None:
    for rel, text in generate().items():
        path = ROOT / rel
        changed = not path.exists() or path.read_text() != text
        path.write_text(text)
        print(f"{'wrote' if changed else 'unchanged'} {rel}")


if __name__ == "__main__":
    main()
