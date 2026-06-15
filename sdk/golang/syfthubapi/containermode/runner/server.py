"""SyftHub container runtime — in-container HTTP multiplexer.

This is the trusted-in-container component. It runs as the entrypoint of
the container, reads requests on :8080, and spawns a fresh bwrap child
per request (one-shot) or per session (agent) to actually execute the
handler. server.py NEVER imports the user's runner.py — handler code only
ever runs inside the bwrap-isolated child.

External API (unchanged from previous server.py; the host-side Go layer
in containermode/executor.go and containermode/agent_handler.go still
speaks the same JSON/SSE protocol):

    GET  /health                       → {"status": "ok"}
    POST /execute                      → JSON in/out for model/data_source
    POST /session/start                → start an agent session
    GET  /session/{id}/events          → SSE event stream
    POST /session/{id}/message         → deliver a user message
    POST /session/{id}/attachment      → deliver an inbound attachment
    DELETE /session/{id}               → cancel a session

Inside each request, server.py builds a bwrap argv and shells out to
the bwrap binary. Stdin / stdout JSON-lines is the IPC with the child.

Environment input from the host (set in the container spec):
    _SYFT_HANDLER_ENV   comma-separated allowlist of env var names the
                        handler may read; everything else is scrubbed
                        before invoking the bwrap child.
    SYFT_SANDBOX_NET    "open" (default), "allowlist", or "none"; sets
                        bwrap's --unshare-net flag.
    SYFT_WORKSPACE_SCOPE  "shared" | "per_user" | "per_session"
    SYFT_EGRESS_PORT / SYFT_EGRESS_SOCK
                        start the keyless egress relay (see below).
"""

from __future__ import annotations

import base64
import functools
import hashlib
import json
import logging
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

import _protocol as P  # noqa: E402  # sibling module — runtime cwd adds this dir to sys.path


# ─── Layout (kept in sync with sandbox.go on the host) ────────────────

SYNTH_DIR_HOST_MOUNT = "/app/synth"     # bound RO by the container
WORKSPACE_POOL_MOUNT = "/app/ws"        # bound RW by the container
AUDIT_HOOK_PATH = "/usr/local/lib/syft_runtime/_syft_audit.py"
ENTRY_PATH = "/usr/local/lib/syft_runtime/syft_entry.py"
SESSION_LOOP_PATH = "/usr/local/lib/syft_runtime/session_loop.py"
BWRAP = "/usr/bin/bwrap"

# Inside-bwrap target paths (what the handler sees).
GUEST_CODE_DIR = P.GUEST_CODE_DIR
GUEST_WORKSPACE_DIR = P.GUEST_WORKSPACE_DIR
GUEST_RUNTIME_DIR = "/usr/local/lib/syft_runtime"

# Maximum handler runtime for one-shot requests, in seconds. Agent
# sessions have no hard cap server-side (the host bridge enforces).
DEFAULT_ONESHOT_TIMEOUT = 120


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("syft_runtime.server")


# Resolve the container user's home dir. The base image creates `runner`
# with home /home/runner; custom Dockerfiles may follow the same
# convention. We bind this dir into the bwrap child so apps that look in
# $HOME (like claude-code reading ~/.claude/credentials.json) can find
# the files the user mounted via frontmatter container.mounts.
def _runtime_home_dir() -> str:
    try:
        import pwd
        home = pwd.getpwuid(os.getuid()).pw_dir
        if home and os.path.isdir(home):
            return home
    except Exception:
        pass
    # Fallback: env HOME if set and exists, else the canonical path.
    env_home = os.environ.get("HOME", "")
    if env_home and os.path.isdir(env_home):
        return env_home
    return "/home/runner"


HOST_HOME_DIR = _runtime_home_dir()


# ─── env-var allowlist passed via the container env ───────────────────

_HANDLER_ENV_KEYS = [
    k.strip() for k in os.environ.get(P.SYFT_HANDLER_ENV, "").split(",")
    if k.strip()
]


def _handler_env() -> dict:
    """Build the env dict passed to bwrap children: a minimal default
    plus only the keys in _HANDLER_ENV_KEYS (whose values come from the
    container's env, which the host set from the endpoint's .env)."""
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        # HOME points at the container user's home (where claude-code
        # etc. look for ~/.config and ~/.<app>/credentials). The dir is
        # bind-mounted into the bwrap child so files placed there by
        # the user's Dockerfile / container.mounts are reachable.
        # SYFT_WORKSPACE_DIR remains the canonical place to write
        # per-session scratch data.
        "HOME": HOST_HOME_DIR,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": GUEST_RUNTIME_DIR,
        P.SYFT_CODE_DIR: GUEST_CODE_DIR,
        P.SYFT_WORKSPACE_DIR: GUEST_WORKSPACE_DIR,
        # Subprocesses are always permitted — agent runners routinely shell
        # out (e.g. the claude-code CLI); isolation comes from bwrap, not
        # from blocking exec.
        P.SYFT_ALLOW_SUBPROCESS: "1",
    }
    for k in _HANDLER_ENV_KEYS:
        v = os.environ.get(k)
        if v is not None:
            base[k] = v
    return base


