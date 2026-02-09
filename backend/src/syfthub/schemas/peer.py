"""Pydantic schemas for NATS peer token system.

These schemas define the request/response formats for the peer token
endpoint, which provides temporary NATS credentials for the aggregator
to communicate with tunneling SyftAI Spaces via pub/sub.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class PeerTokenRequest(BaseModel):
    """Request to generate a peer token for NATS communication.

    The caller specifies which tunneling users they need to reach.
    The backend generates a temporary NATS token and a unique reply channel.

    Attributes:
        target_usernames: Usernames of tunneling spaces to communicate with
    """

    target_usernames: List[str] = Field(
        ...,
        min_length=1,
        description="Usernames of the tunneling spaces the aggregator needs to reach",
        examples=[["alice", "bob"]],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "target_usernames": ["alice", "bob"],
            }
        }
    }


class PeerTokenResponse(BaseModel):
    """Response containing a temporary NATS peer token.

    The peer_token grants temporary NATS access scoped to:
    - Publishing to the target users' channels
    - Subscribing to the unique peer reply channel

    Attributes:
        peer_token: Temporary token for NATS authentication
        peer_channel: Unique reply channel ID for receiving responses
        expires_in: Seconds until the token expires
        nats_url: WebSocket URL for NATS connection (for external clients)
    """

    peer_token: str = Field(
        ...,
        description="Temporary token for NATS authentication",
    )
    peer_channel: str = Field(
        ...,
        description="Unique reply channel ID (e.g., 'peer_abc123')",
        examples=["peer_550e8400e29b41d4a716446655440000"],
    )
    expires_in: int = Field(
        ...,
        description="Seconds until the token expires",
        examples=[120],
    )
    nats_url: str = Field(
        ...,
        description="NATS server URL for connection",
        examples=["nats://nats:4222"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "peer_token": "pt_a1b2c3d4e5f6...",
                "peer_channel": "peer_550e8400e29b41d4a716446655440000",
                "expires_in": 120,
                "nats_url": "nats://nats:4222",
            }
        }
    }
