"""SyftHub in-bwrap audit hook (defense in depth).

IMPORTANT: this file MUST NOT be named `sitecustomize.py`. Python's
`site` module auto-imports `sitecustomize` from any sys.path entry
(including PYTHONPATH-added dirs AND the running script's own dir).
That would cause the hook to fire in:
  - server.py (the in-container multiplexer) — would block its own
    subprocess.Popen call to bwrap
  - dpkg / apt-get python post-install scripts running under
    `docker build` RUN steps in the user's image
  - any other Python process that happens to have the runtime dir
    on its sys.path

Instead, syft_entry.py imports this module EXPLICITLY, AFTER the user's
runner.py has been loaded by importlib. That guarantees:
  - module-level import of the handler library tree runs un-audited
    (anthropic, openai SDKs etc. often open config files during
    `import` which would otherwise trip the audit hook)
  - handler() invocation runs under the full audit policy

Two layers protect the handler:

  1. KERNEL — bwrap's mount namespace contains /app/code (RO) and
     /app/workspace (RW); .env, policy/, setup.yaml, runner.py source
     edits are absent or read-only at the kernel level.

  2. PYTHON AUDIT (this file) — sys.addaudithook intercepts open(),
     os.open(), subprocess.Popen(), ctypes.dlopen(), os.exec*. It
     denies any access that does not match the allow-list. Bypassable
     only by raw C calls (which the kernel layer still blocks).

The hook is REGISTERED ONCE at startup and cannot be removed
(sys.addaudithook is monotone — PEP 578). Trying to add a counter-hook
that re-allows operations DOES NOT undo the deny — the deny runs first.
"""

from __future__ import annotations

import errno
import os
import sys

import _protocol as P  # noqa: E402  # sibling module on sys.path inside bwrap

# ─── Configuration ───────────────────────────────────────────────────

# Paths the handler may READ (and only read). Resolved via realpath to
# defeat ../ tricks. Order does not matter.
#
# /etc is allowed wholesale because the Python stdlib reads many files
# under it (nsswitch.conf, hosts, locale.alias, mime.types, …) and
# blocking them breaks ordinary library code. Sensitive content in /etc
# is owned by root and not in the user's endpoint dir, so it's not in
# the threat model we're defending against here.
_ALLOWED_READ_PREFIXES = (
    "/app/code",
    "/app/workspace",
    "/usr",
    "/lib",
    "/lib64",
    "/etc",
    "/dev/null",
    "/dev/random",
    "/dev/urandom",
    "/dev/zero",
    "/dev/tty",
    "/proc",
    "/sys",
    "/tmp",
    "/home",
    # site-packages live under sys.prefix (added below).
    sys.prefix,
    sys.exec_prefix,
)

# Paths the handler may WRITE.
_ALLOWED_WRITE_PREFIXES = (
    "/app/workspace",
    "/tmp",
    "/dev/null",
)

# File basenames that MUST NEVER be readable — belt-and-suspenders in
# case a misconfigured bwrap mount accidentally exposes them.
_DENIED_BASENAMES = frozenset({
    ".env",
    "setup.yaml",
    ".setup-state.json",
    "policies.yaml",
})

# Directory names whose contents must never be accessed (any segment).
_DENIED_DIR_SEGMENTS = frozenset({
    "policy",
    "policies",
})

# Whether the handler is allowed to spawn subprocesses. Set from the
# bwrap launcher via env var SYFT_ALLOW_SUBPROCESS=1.
_ALLOW_SUBPROCESS = os.environ.get(P.SYFT_ALLOW_SUBPROCESS) == "1"

# Telemetry — when SYFT_AUDIT_LOG is set, emit a line per denied event.
_AUDIT_LOG_FD = None
_audit_log_path = os.environ.get("SYFT_AUDIT_LOG")
if _audit_log_path:
    try:
        _AUDIT_LOG_FD = os.open(_audit_log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    except OSError:
        _AUDIT_LOG_FD = None


def _log_violation(event: str, path: str, reason: str) -> None:
    """Best-effort structured log of a denied event. Never raises."""
    if _AUDIT_LOG_FD is None:
        return
    import json
    try:
        line = json.dumps({
            "event": event,
            "path": path,
            "reason": reason,
            "pid": os.getpid(),
        }, separators=(",", ":")) + "\n"
        os.write(_AUDIT_LOG_FD, line.encode("utf-8", "replace"))
    except Exception:
        pass


def _normalize(path) -> str:
    """Best-effort realpath. Returns "" when normalization fails — caller
    treats that as deny."""
    try:
        p = os.fspath(path)
    except TypeError:
        return ""
    if not isinstance(p, str):
        try:
            p = p.decode("utf-8", "surrogateescape")
        except Exception:
            return ""
    try:
        # realpath resolves .., symlinks, redundant slashes. Even if the
        # file doesn't exist yet, realpath returns the would-be path.
        return os.path.realpath(p)
    except (OSError, ValueError):
        return ""


def _has_denied_segment(p: str) -> bool:
    """True iff any path segment names a denied dir or basename."""
    parts = p.split(os.sep)
    base = parts[-1] if parts else ""
    if base in _DENIED_BASENAMES:
        return True
    for seg in parts:
        if seg in _DENIED_DIR_SEGMENTS:
            return True
    return False


def _allowed_for_read(path: str) -> bool:
    if not path:
        return False
    if _has_denied_segment(path):
        return False
    for pref in _ALLOWED_READ_PREFIXES:
        if not pref:
            continue
        if path == pref or path.startswith(pref + os.sep):
            return True
    return False


def _allowed_for_write(path: str) -> bool:
    if not path:
        return False
    if _has_denied_segment(path):
        return False
    for pref in _ALLOWED_WRITE_PREFIXES:
        if path == pref or path.startswith(pref + os.sep):
            return True
    return False


def _open_is_write(mode_or_flags) -> bool:
    """Decide if an `open` / `os.open` arg-list represents a write."""
    if isinstance(mode_or_flags, str):
        # Any of w/a/x means write; '+' upgrades r-modes to read-write.
        return any(c in mode_or_flags for c in "wax+")
    try:
        flags = int(mode_or_flags)
    except (TypeError, ValueError):
        return False
    return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))


