"""In-memory registry of active agent sessions for attachment HTTP authorization.

The CLIENT uploads attachments via HTTP POST /agent/session/{sid}/attachment.
That request needs to be tied back to a live WS session so we know which
NATSSessionTransport to send the metadata event through, and so we have the
shared session_attachment_key to wrap per-file keys.

Lifecycle: registered when agent_session_ws creates a session, unregistered
in the finally-block when the WS closes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class AttachmentSession:
    """Per-session state needed by the HTTP relay endpoints."""

    session_id: str
    target_username: str
    session_attachment_key: bytes  # 32-byte AES key shared with the HOST
    # transport is typed loosely to avoid circular imports.
    transport: Any

    # Quota tracking (platform-level — per-endpoint policy lands in v2).
    bytes_used: int = 0
    files_used: int = 0


class AttachmentSessionRegistry:
    """Thread-safe registry of active attachment-capable sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, AttachmentSession] = {}
        self._lock = threading.Lock()

    def register(self, session: AttachmentSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> AttachmentSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def consume_quota(self, session_id: str, bytes_added: int) -> bool:
        """Record bytes_added against the session's quota. Returns False if
        the per-session aggregate cap would be exceeded.

        Uses platform defaults (see docs/architecture/attachments.md). Per-
        endpoint policy lands in v2.
        """
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                return False
            if s.bytes_used + bytes_added > MAX_ATTACHMENT_BYTES_PER_SESSION:
                return False
            if s.files_used + 1 > MAX_ATTACHMENTS_PER_SESSION:
                return False
            s.bytes_used += bytes_added
            s.files_used += 1
            return True


# Platform-default quotas (from docs/architecture/attachments.md "Platform-
# level quotas (v1)" table). Overridden by environment in production.
MAX_ATTACHMENT_BYTES_PER_FILE = 25 * 1024 * 1024  # 25 MiB
MAX_ATTACHMENT_BYTES_PER_SESSION = 100 * 1024 * 1024  # 100 MiB
MAX_ATTACHMENTS_PER_SESSION = 20


# Process-wide singleton. Lifetime tied to the aggregator process.
_registry = AttachmentSessionRegistry()


def registry() -> AttachmentSessionRegistry:
    """Return the process-wide attachment session registry."""
    return _registry