# ─── workspace scope resolution ───────────────────────────────────────

_SAFE_RE = re.compile(r"[^A-Za-z0-9_\-]")


def _safe_segment(s: str, fallback: str = "anon") -> str:
    """Sanitize a username/session-id for use as a filesystem segment."""
    if not s:
        return fallback
    out = _SAFE_RE.sub("_", s)
    return out[:128] if len(out) > 128 else out


def _workspace_for(scope: str, session_id: str = "", user_sub: str = "") -> str:
    """Return the host-side path that should be bound RW at /app/workspace.

    scope ∈ {shared, per_user, per_session}. The directory is created on
    demand."""
    if scope == "per_user":
        sub = _safe_segment(user_sub, "anon")
        path = os.path.join(WORKSPACE_POOL_MOUNT, "users", sub)
    elif scope == "per_session":
        sub = _safe_segment(session_id, uuid.uuid4().hex)
        path = os.path.join(WORKSPACE_POOL_MOUNT, "sessions", sub)
    else:  # shared (default)
        path = os.path.join(WORKSPACE_POOL_MOUNT, "shared")
    os.makedirs(path, mode=0o755, exist_ok=True)
    return path


# ─── sealed-code payload + resource enumeration ───────────────────────

# Files that are treated as endpoint CODE: shipped via stdin, NOT placed
# on the filesystem the handler can see. Anything not in this set is
# treated as a resource (bound RO into /app/code).
_CODE_FILE_SUFFIXES = (".py",)
_CODE_FILE_NAMES = frozenset({"pyproject.toml"})

# Cap on the total source-code payload size to keep the first stdin
# frame reasonable. A handful of .py files is typically well under
# 1 MB; if a user genuinely ships hundreds of MB of Python code as
# part of an endpoint, the sealed-code path is the wrong fit.
_SEALED_CODE_BYTE_LIMIT = 4 * 1024 * 1024  # 4 MiB


def _walk_synth(synth_dir: str):
    """Yield (rel_path, abs_path, is_dir) for every entry under synth_dir."""
    if not os.path.isdir(synth_dir):
        return
    for dirpath, dirnames, filenames in os.walk(synth_dir):
        rel_dir = os.path.relpath(dirpath, synth_dir)
        for d in dirnames:
            rel = os.path.normpath(os.path.join(rel_dir, d))
            yield rel, os.path.join(dirpath, d), True
        for f in filenames:
            rel = os.path.normpath(os.path.join(rel_dir, f))
            yield rel, os.path.join(dirpath, f), False


def _is_code_file(rel_path: str) -> bool:
    name = os.path.basename(rel_path)
    if name in _CODE_FILE_NAMES:
        return True
    return any(name.endswith(sfx) for sfx in _CODE_FILE_SUFFIXES)


@functools.lru_cache(maxsize=4)
def _resource_binds(guest_code_dir: str) -> tuple[str, ...]:
    """Build --ro-bind args for every top-level entry under the synth
    dir that is NOT endpoint code. .py files + pyproject.toml are
    intentionally excluded — they're shipped via the sealed-code
    payload and never appear in the bwrap mount tree.

    Top-level entries only: nested directories (e.g., templates/) are
    bound as a single subtree, which means any code inside a resource
    directory ALSO becomes visible to subprocesses. Users who want
    .py helpers must keep them at the synth-dir root.

    Cached: the synth dir is immutable for the container lifetime
    (host rebuilds the container on endpoint reload)."""
    args: list[str] = []
    synth = SYNTH_DIR_HOST_MOUNT
    if not os.path.isdir(synth):
        return tuple(args)
    for entry in sorted(os.listdir(synth)):
        src = os.path.join(synth, entry)
        if not os.path.isdir(src) and _is_code_file(entry):
            continue
        args += ["--ro-bind", src, os.path.join(guest_code_dir, entry)]
    return tuple(args)