def _audit(event: str, args: tuple) -> None:
    """sys.addaudithook callback. Raises PermissionError on deny."""
    # Filesystem reads / writes
    if event == "open":
        # args == (path, mode, flags). path can be:
        #   - str/bytes/PathLike: the usual case → resolve and gate.
        #   - int: a file descriptor; open(fd) wraps an EXISTING fd in
        #     a Python file object. No new file access happens — the
        #     fd was opened via a previous syscall that the hook
        #     already had its chance to gate. Skipping here is correct
        #     AND necessary; subprocess pipe IO, asyncio internals,
        #     and stdlib code commonly hit this path.
        if len(args) < 1:
            return
        path_arg = args[0]
        if isinstance(path_arg, int):
            return
        mode = args[1] if len(args) > 1 else ""
        flags = args[2] if len(args) > 2 else 0
        is_write = _open_is_write(mode) or _open_is_write(flags)
        norm = _normalize(path_arg)
        ok = _allowed_for_write(norm) if is_write else _allowed_for_read(norm)
        if not ok:
            _log_violation("open", str(path_arg), "write" if is_write else "read")
            raise PermissionError(errno.EACCES, "syft-sandbox: access denied", str(path_arg))
        return

    if event == "os.open":
        # args == (path, flags, mode). os.open is documented to take a
        # path, but defensively skip ints just like the open event.
        if len(args) < 2:
            return
        path_arg = args[0]
        if isinstance(path_arg, int):
            return
        flags = args[1]
        is_write = _open_is_write(flags)
        norm = _normalize(path_arg)
        ok = _allowed_for_write(norm) if is_write else _allowed_for_read(norm)
        if not ok:
            _log_violation("os.open", str(path_arg), "write" if is_write else "read")
            raise PermissionError(errno.EACCES, "syft-sandbox: access denied", str(path_arg))
        return

    # Subprocess / exec — deny unless explicitly enabled.
    if not _ALLOW_SUBPROCESS:
        if event in ("subprocess.Popen", "os.exec", "os.posix_spawn", "os.posix_spawnp"):
            _log_violation(event, str(args), "subprocess denied")
            raise PermissionError(errno.EACCES, "syft-sandbox: subprocess denied")
        if event == "os.system":
            _log_violation("os.system", str(args), "shell denied")
            raise PermissionError(errno.EACCES, "syft-sandbox: shell denied")

    # ctypes bypass — block dynamic library loading.
    if event in ("ctypes.dlopen", "ctypes.PyDLL", "ctypes.cdll.LoadLibrary"):
        # Allow internal Python-bundled libs (e.g., _ssl.so import chain) —
        # those don't fire ctypes.dlopen; only explicit user ctypes calls do.
        path_str = str(args[0]) if args else ""
        norm = _normalize(path_str) if path_str else ""
        if norm and (norm.startswith(sys.prefix) or norm.startswith(sys.exec_prefix)):
            return
        _log_violation(event, path_str, "ctypes denied")
        raise PermissionError(errno.EACCES, "syft-sandbox: ctypes denied")

    # Privilege ops — should already be blocked by capability dropping,
    # but cheap to also fail at this level.
    if event in ("os.setuid", "os.setgid", "os.setresuid", "os.setresgid"):
        _log_violation(event, str(args), "privilege op denied")
        raise PermissionError(errno.EACCES, "syft-sandbox: privilege op denied")


# Register only once. PEP 578 ensures the hook cannot be removed once added.
# Guard against double-registration if sitecustomize is imported twice for
# any reason (it shouldn't be, but cheap insurance).
if not getattr(sys, "_syft_audit_hook_installed", False):
    sys.addaudithook(_audit)
    sys._syft_audit_hook_installed = True  # type: ignore[attr-defined]


# ─── subprocess env inheritance ───────────────────────────────────────
#
# Subprocesses the handler spawns (claude-code, ffmpeg, git, …) inherit
# runner.py's FULL environment by default — standard Python behavior, no
# filtering. This is safe because no real secret lives in the container
# env: the egress broker keeps LLM credentials on the host and injects
# only sentinels/redacted values into the container (see provider.go and
# egressbroker/). There is therefore nothing to strip from a child's env.
#
# The read/write/subprocess audit hook above remains the security
# boundary (filesystem isolation, .env/policy denial, ctypes/privilege
# blocks); environment confidentiality is owned by the broker, not by a
# Popen monkey-patch.
