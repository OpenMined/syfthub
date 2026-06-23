"""Agent resource for bidirectional agent sessions via the Aggregator service.

Example usage:
    session = client.agent.start_session(
        AgentSessionOptions(
            prompt="Help me refactor this code",
            endpoint="alice/code-assistant",
        )
    )
    try:
        for event in session.events():
            if event["type"] == "agent.message":
                print(event["payload"]["content"])
            elif event["type"] == "session.completed":
                break
    finally:
        session.close()
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import websocket as _ws

from syfthub_sdk.exceptions import SyftHubError

if TYPE_CHECKING:
    from syfthub_sdk.auth import AuthResource


class AgentSessionError(SyftHubError):
    """Raised when an agent session operation fails."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


AgentSessionState = Literal[
    "idle",
    "connecting",
    "running",
    "awaiting_input",
    "completed",
    "failed",
    "cancelled",
    "error",
]


@dataclass
class AgentConfig:
    """Optional configuration for an agent session."""

    max_tokens: int | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class AgentHistoryMessage:
    """A message in optional conversation history."""

    role: str
    content: str


@dataclass
class AgentSessionOptions:
    """Options for starting an agent session.

    Args:
        prompt: The initial user prompt.
        endpoint: Endpoint in ``owner/slug`` format.
        config: Optional agent configuration.
        messages: Optional conversation history.
        aggregator_url: Override the client's aggregator URL.
    """

    prompt: str
    endpoint: str
    config: AgentConfig | None = None
    messages: list[AgentHistoryMessage] | None = None
    aggregator_url: str | None = None


class AgentSessionClient:
    """Client for an active agent session.

    Use :meth:`events` to iterate over events as they arrive, and
    :meth:`close` to cleanly terminate the connection.

    Example:
        session = client.agent.start_session(options)
        try:
            for event in session.events():
                print(event["type"], event.get("payload"))
        finally:
            session.close()
    """

    def __init__(self, ws: _ws.WebSocket, session_id: str) -> None:
        self._ws = ws
        self.session_id = session_id
        self._state: AgentSessionState = "running"

    @property
    def state(self) -> AgentSessionState:
        """Current session state."""
        return self._state

    def events(self) -> Generator[dict[str, Any], None, None]:
        """Yield agent events as they arrive.

        Stops when the session completes, fails, or the connection closes.
        """
        terminal = {"session.completed", "session.failed"}
        while True:
            try:
                raw = self._ws.recv()
            except Exception:
                break
            if not raw:
                break

            try:
                event: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")
            if event_type == "agent.request_input":
                self._state = "awaiting_input"
            elif event_type == "session.completed":
                self._state = "completed"
            elif event_type == "session.failed":
                self._state = "failed"
            elif event_type == "agent.error":
                payload = event.get("payload", {})
                if not payload.get("recoverable", True):
                    self._state = "error"
            elif self._state in ("awaiting_input", "connecting"):
                self._state = "running"

            yield event

            if event_type in terminal:
                break

    def send_message(self, content: str) -> None:
        """Send a user message to the agent."""
        self._send({"type": "user.message", "payload": {"content": content}})

    def confirm(self, tool_call_id: str) -> None:
        """Confirm a tool call."""
        self._send({"type": "user.confirm", "payload": {"tool_call_id": tool_call_id}})

    def deny(self, tool_call_id: str, reason: str | None = None) -> None:
        """Deny a tool call."""
        payload: dict[str, Any] = {"tool_call_id": tool_call_id}
        if reason is not None:
            payload["reason"] = reason
        self._send({"type": "user.deny", "payload": payload})

    def cancel(self) -> None:
        """Cancel the session."""
        self._state = "cancelled"
        self._send({"type": "user.cancel"})

    def close(self) -> None:
        """Close the session and the WebSocket connection."""
        with contextlib.suppress(Exception):
            self._send({"type": "session.close"})
        with contextlib.suppress(Exception):
            self._ws.close()

    def _send(self, msg: dict[str, Any]) -> None:
        self._ws.send(json.dumps(msg))


class AgentResource:
    """Bidirectional agent sessions via the Aggregator.

    Example:
        session = client.agent.start_session(
            AgentSessionOptions(prompt="Hello", endpoint="alice/bot")
        )
        for event in session.events():
            print(event["type"])
        session.close()
    """

    def __init__(self, auth: AuthResource, aggregator_url: str) -> None:
        self._auth = auth
        self._aggregator_url = aggregator_url.rstrip("/")

    def start_session(self, options: AgentSessionOptions) -> AgentSessionClient:
        """Start a new agent session.

        Resolves the endpoint, fetches satellite and peer tokens, opens a
        WebSocket connection to the aggregator, sends ``session.start``, and
        waits for ``session.created`` before returning.

        Args:
            options: Session options including prompt and endpoint.

        Returns:
            AgentSessionClient ready to yield events.

        Raises:
            ValueError: If the endpoint is not in ``owner/slug`` format.
            AgentSessionError: If the aggregator rejects the session.
        """
        parts = options.endpoint.split("/", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Endpoint must be in 'owner/slug' format, got: {options.endpoint}"
            )
        owner, slug = parts

        sat_resp = self._auth.get_satellite_token(owner)
        peer_resp = self._auth.get_peer_token([owner])

        aggregator_url = (options.aggregator_url or self._aggregator_url).rstrip("/")
        ws_url = aggregator_url.replace("https://", "wss://").replace(
            "http://", "ws://"
        )
        ws_url += "/agent/session"

        ws: _ws.WebSocket = _ws.create_connection(ws_url)

        start_payload: dict[str, Any] = {
            "prompt": options.prompt,
            "endpoint": {"owner": owner, "slug": slug},
            "satellite_token": sat_resp.target_token,
            "peer_token": peer_resp.peer_token,
            "peer_channel": peer_resp.peer_channel,
        }
        if options.config is not None:
            cfg = options.config
            config_dict: dict[str, Any] = {}
            if cfg.max_tokens is not None:
                config_dict["max_tokens"] = cfg.max_tokens
            if cfg.temperature is not None:
                config_dict["temperature"] = cfg.temperature
            if cfg.system_prompt is not None:
                config_dict["system_prompt"] = cfg.system_prompt
            if cfg.metadata is not None:
                config_dict["metadata"] = cfg.metadata
            if config_dict:
                start_payload["config"] = config_dict
        if options.messages:
            start_payload["messages"] = [
                {"role": m.role, "content": m.content} for m in options.messages
            ]

        ws.send(json.dumps({"type": "session.start", "payload": start_payload}))

        raw = ws.recv()
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError as exc:
            ws.close()
            raise AgentSessionError("Failed to parse session.created response") from exc

        if resp.get("type") == "agent.error":
            ws.close()
            payload = resp.get("payload", {})
            raise AgentSessionError(
                payload.get("message", "Session start failed"),
                code=payload.get("code"),
            )

        session_id = resp.get("session_id") or resp.get("payload", {}).get(
            "session_id", ""
        )
        return AgentSessionClient(ws, session_id)