@functools.lru_cache(maxsize=1)
def _sealed_code_payload() -> dict:
    """Read every .py file (and pyproject.toml) in the synth dir into a
    dict {relative_path: source_text}. The dict is shipped to the
    bwrap child as part of the first stdin frame; syft_entry.py
    compiles each entry and registers it in sys.modules.

    The dict's keys are POSIX-style relative paths (e.g. "runner.py",
    "helpers/parser.py"). syft_entry.py translates them into module
    names and a synthetic /app/code/<path> for __file__.

    Cached: the synth dir is immutable for the container lifetime.
    Callers must treat the returned dict as read-only."""
    synth = SYNTH_DIR_HOST_MOUNT
    payload: dict[str, str] = {}
    total = 0
    if not os.path.isdir(synth):
        return payload
    for rel, abs_path, is_dir in _walk_synth(synth):
        if is_dir:
            continue
        if not _is_code_file(rel):
            continue
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
        except OSError as e:
            log.warning("sealed-code: skipping %s: %s", rel, e)
            continue
        if total + len(data) > _SEALED_CODE_BYTE_LIMIT:
            log.error("sealed-code: payload exceeds %d bytes; skipping %s",
                      _SEALED_CODE_BYTE_LIMIT, rel)
            continue
        total += len(data)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            log.warning("sealed-code: %s is not utf-8, skipping", rel)
            continue
        payload[rel.replace(os.sep, "/")] = text
    return payload


# ─── bwrap argv builder ───────────────────────────────────────────────

def _bwrap_argv(workspace_dir: str) -> list[str]:
    """Build the bwrap argv shared by all child invocations.

    The mount layout is deliberately minimal — only what the handler
    needs to import Python stdlib + load runner.py + read/write
    workspace + use /tmp."""
    net_mode = os.environ.get(P.SYFT_SANDBOX_NET, "open").lower()

    argv = [
        BWRAP,
        # Namespaces.
        #
        # WHAT WE UNSHARE:
        #   user / ipc / uts  — cheap to isolate; no kernel rules tie
        #   their ownership to procfs.
        #
        # WHAT WE INTENTIONALLY DO NOT UNSHARE:
        #   pid — Linux ≥ 4.18 requires that the userns mounting procfs
        #         own BOTH the pidns AND the netns. We can't unshare the
        #         netns (handler needs network for API calls) AND we
        #         need procfs for Python's stdlib. So we share the
        #         container's pidns. Per-session pid isolation is a lost
        #         defense-in-depth layer; the container boundary still
        #         separates sessions from anything outside the container,
        #         and sessions all run as the same uid (1000) so they
        #         could ptrace each other regardless.
        #   net — handler needs network access (LLM API calls).
        #         Allowlist-mode policy is enforced at the proxy layer.
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup-try",
        "--die-with-parent",
        "--new-session",
        # Minimal /usr + Python runtime libraries (read-only).
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind-try", "/lib64", "/lib64",
        "--ro-bind-try", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind-try", "/etc/ssl", "/etc/ssl",
        "--ro-bind-try", "/etc/ca-certificates", "/etc/ca-certificates",
        # /app/code: a tmpfs containing only the user's DECLARED
        # RESOURCES (non-.py files like templates/, prompts/, data/).
        # The user's .py source code (runner.py + any helpers) is NOT
        # placed on the filesystem at all — it is shipped to the
        # handler as a `_sealed_code` payload in the first stdin
        # frame and pre-registered in sys.modules by syft_entry.py.
        #
        # Why: an LLM-driven handler can call subprocess.Popen (e.g.
        # `cat /app/code/runner.py` via claude-code's shell tool).
        # Subprocesses are NOT subject to the Python audit hook;
        # only kernel-level filesystem permissions stop them. By
        # leaving runner.py off the mount tree, ANY subprocess read
        # of /app/code/*.py returns ENOENT.
        #
        # /app/code itself is tmpfs (writable inside bwrap), but
        # writes don't persist — the tmpfs is destroyed when the
        # bwrap child exits. Resource binds underneath are RO.
        "--tmpfs", GUEST_CODE_DIR,
        *_resource_binds(GUEST_CODE_DIR),
        # The runtime (_syft_audit + syft_entry + session_loop) —
        # owned by root inside the image, chmod a-w.
        "--ro-bind", "/usr/local/lib/syft_runtime", GUEST_RUNTIME_DIR,
        # Container user's home directory — ALLOW-ONLY model.
        #
        # $HOME is a fresh, empty tmpfs; only the user's explicitly declared
        # mounts (always under $HOME/volumes/<name>, per the mounts UI) are
        # bound back in. Everything else the home volume might hold —
        # ~/.claude and ~/.claude.json (claude-code session/project history,
        # backups, any credentials), shell rc files, anything a prior session
        # wrote — is INVISIBLE by construction, not by enumeration. This is the
        # same posture as /app/code: build from nothing, bind in only what's
        # allowed, so a prompt-injected agent's `cat ~/.claude/...` or
        # `ls /home/runner` sees only the mounts it was given.
        #
        # claude still gets a writable ~/.claude for THIS session (it creates
        # it on the tmpfs); the state is ephemeral and destroyed when the bwrap
        # child exits. Writes into the bound mounts are gated by the underlying
        # container layer — a read-only frontmatter mount stays RO regardless.
        #
        # NOTE: content a custom endpoint image bakes into its home dir, or a
        # mount targeting a /home/<user> path OUTSIDE volumes/, will NOT be
        # visible — mounts must live under $HOME/volumes (which the UI enforces).
        "--tmpfs", HOST_HOME_DIR,
        "--bind-try", os.path.join(HOST_HOME_DIR, "volumes"), os.path.join(HOST_HOME_DIR, "volumes"),
        # Writable workspace.
        "--bind", workspace_dir, GUEST_WORKSPACE_DIR,
        "--tmpfs", "/tmp",
        # Bind the container's /proc instead of mounting a fresh procfs.
        # `--proc /proc` calls `mount -t proc` which the kernel rejects
        # when the userns doesn't own both pidns and netns (see above).
        # Binding the container's existing /proc satisfies Python's
        # stdlib needs (/proc/self/...) without violating the kernel
        # rule. The container env is HandlerEnv only (no PolicyEnv
        # secrets), so /proc/<pid>/environ does not leak anything
        # beyond what the handler is already allowed to see.
        "--ro-bind", "/proc", "/proc",
        "--dev", "/dev",
        "--chdir", GUEST_CODE_DIR,
        # Reset env; we set the allowlist below.
        "--clearenv",
    ]
    if net_mode == "none":
        # Note: --unshare-net combined with sharing the pidns will make
        # `--proc /proc` work (procfs from the bind is still consistent
        # because the netns ownership is what matters at mount time, and
        # bind-mounting an existing procfs doesn't re-trigger the check).
        # But there's still no network egress, by design.
        argv.append("--unshare-net")
    # In "allowlist" mode the container itself holds the proxy; the bwrap
    # child shares net so HTTPS_PROXY routes through 127.0.0.1.
    # In "open" mode net is shared by default (no --unshare-net).

    for k, v in _handler_env().items():
        argv += ["--setenv", k, v]
    argv += ["--", "python3", ENTRY_PATH]
    return argv


