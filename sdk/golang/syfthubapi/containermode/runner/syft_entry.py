"""In-bwrap entrypoint that loads the user's runner.py and dispatches.

Runs inside the bwrap sandbox. The audit hook is NOT auto-imported via
sitecustomize.py (that name is reserved and would make the hook also
fire in server.py and during docker-build RUN steps). Instead, this
script imports _syft_audit EXPLICITLY, between loading the user's
runner.py module (which is allowed to do un-audited library imports at
module level) and invoking handler() (which runs under the full audit
policy).

The first stdin line tells us what kind of invocation this is:

    {"type": "model", "messages": [...], "context": {...},
     "_sealed_code": {"runner.py": "...", ...}}
    {"type": "data_source", "query": "...", "context": {...},
     "_sealed_code": {...}}
    {"type": "session_start", "session_id": "...", "prompt": "...",
     "messages": [...], "config": {...}, "attachments_dir": "...",
     "_sealed_code": {...}}

For model / data_source: read one JSON frame, dispatch to handler,
write one JSON result frame to stdout, exit.

For session_start: instantiate AgentSession (which spawns its own stdin
reader thread for subsequent frames), call handler(session). On
return, write a session.completed or session.failed event and exit.

The _sealed_code field is the runtime mechanism that hides runner.py
from the bwrap filesystem. server.py reads every .py file in the synth
dir and ships them as {relative_path: source_text}; this entrypoint
compiles each source in-memory and registers the resulting module in
sys.modules BEFORE invoking the handler. Subsequent `import runner`
finds the cached module without touching the filesystem — so
subprocesses launched by the handler (e.g. claude-code's shell tool)
that try to `cat /app/code/runner.py` see ENOENT, even though the user
prompted them to read the file.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import os
import sys
import traceback
from typing import Any

import _protocol as P  # sibling module on sys.path inside bwrap


CODE_DIR = os.environ.get(P.SYFT_CODE_DIR, "/app/code")


def _write_frame(frame: dict) -> None:
    """Write a single JSON-line frame to stdout and flush."""
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()


def _module_name_from_rel_path(rel: str) -> str:
    """Convert a synth-dir-relative path into a Python module name.

    Examples:
        "runner.py"               → "runner"
        "helpers/parser.py"       → "helpers.parser"
        "pyproject.toml"          → ""  (not a module; caller skips)
    """
    if not rel.endswith(".py"):
        return ""
    rel_no_ext = rel[:-3]
    if rel_no_ext.endswith("/__init__"):
        rel_no_ext = rel_no_ext[: -len("/__init__")]
    return rel_no_ext.replace("/", ".")


def _register_sealed_modules(sealed: dict) -> None:
    """Compile each sealed-code entry and register it in sys.modules.

    The synthetic __file__ for each module is /app/code/<rel> so that
    user code that uses __file__ for path resolution still resolves to
    declared resources (which ARE bound at /app/code/<name>/...). The
    file itself does NOT exist on disk — `open(__file__)` from the
    handler returns ENOENT, which is the intended behavior."""
    # Register parent packages first so child modules can resolve their
    # ancestry on import. Sort by depth to ensure that order.
    rels = sorted(sealed.keys(), key=lambda p: (p.count("/"), p))
    for rel in rels:
        mod_name = _module_name_from_rel_path(rel)
        if not mod_name:
            continue
        source = sealed[rel]
        synthetic_file = os.path.join(CODE_DIR, rel)
        spec = importlib.util.spec_from_loader(
            mod_name, loader=None, origin=synthetic_file,
        )
        if spec is None:
            raise RuntimeError(
                f"sealed-code: failed to build spec for {mod_name}")
        module = importlib.util.module_from_spec(spec)
        module.__file__ = synthetic_file
        # For packages (__init__.py), set __path__ so submodule imports
        # work via the standard mechanism.
        if rel.endswith("/__init__.py") or rel == "__init__.py":
            pkg_rel = rel[: -len("/__init__.py")] if "/" in rel else ""
            module.__path__ = [os.path.join(CODE_DIR, pkg_rel)]
        try:
            compiled = compile(source, synthetic_file, "exec")
        except SyntaxError as e:
            raise RuntimeError(
                f"sealed-code: syntax error in {rel}: {e}") from e
        sys.modules[mod_name] = module
        try:
            exec(compiled, module.__dict__)
        except Exception:
            # Module init failed; remove the half-built entry so a
            # later import attempt doesn't see a broken module.
            sys.modules.pop(mod_name, None)
            raise


def _resolve_handler() -> Any:
    """Return the handler callable from the pre-registered runner module."""
    runner = sys.modules.get("runner")
    if runner is None:
        raise RuntimeError(
            "sealed-code: 'runner' module not registered "
            "(synth dir missing runner.py or sealed-code payload empty)")
    if not hasattr(runner, "handler"):
        raise AttributeError("runner.py must define a `handler` function")
    return runner.handler


def _call_one_shot(handler, frame: dict) -> Any:
    """Call handler() with the right signature for the endpoint type.

    Arity-aware to match the filemode legacy wrapper: prefer
    handler(messages, context) / handler(query, context) when defined
    with two args, fall back to single-arg form otherwise."""
    endpoint_type = frame.get("type", "model")
    context = frame.get("context", {}) or {}
    # Some clients nest the user-visible portion under "metadata".
    if isinstance(context, dict) and "metadata" in context:
        context = context["metadata"]

    try:
        sig = inspect.signature(handler)
        params = len(sig.parameters)
    except (ValueError, TypeError):
        params = -1

    if endpoint_type == "data_source":
        query = frame.get("query", "")
        return handler(query, context) if params >= 2 else handler(query)

    if endpoint_type == "model":
        messages = frame.get("messages", [])
        return handler(messages, context) if params >= 2 else handler(messages)

    # Unknown type — pass the full frame through.
    return handler(frame)


def _run_one_shot(handler, frame: dict) -> None:
    """Execute a model/data_source request, emit a single-line JSON
    response, exit 0 regardless of handler outcome."""
    try:
        result = _call_one_shot(handler, frame)
        if asyncio.iscoroutine(result):
            result = asyncio.run(result)
        _write_frame({"success": True, "result": result})
    except Exception as e:
        _write_frame({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        })


def _run_session(handler, frame: dict) -> None:
    """Long-lived agent session: hand control to runner.handler(session)
    and emit terminal session.completed/session.failed on return."""
    from session_loop import AgentSession

    session = AgentSession(frame)
    try:
        result = handler(session)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
        _emit_terminal("session.completed", {"session_id": session.id})
    except KeyboardInterrupt:
        # Cancellation arrived via {type: cancel} on stdin.
        _emit_terminal("session.cancelled", {"session_id": session.id})
    except Exception as e:
        _emit_terminal("session.failed", {
            "session_id": session.id,
            "error": str(e),
            "reason": "handler_error",
            "traceback": traceback.format_exc(),
        })


def _emit_terminal(event_type: str, data: dict) -> None:
    """Write a single terminal-event JSON frame and flush."""
    _write_frame({"type": event_type, "data": data})


def main() -> int:
    # First line determines mode AND carries the sealed-code payload.
    first = sys.stdin.readline()
    if not first:
        return 1
    try:
        frame = json.loads(first)
    except Exception as e:
        sys.stderr.write(f"syft_entry: invalid first frame: {e}\n")
        return 1

    # Pre-register sealed modules (runner + helpers) in sys.modules so
    # that the user's import statements resolve without filesystem
    # access. The payload is consumed once; remove it from the frame so
    # downstream code doesn't see it (and so the handler's
    # `messages`/`context` shape is unaffected for model invocations).
    sealed = frame.pop("_sealed_code", None) or {}
    try:
        if sealed:
            _register_sealed_modules(sealed)
        handler = _resolve_handler()
    except Exception as e:
        if frame.get("type") == "session_start":
            _emit_terminal("session.failed", {
                "session_id": frame.get("session_id", ""),
                "error": str(e),
                "reason": "handler_load_failed",
                "traceback": traceback.format_exc(),
            })
        else:
            _write_frame({
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            })
        return 1

    # Activate the audit hook AFTER the user's library tree has finished
    # module-level imports. Doing this earlier would block legitimate
    # library config-file reads at import time (anthropic SDK, httpx,
    # certifi, ...). Importing this module is what registers the hook
    # via sys.addaudithook(); once installed it cannot be removed.
    try:
        import _syft_audit  # noqa: F401 — side-effect import
    except Exception as e:  # pragma: no cover — runtime invariant
        sys.stderr.write(f"syft_entry: audit hook failed to load: {e}\n")
        return 1

    if frame.get("type") == "session_start":
        _run_session(handler, frame)
    else:
        _run_one_shot(handler, frame)
    return 0


if __name__ == "__main__":
    sys.exit(main())
