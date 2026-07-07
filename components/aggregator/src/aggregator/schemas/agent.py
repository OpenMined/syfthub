"""Pydantic v2 models for agent WebSocket messages and NATS agent message schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Session State
# =============================================================================


class AgentSessionState(str, Enum):
    """Agent session lifecycle state."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


# =============================================================================
# Client-to-Server (WebSocket inbound) models
# =============================================================================


class AgentWSEnvelope(BaseModel):
    """WebSocket message envelope for agent protocol."""

    type: str = Field(..., description="Message type identifier")
    session_id: str | None = Field(
        default=None, description="Session ID (set after session.created)"
    )
    sequence: int | None = Field(default=None, description="Monotonic sequence counter")
    timestamp: str | None = Field(default=None, description="ISO 8601 timestamp")
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload")


class EndpointRef(BaseModel):
    """Reference to an endpoint by owner and slug."""

    owner: str = Field(..., description="Endpoint owner username")
    slug: str = Field(..., description="Endpoint slug")


class SessionStartPayload(BaseModel):
    """Payload for session.start message."""

    prompt: str = Field(..., description="User's initial prompt")
    endpoint: EndpointRef = Field(..., description="Target agent endpoint")
    satellite_token: str = Field(..., description="Satellite token for space authentication")
    transaction_token: str | None = Field(default=None, description="Pre-authorized billing token")
    peer_token: str | None = Field(default=None, description="Peer token for NATS channel")
    peer_channel: str | None = Field(default=None, description="Peer channel identifier")
    config: dict[str, Any] | None = Field(default=None, description="Agent configuration")
    messages: list[dict[str, str]] | None = Field(default=None, description="Conversation history")


class UserMessagePayload(BaseModel):
    """Payload for user.message."""

    content: str = Field(..., description="Message content")
    satellite_token: str | None = Field(
        default=None, description="Optional refreshed satellite token"
    )


class UserConfirmPayload(BaseModel):
    """Payload for user.confirm."""

    tool_call_id: str = Field(..., description="ID of the tool call to confirm")
    modifications: str | None = Field(default=None, description="Optional argument modifications")


class UserDenyPayload(BaseModel):
    """Payload for user.deny."""

    tool_call_id: str = Field(..., description="ID of the tool call to deny")
    reason: str | None = Field(default=None, description="Reason for denial")


# =============================================================================
# Server-to-Client (WebSocket outbound) event payload models
# =============================================================================


class SessionCreatedPayload(BaseModel):
    """Payload for session.created event."""

    session_id: str = Field(..., description="Unique session identifier")


class AgentThinkingPayload(BaseModel):
    """Payload for agent.thinking event."""

    content: str = Field(..., description="Reasoning content")
    is_streaming: bool = Field(default=False, description="Whether content is being streamed")


class AgentToolCallPayload(BaseModel):
    """Payload for agent.tool_call event."""

    tool_call_id: str = Field(..., description="Unique tool call identifier")
    tool_name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    requires_confirmation: bool = Field(
        default=False, description="Whether user confirmation is needed"
    )
    description: str | None = Field(default=None, description="Human-readable description")


class AgentToolResultPayload(BaseModel):
    """Payload for agent.tool_result event."""

    tool_call_id: str = Field(..., description="Matching tool call ID")
    status: str = Field(..., description="'success' or 'error'")
    result: Any = Field(default=None, description="Tool output")
    error: str | None = Field(default=None, description="Error details")
    duration_ms: int | None = Field(default=None, description="Execution time in ms")


class AgentMessagePayload(BaseModel):
    """Payload for agent.message event."""

    content: str = Field(..., description="Message content")
    is_complete: bool = Field(default=True, description="Whether message is complete")


class AgentTokenPayload(BaseModel):
    """Payload for agent.token event."""

    token: str = Field(..., description="Streaming token")


class AgentStatusPayload(BaseModel):
    """Payload for agent.status event."""

    status: str = Field(..., description="Status identifier")
    detail: str = Field(default="", description="Human-readable detail")
    progress: float | None = Field(default=None, ge=0, le=1, description="Progress 0-1")


class AgentRequestInputPayload(BaseModel):
    """Payload for agent.request_input event."""

    prompt: str = Field(..., description="What the agent is requesting")


class AgentErrorPayload(BaseModel):
    """Payload for agent.error event."""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    recoverable: bool = Field(default=False, description="Whether the session can continue")


class SessionCompletedPayload(BaseModel):
    """Payload for session.completed event."""

    session_id: str = Field(..., description="Session ID")


class SessionFailedPayload(BaseModel):
    """Payload for session.failed event."""

    error: str = Field(..., description="Error message")
    reason: str = Field(default="unknown", description="Failure reason")