# ─── one-shot invocation (model / data_source) ────────────────────────

def execute_one_shot(input_payload: dict, timeout: float) -> dict:
    """Spawn a bwrap child, write input_payload as the first stdin frame,
    read the one-line JSON result, return it.

    On error returns {success: False, error: <message>, error_type: ...}
    — never raises, so the HTTP handler can return 200 with a structured
    body regardless of outcome."""
    workspace = _workspace_for(
        os.environ.get(P.SYFT_WORKSPACE_SCOPE, "shared"),
    )
    argv = _bwrap_argv(workspace)
    # Attach the sealed-code payload so syft_entry.py can register the
    # modules in sys.modules without the .py files being present in the
    # bwrap mount tree.
    input_payload = dict(input_payload)
    input_payload["_sealed_code"] = _sealed_code_payload()
    log.debug("spawning one-shot bwrap child: %s", " ".join(argv))

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"bwrap not found: {e}",
            "error_type": "FileNotFoundError",
        }
    except OSError as e:
        return {
            "success": False,
            "error": f"bwrap exec failed: {e}",
            "error_type": "OSError",
        }

    try:
        out_bytes, err_bytes = proc.communicate(
            input=(json.dumps(input_payload) + "\n").encode("utf-8"),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            out_bytes, err_bytes = proc.communicate(timeout=5)
        except Exception:
            out_bytes, err_bytes = b"", b""
        return {
            "success": False,
            "error": f"handler exceeded timeout of {timeout}s",
            "error_type": "TimeoutError",
        }

    if err_bytes:
        log.warning("bwrap child stderr: %s",
                    err_bytes.decode("utf-8", "replace"))

    last_line = ""
    for line in out_bytes.decode("utf-8", "replace").splitlines():
        if line.strip():
            last_line = line
    if not last_line:
        return {
            "success": False,
            "error": "handler produced no output",
            "error_type": "NoOutput",
            "stderr": err_bytes.decode("utf-8", "replace")[-512:],
        }
    try:
        return json.loads(last_line)
    except Exception as e:
        return {
            "success": False,
            "error": f"unparseable handler output: {e}",
            "error_type": "BadOutput",
        }


# ─── agent session multiplexer ────────────────────────────────────────

class _Session:
    """Long-lived bwrap subprocess + per-session event queue.

    Owns the child process lifecycle, reader thread (stdout → queue),
    and exposes deliver_message / deliver_attachment / cancel APIs.

    Terminal events (session.completed / session.failed / session.cancelled)
    are emitted by syft_entry.py inside the bwrap child, picked up by the
    reader thread, and forwarded to subscribers of /session/{id}/events."""

    # Event types emitted by syft_entry.py at the end of a session. The
    # reader loop tracks whether any of these was observed so it can
    # synthesize a failure event when bwrap dies before emitting any.
    _TERMINAL_EVENT_TYPES = frozenset({
        "session.completed",
        "session.failed",
        "session.cancelled",
    })
    # Cap on captured stderr — bwrap is terse but a runaway handler
    # crash dumping a megabyte of traceback would otherwise sit in
    # memory until the session is dropped.
    _STDERR_CAPTURE_LIMIT = 64 * 1024

    def __init__(self, session_id: str, start_payload: dict, user_sub: str):
        self.id = session_id
        self.events: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=512)
        self._done = threading.Event()
        self._lock = threading.Lock()
        # Set whenever a terminal event was forwarded from the child;
        # consulted by _reader_loop on EOF to decide whether to
        # synthesize a session.failed.
        self._saw_terminal = False
        # Most recent stderr lines from the bwrap child — surfaced in
        # the synthetic failure event so the operator sees the real
        # error (e.g. "bwrap: No permissions to create new namespace").
        self._stderr_tail: list[str] = []

        scope = os.environ.get(P.SYFT_WORKSPACE_SCOPE, "per_session")
        self._workspace = _workspace_for(scope, session_id=session_id,
                                         user_sub=user_sub)
        argv = _bwrap_argv(self._workspace)
        log.debug("spawning agent bwrap child for %s", session_id)
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )

        # Send session_start as the first frame. Includes the
        # sealed-code payload so syft_entry.py can register the
        # endpoint's modules in sys.modules — the .py files are NOT
        # on the bwrap filesystem.
        first = dict(start_payload)
        first.setdefault("type", "session_start")
        first["attachments_dir"] = start_payload.get(
            "attachments_dir", ""
        )
        first["_sealed_code"] = _sealed_code_payload()
        self._write(first)

        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True,
            name=f"session-{session_id}-reader",
        )
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(
            target=self._stderr_loop, daemon=True,
            name=f"session-{session_id}-stderr",
        )
        self._stderr_thread.start()

    # ── outbound (to bwrap child stdin) ─────────────────────────

    def _write(self, frame: dict) -> bool:
        line = (json.dumps(frame) + "\n").encode("utf-8")
        with self._lock:
            try:
                if self._proc.stdin is None or self._proc.stdin.closed:
                    return False
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
                return True
            except (BrokenPipeError, ValueError, OSError) as e:
                log.warning("session %s write failed: %s", self.id, e)
                return False

    def deliver_message(self, message: dict) -> bool:
        return self._write({"type": "user_message", "message": message})

    def deliver_attachment(self, attachment: dict) -> bool:
        return self._write({"type": "user_attachment", "attachment": attachment})

    def cancel(self) -> bool:
        if self._done.is_set():
            return False
        ok = self._write({"type": "cancel"})
        # Belt-and-suspenders: signal SIGTERM after a brief grace.
        threading.Timer(2.0, self._sigterm).start()
        return ok

    def _sigterm(self) -> None:
        if self._done.is_set():
            return
        try:
            self._proc.terminate()
        except Exception:
            pass

    # ── inbound (from bwrap child stdout) ───────────────────────

    def _reader_loop(self) -> None:
        assert self._proc.stdout is not None
        try:
            for raw in self._proc.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    frame = json.loads(raw)
                except Exception:
                    log.warning("session %s: malformed event line: %r",
                                self.id, raw[:200])
                    continue
                event_type = frame.get("type", "message")
                if event_type in self._TERMINAL_EVENT_TYPES:
                    self._saw_terminal = True
                # Map to the wire shape the host expects.
                self.events.put({
                    "type": event_type,
                    "data": frame.get("data", {}),
                    "id": frame.get("id", 0),
                })
        finally:
            rc = self._proc.wait()
            # If the child died (or exited cleanly) WITHOUT emitting a
            # terminal event, the host SSE reader has no way to know
            # the session ended in a failure — it would treat the empty
            # stream as a clean completion. Synthesize a session.failed
            # carrying the bwrap stderr so the operator sees the real
            # cause (most commonly: "bwrap: No permissions to create
            # new namespace" → host kernel disallows userns OR docker
            # seccomp is blocking unshare).
            if not self._saw_terminal:
                stderr_tail = "\n".join(self._stderr_tail).strip()
                reason = (
                    f"bwrap child exited with status {rc}" if rc != 0
                    else "bwrap child exited without emitting a terminal event"
                )
                self.events.put({
                    "type": "session.failed",
                    "data": {
                        "session_id": self.id,
                        "error": reason,
                        "reason": "bwrap_no_terminal",
                        "stderr": stderr_tail[-2048:] if stderr_tail else "",
                        "exit_code": rc,
                    },
                    "id": 0,
                })
            self._done.set()
            self.events.put(None)  # sentinel — SSE loop closes connection

    def _stderr_loop(self) -> None:
        assert self._proc.stderr is not None
        captured = 0
        try:
            for raw in self._proc.stderr:
                line = raw.decode("utf-8", "replace").rstrip()
                if not line:
                    continue
                log.warning("[session-%s stderr] %s", self.id, line)
                # Capture for inclusion in synthetic failure events.
                if captured < self._STDERR_CAPTURE_LIMIT:
                    self._stderr_tail.append(line)
                    captured += len(line) + 1
        except Exception:
            pass

    def is_done(self) -> bool:
        return self._done.is_set()


