"""Schemas for NATS credential endpoints."""

from pydantic import BaseModel, Field


class NatsCredentialsResponse(BaseModel):
    """Response containing NATS authentication credentials."""

    nats_auth_token: str = Field(
        ..., description="The shared NATS auth token for WebSocket connections"
    )
