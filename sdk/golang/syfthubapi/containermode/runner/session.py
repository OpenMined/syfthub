"""Thread-based agent session management."""
import threading
import queue
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("container_runner.session")


@dataclass
class Session:
    id: str
    prompt: str
    messages: list
    config: dict
    handler: object  # callable

    # Internal state
    event_queue: queue.Queue = field(
        default_factory=lambda: queue.Queue(maxsize=100)
    )
    message_queue: queue.Queue = field(
        default_factory=lambda: queue.Queue(maxsize=100)
    )
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _cancel_event: threading.Event = field(
        default_factory=threading.Event, repr=False
    )
    _done: bool = field(default=False)
    _error: Optional[str] = field(default=None)
    _sequence: int = field(default=0)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def start(self):
        """Spawn the handler thread."""
        self._thread = threading.Thread(
            target=self._run_handler,
            name=f"session-{self.id}",
            daemon=True,
        )
        self._thread.start()

    def send_event(self, event_type: str, data: dict):
        """Put an event on the event queue with auto-incrementing sequence."""
        with self._lock:
            self._sequence += 1
            seq = self._sequence
        event = {
            "type": event_type,
            "data": data,
            "id": seq,
        }
        try:
            self.event_queue.put(event, timeout=5.0)
        except queue.Full:
            logger.warning(
                "Event queue full for session %s, dropping event: %s",
                self.id,
                event_type,
            )

    def receive_message(self, timeout=None):
        """Blocking read from message queue."""
        try:
            return self.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def deliver_message(self, message: dict):
        """Non-blocking put on message queue."""
        try:
            self.message_queue.put_nowait(message)
            return True
        except queue.Full:
            logger.warning(
                "Message queue full for session %s", self.id
            )
            return False

    def cancel(self):
        """Set cancel event; handler should check periodically."""
        self._cancel_event.set()

    def is_done(self) -> bool:
        """Check if handler thread has finished."""
        return self._done

    def wait(self, timeout=None):
        """Join handler thread."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run_handler(self):
        """Run the user's handler function in a thread."""
        try:
            session_api = SessionAPI(self)
            self.handler(session_api)
            self._done = True
            self.send_event(
                "agent.session_complete", {"status": "completed"}
            )
        except Exception as e:
            self._error = str(e)
            self._done = True
            self.send_event("agent.session_failed", {"error": str(e)})
        finally:
            # Sentinel to signal event stream to close
            self.event_queue.put(None)


class SessionAPI:
    """API object passed to agent handlers for sending events and
    receiving messages.

    This mirrors the filemode AgentSession interface so that the same
    runner.py handler works in both subprocess and container mode.
    """

    def __init__(self, session: Session):
        self._session = session
        self._tc_counter = 0
        # Expose session data (mirrors filemode AgentSession attributes).
        self.id = session.id
        self.prompt = session.prompt
        self.messages = session.messages
        self.config = session.config

    def send_message(self, content: str):
        """Send a complete message to the user."""
        self._session.send_event(
            "agent.message", {"content": content, "is_complete": True}
        )

    def send_thinking(self, content: str):
        """Send thinking/reasoning content."""
        self._session.send_event(
            "agent.thinking", {"content": content, "is_streaming": False}
        )

    def send_status(self, status: str, detail: str = ""):
        """Send a status update."""
        self._session.send_event(
            "agent.status", {"status": status, "detail": detail}
        )

    def send_tool_call(self, tool_name: str, arguments: dict,
                       tool_call_id: str = None, description: str = "",
                       requires_confirmation: bool = False):
        """Send a tool call event."""
        if tool_call_id is None:
            self._tc_counter += 1
            tool_call_id = f"tc-{self._tc_counter}"
        self._session.send_event(
            "agent.tool_call",
            {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "description": description,
                "requires_confirmation": requires_confirmation,
            },
        )

    def send_tool_result(self, tool_call_id: str, status: str = "success",
                         result: Any = None, error: Any = None,
                         duration_ms: int = 0):
        """Send a tool result event."""
        self._session.send_event(
            "agent.tool_result",
            {
                "tool_call_id": tool_call_id,
                "status": status,
                "result": result,
                "error": error,
                "duration_ms": duration_ms,
            },
        )

    def send_token(self, token: str):
        """Send a streaming token."""
        self._session.send_event(
            "agent.token", {"token": token}
        )

    def receive(self) -> Optional[dict]:
        """Block until a user message arrives. Returns dict with message content."""
        if self._session._cancel_event.is_set():
            raise InterruptedError("Session cancelled")
        msg = self._session.receive_message()
        if msg is None:
            raise InterruptedError("Session cancelled")
        if msg.get("type") == "cancel":
            raise KeyboardInterrupt("Session cancelled by user")
        return msg.get("message", msg)

    def receive_message(self, timeout: float = None) -> Optional[dict]:
        """Block until a user message arrives or timeout."""
        if self._session._cancel_event.is_set():
            raise InterruptedError("Session cancelled")
        try:
            return self._session.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def request_input(self, prompt: str = ""):
        """Ask the user for input and wait for their response."""
        self._session.send_event(
            "agent.request_input", {"prompt": prompt}
        )
        return self.receive()

    def request_confirmation(self, action: str, arguments: dict = None,
                             description: str = ""):
        """Ask user to confirm an action. Returns True if confirmed."""
        self.send_tool_call(
            tool_name=action,
            arguments=arguments or {},
            description=description,
            requires_confirmation=True,
        )
        response = self.receive()
        return response.get("type") == "user_confirm"

    @property
    def cancelled(self) -> bool:
        return self._session._cancel_event.is_set()


class SessionManager:
    """Manages active agent sessions."""

    def __init__(self, handler):
        self.handler = handler
        self._sessions: dict = {}
        self._lock = threading.Lock()

    def start_session(
        self, session_id: str, prompt: str, messages: list, config: dict
    ) -> Session:
        """Create and start a new session."""
        session = Session(
            id=session_id,
            prompt=prompt,
            messages=messages,
            config=config,
            handler=self.handler,
        )
        with self._lock:
            self._sessions[session_id] = session
        session.start()
        logger.info("Started session %s", session_id)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def deliver_message(self, session_id: str, message: dict) -> bool:
        """Deliver a message to a session."""
        session = self.get_session(session_id)
        if session is None:
            return False
        return session.deliver_message(message)

    def cancel_session(self, session_id: str) -> bool:
        """Cancel a session."""
        session = self.get_session(session_id)
        if session is None:
            return False
        session.cancel()
        logger.info("Cancelled session %s", session_id)
        return True

    def cancel_all(self):
        """Cancel all active sessions."""
        with self._lock:
            for session_id, session in self._sessions.items():
                session.cancel()
                logger.info("Cancelled session %s", session_id)