class _SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def start(self, session_id: str, start_payload: dict, user_sub: str) -> _Session:
        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"session {session_id} already exists")
            s = _Session(session_id, start_payload, user_sub)
            self._sessions[session_id] = s
            return s

    def get(self, session_id: str) -> Optional[_Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        with self._lock:
            s = self._sessions.pop(session_id, None)
        if s and not s.is_done():
            s.cancel()

    def cancel_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
        for s in sessions:
            s.cancel()


sessions = _SessionManager()


# ─── HTTP handler ─────────────────────────────────────────────────────

class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        log.debug("http %s", format % args)

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _parts(self) -> list[str]:
        return [s for s in self.path.split("?")[0].split("/") if s]

    # ── routes ──────────────────────────────────────────────────

    def do_GET(self):
        parts = self._parts()
        if parts == ["health"]:
            self._send_json(200, {"status": "ok"})
            return
        if (len(parts) == 3 and parts[0] == "session"
                and parts[2] == "events"):
            self._handle_session_events(parts[1])
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parts = self._parts()
        if parts == ["execute"]:
            self._handle_execute()
            return
        if parts == ["session", "start"]:
            self._handle_session_start()
            return
        if (len(parts) == 3 and parts[0] == "session"
                and parts[2] == "message"):
            self._handle_session_message(parts[1])
            return
        if (len(parts) == 3 and parts[0] == "session"
                and parts[2] == "attachment"):
            self._handle_session_attachment(parts[1])
            return
        self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        parts = self._parts()
        if len(parts) == 2 and parts[0] == "session":
            self._handle_session_cancel(parts[1])
            return
        self._send_json(404, {"error": "not found"})

    # ── handlers ────────────────────────────────────────────────

    def _handle_execute(self) -> None:
        try:
            payload = self._read_json()
        except Exception as e:
            self._send_json(400, {"success": False,
                                  "error": f"invalid JSON: {e}"})
            return
        timeout = float(payload.get("timeout_seconds")
                        or DEFAULT_ONESHOT_TIMEOUT)
        result = execute_one_shot(payload, timeout=timeout)
        # Always 200; the body says success/failure.
        self._send_json(200, result)

    def _handle_session_start(self) -> None:
        try:
            body = self._read_json()
        except Exception as e:
            self._send_json(400, {"success": False,
                                  "error": f"invalid JSON: {e}"})
            return
        session_id = body.get("session_id", "")
        if not session_id:
            self._send_json(400, {"success": False,
                                  "error": "session_id is required"})
            return
        user_sub = (body.get("user") or {}).get("sub", "") if isinstance(
            body.get("user"), dict) else ""
        try:
            sessions.start(session_id, body, user_sub)
        except ValueError as e:
            self._send_json(409, {"success": False, "error": str(e)})
            return
        except Exception as e:
            log.error("session_start failed: %s", e)
            self._send_json(500, {"success": False, "error": str(e)})
            return
        self._send_json(200, {"success": True, "session_id": session_id})

    def _handle_session_events(self, session_id: str) -> None:
        s = sessions.get(session_id)
        if s is None:
            self._send_json(404, {"error": "session not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # SSE streams have no Content-Length and we don't use chunked
        # encoding. The ONLY way to signal end-of-stream is to close
        # the TCP connection — without `Connection: close`, HTTP/1.1
        # keep-alive keeps the socket open after this handler returns
        # and the Go SSE reader blocks forever waiting for more bytes.
        # That manifests as "agent hangs with no reply" on the client.
        self.send_header("Connection", "close")
        # Tell Python's BaseHTTPRequestHandler to honor the close
        # request and not promote the connection to keep-alive.
        self.close_connection = True
        self.end_headers()
        try:
            while True:
                try:
                    ev = s.events.get(timeout=1.0)
                except queue.Empty:
                    if s.is_done():
                        break
                    continue
                if ev is None:
                    break
                event_type = ev.get("type", "message")
                event_data = json.dumps(ev.get("data", {}))
                event_id = ev.get("id", 0)
                msg = (
                    f"event: {event_type}\n"
                    f"data: {event_data}\n"
                    f"id: {event_id}\n\n"
                )
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            log.info("SSE client disconnected (session %s)", session_id)

    def _handle_session_message(self, session_id: str) -> None:
        try:
            body = self._read_json()
        except Exception as e:
            self._send_json(400, {"success": False,
                                  "error": f"invalid JSON: {e}"})
            return
        s = sessions.get(session_id)
        if s is None:
            self._send_json(404, {"success": False, "error": "session not found"})
            return
        ok = s.deliver_message(body)
        self._send_json(200 if ok else 503,
                        {"success": ok})

    def _handle_session_attachment(self, session_id: str) -> None:
        try:
            body = self._read_json()
        except Exception as e:
            self._send_json(400, {"success": False,
                                  "error": f"invalid JSON: {e}"})
            return
        s = sessions.get(session_id)
        if s is None:
            self._send_json(404, {"success": False, "error": "session not found"})
            return

        data_b64 = body.get("inline_data_b64", "")
        if not data_b64:
            self._send_json(400, {"success": False,
                                  "error": "inline_data_b64 required"})
            return
        try:
            raw = base64.b64decode(data_b64)
        except Exception as e:
            self._send_json(400, {"success": False,
                                  "error": f"decode: {e}"})
            return

        declared_size = body.get("size_bytes")
        if declared_size is not None and declared_size != len(raw):
            self._send_json(400, {"success": False, "error": "size mismatch"})
            return
        declared_sha = body.get("sha256", "")
        if declared_sha:
            actual = hashlib.sha256(raw).hexdigest()
            if actual != declared_sha:
                self._send_json(400, {"success": False, "error": "sha mismatch"})
                return

        file_id = body.get("file_id", "")
        raw_name = body.get("name", "") or ""

        # Pick a sanitized on-disk basename. Prefer the original filename
        # (so LLM-driven agents can use the friendly name in read_file calls
        # without hallucinating a path) and fall back to file_id when the
        # name is missing or sanitizes to nothing. _safe_segment REPLACES
        # dots with underscores (not strips), so split the extension off,
        # sanitize stem and ext separately, then reassemble — otherwise
        # "report.pdf" would collide with "report_pdf" in the unsplit path.
        basename_input = os.path.basename(raw_name) if raw_name else ""
        stem, ext_raw = os.path.splitext(basename_input)
        safe_stem = _safe_segment(stem, fallback="")
        safe_ext_body = _safe_segment(ext_raw.lstrip("."), fallback="")
        safe_ext = "." + safe_ext_body if safe_ext_body else ""
        if not safe_stem:
            safe_stem = _safe_segment(file_id)
        basename = safe_stem + safe_ext

        # Materialize under the session's workspace. The workspace is bound
        # into the bwrap child at GUEST_WORKSPACE_DIR, so we write to the
        # host-container path here but deliver the bwrap-visible path to the
        # handler — otherwise the audit hook denies the read (the host path
        # is neither bind-mounted at the same location nor in the allow-list).
        attachments_subdir = os.path.join(s._workspace, ".attachments")
        os.makedirs(attachments_subdir, mode=0o700, exist_ok=True)
        host_path = os.path.join(attachments_subdir, basename)
        # Two attachments with the same filename (different file_ids)
        # coexist — suffix the loser with a slice of its file_id rather
        # than overwrite. O_EXCL makes the create-or-collide check atomic.
        try:
            fd = os.open(host_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            short_id = _safe_segment(file_id)[:12]
            basename = f"{safe_stem}_{short_id}{safe_ext}"
            host_path = os.path.join(attachments_subdir, basename)
            fd = os.open(host_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        try:
            os.chmod(host_path, 0o600)
        except OSError:
            pass

        guest_path = os.path.join(GUEST_WORKSPACE_DIR, ".attachments", basename)

        delivered = s.deliver_attachment({
            "file_id": file_id,
            "name": body.get("name", file_id),
            "mime": body.get("mime", "application/octet-stream"),
            "size_bytes": len(raw),
            "sha256": declared_sha,
            "path": guest_path,
        })
        if not delivered:
            # The file is on disk but the runner queue rejected it. Clean
            # up so we don't leak a stray attachment for a delivery that
            # never happened.
            try:
                os.unlink(host_path)
            except OSError:
                pass
            self._send_json(503, {"success": False,
                                  "error": "attachment queue full"})
            return
        # Return BOTH the host-side path (for host-process audit / retry /
        # observability — outside bwrap) and the guest-side path (what the
        # handler will see inside bwrap). The historical "path" key kept
        # for backwards compatibility currently maps to guest_path because
        # that is what the protocol layer hands to the handler; new
        # consumers that need to stat the file from the host process
        # should use "host_path".
        self._send_json(200, {
            "success": True,
            "file_id": file_id,
            "path": guest_path,
            "guest_path": guest_path,
            "host_path": host_path,
        })

    def _handle_session_cancel(self, session_id: str) -> None:
        s = sessions.get(session_id)
        if s is None:
            self._send_json(404, {"success": False, "error": "session not found"})
            return
        s.cancel()
        sessions.drop(session_id)
        self._send_json(200, {"success": True})


# ─── server entry ─────────────────────────────────────────────────────

class _ThreadedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _verify_runtime_ready() -> None:
    """Fail fast at startup if the in-bwrap runtime is missing or bwrap
    cannot be invoked. Without these the container is useless."""
    for path in (BWRAP, AUDIT_HOOK_PATH, ENTRY_PATH, SESSION_LOOP_PATH):
        if not os.path.exists(path):
            log.error("runtime not ready: %s missing", path)
            raise SystemExit(2)
    if not os.access(BWRAP, os.X_OK):
        log.error("bwrap not executable: %s", BWRAP)
        raise SystemExit(2)
    # Ensure /app/synth is a directory (might be empty during early boot
    # if the host loader hasn't materialized yet, but the mount point
    # itself must exist).
    if not os.path.isdir(SYNTH_DIR_HOST_MOUNT):
        log.warning("%s does not exist; first request will fail",
                    SYNTH_DIR_HOST_MOUNT)


# ─── egress relay ─────────────────────────────────────────────────────────
#
# Keyless TCP→AF_UNIX relay. When SYFT_EGRESS_PORT / SYFT_EGRESS_SOCK are set
# (see containermode/egress.go), every handler LLM call is pointed at
# http://127.0.0.1:<port> (ANTHROPIC_BASE_URL / OPENAI_BASE_URL). This relay
# forwards those bytes verbatim to the host egress broker over the bind-mounted
# unix socket. It holds NO credential — the broker injects the real auth on the
# host side, so a compromised handler cannot read a secret here. The bwrap child
# shares the container netns, so it can reach this loopback listener regardless
# of the container's docker network mode (which is decided by the host provider
# — see filemode/provider.go).
def _start_egress_relay() -> None:
    port_s = os.environ.get(P.SYFT_EGRESS_PORT, "")
    sock_path = os.environ.get(P.SYFT_EGRESS_SOCK, "")
    if not port_s or not sock_path:
        return
    try:
        port = int(port_s)
    except ValueError:
        log.warning("egress relay: invalid %s %r", P.SYFT_EGRESS_PORT, port_s)
        return

    def _pump(src: socket.socket, dst: socket.socket) -> None:
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
        except OSError:
            pass
        finally:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def _handle(conn: socket.socket) -> None:
        try:
            up = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            up.connect(sock_path)
        except OSError as e:
            log.warning("egress relay: connect %s failed: %s", sock_path, e)
            conn.close()
            return
        # One pump per direction so request and streamed (SSE) response flow
        # concurrently without buffering.
        threading.Thread(target=_pump, args=(conn, up), daemon=True).start()
        _pump(up, conn)
        conn.close()
        up.close()

    def _serve() -> None:
        ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            ls.bind(("127.0.0.1", port))
            ls.listen(128)
        except OSError as e:
            log.error("egress relay: bind 127.0.0.1:%d failed: %s", port, e)
            return
        log.info("egress relay: 127.0.0.1:%d → %s", port, sock_path)
        while True:
            try:
                conn, _ = ls.accept()
            except OSError:
                break
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()

    threading.Thread(target=_serve, daemon=True).start()


def main() -> int:
    _verify_runtime_ready()
    _start_egress_relay()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    server = _ThreadedServer((host, port), RequestHandler)

    def _shutdown(signum, _frame):  # _frame: required by signal API, unused
        log.info("shutdown signal %s — cancelling sessions", signum)
        sessions.cancel_all()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("syft container runtime listening on %s:%d", host, port)
    log.info("handler-env allowlist: %s",
             ", ".join(_HANDLER_ENV_KEYS) or "<none>")
    log.info("network mode: %s",
             os.environ.get(P.SYFT_SANDBOX_NET, "open"))
    try:
        server.serve_forever()
    finally:
        sessions.cancel_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
