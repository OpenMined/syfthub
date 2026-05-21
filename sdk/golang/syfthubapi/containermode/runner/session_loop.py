"""In-bwrap AgentSession — JSON-lines bidirectional protocol on stdin/stdout.

This is the agent counterpart to the one-shot dispatcher in syft_entry.py.
It runs in the bwrap-isolated child process and exposes the SAME PUBLIC
SURFACE as filemode/agent_executor.go's wrapper script and the legacy
containermode SessionAPI — so the same user-written runner.handler(session)
works in any mode.

Protocol on stdin (JSON-lines, one frame per line):
    {"type": "session_start", "session_id": "...", "prompt": "...",
     "messages": [...], "config": {...}, "attachments_dir": "..."}
    {"type": "user_message", "message": {"type": "user_message",
                                          "content": "..."}}
    {"type": "user_attachment", "attachment": {"file_id": "...", ...}}
    {"type": "cancel"}

Protocol on stdout (JSON-lines):
    {"type": "<event>", "data": {...}, "id": <seq>}
    e.g. {"type": "agent.message", "data": {"content": "hi"}, "id": 3}

Terminal events (session.completed / session.failed) are emitted by the
caller in syft_entry.main, NOT here. This file only owns user-facing
event emission.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import uuid
from typing import Any, Optional


class _Cancelled:
    """Sentinel pushed onto the message queue when {type: cancel} arrives."""


class AgentSession:
    """In-process AgentSession that bridges stdin/stdout to the user's
    handler(session) function.

    Public attributes/methods mirror filemode AgentSession and the legacy
    container SessionAPI; do not break the surface."""

    def __init__(self, data: dict):
        self.id: str = data.get("session_id", "")
        self.prompt: str = data.get("prompt", "")
        self.messages: list = data.get("messages", [])
        self.config: dict = data.get("config", {})
        self.attachments_dir: str = data.get("attachments_dir", "")

        self._write_lock = threading.Lock()
        self._tc_counter = 0
        self._sequence = 0

        # Stdin frames are demultiplexed into two queues by a reader thread.
        self._messages: "queue.Queue[Any]" = queue.Queue()
        self._attachments: "queue.Queue[Any]" = queue.Queue()
        self._cancelled = False

        self._stdin_thread = threading.Thread(
            target=self._read_stdin_loop, daemon=True
        )
        self._stdin_thread.start()

    # ── outbound events ─────────────────────────────────────────

    def send_message(self, content: str) -> None:
        """Send a complete assistant message to the user."""
        self._emit("agent.message", {"content": content, "is_complete": True})

    def send_thinking(self, content: str) -> None:
        self._emit("agent.thinking", {"content": content, "is_streaming": False})

    def send_status(self, status: str, detail: str = "") -> None:
        self._emit("agent.status", {"status": status, "detail": detail})

    def send_tool_call(self, tool_name: str, arguments: dict,
                       tool_call_id: Optional[str] = None,
                       description: str = "",
                       requires_confirmation: bool = False) -> str:
        if tool_call_id is None:
            self._tc_counter += 1
            tool_call_id = f"tc-{self._tc_counter}"
        self._emit("agent.tool_call", {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "description": description,
            "requires_confirmation": requires_confirmation,
        })
        return tool_call_id

    def send_tool_result(self, tool_call_id: str, status: str = "success",
                         result: Any = None, error: Any = None,
                         duration_ms: int = 0) -> None:
        self._emit("agent.tool_result", {
            "tool_call_id": tool_call_id,
            "status": status,
            "result": result,
            "error": error,
            "duration_ms": duration_ms,
        })

    def send_token(self, token: str) -> None:
        self._emit("agent.token", {"token": token})

    def send_attachment(self, path, mime: Optional[str] = None,
                        name: Optional[str] = None) -> str:
        """Send a file attachment. Reads the file in-process and emits
        inline-tier metadata; the host bridge re-routes to object_store
        when it exceeds the inline threshold."""
        import base64
        import hashlib

        path_str = os.fspath(path)
        if not os.path.isfile(path_str):
            raise FileNotFoundError(path_str)
        with open(path_str, "rb") as f:
            data = f.read()
        sha = hashlib.sha256(data).hexdigest()
        file_id = "att-" + uuid.uuid4().hex
        self._emit("agent.attachment", {
            "file_id": file_id,
            "name": name or os.path.basename(path_str),
            "mime": mime or "application/octet-stream",
            "size_bytes": len(data),
            "plaintext_sha256": sha,
            "transport": "inline",
            "inline_data_b64": base64.b64encode(data).decode("ascii"),
        })
        return file_id

    # ── inbound events ──────────────────────────────────────────

    def receive(self, timeout: Optional[float] = None) -> Optional[dict]:
        """Block until a user message arrives. Returns the message dict
        (with "type" and optional "content" / "tool_call_id" fields).

        Raises KeyboardInterrupt on cancel, mirroring filemode behavior."""
        try:
            msg = self._messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(msg, _Cancelled):
            raise KeyboardInterrupt("Session cancelled by user")
        return msg

    def receive_attachment(self, timeout: Optional[float] = None) -> Optional[dict]:
        try:
            att = self._attachments.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(att, _Cancelled):
            return None
        return att

    def request_input(self, prompt: str = "") -> Optional[dict]:
        self._emit("agent.request_input", {"prompt": prompt})
        return self.receive()

    def request_confirmation(self, action: str,
                             arguments: Optional[dict] = None,
                             description: str = "") -> bool:
        self.send_tool_call(
            tool_name=action, arguments=arguments or {},
            description=description, requires_confirmation=True,
        )
        response = self.receive()
        if response is None:
            return False
        return response.get("type") == "user_confirm"

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    # ── internal plumbing ───────────────────────────────────────

    def _emit(self, event_type: str, data: dict) -> None:
        with self._write_lock:
            self._sequence += 1
            frame = {"type": event_type, "data": data, "id": self._sequence}
            sys.stdout.write(json.dumps(frame) + "\n")
            sys.stdout.flush()

    def _read_stdin_loop(self) -> None:
        """Demultiplex stdin frames into message vs. attachment queues."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except Exception:
                continue
            t = frame.get("type", "")
            if t == "cancel":
                self._cancelled = True
                self._messages.put(_Cancelled())
                self._attachments.put(_Cancelled())
                return
            if t == "user_attachment":
                self._attachments.put(frame.get("attachment", {}))
                continue
            # default: user_message-style frame
            self._messages.put(frame.get("message", {}))
