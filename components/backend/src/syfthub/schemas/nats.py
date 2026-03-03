"""Schemas for NATS credential endpoints."""

import base64
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class NatsCredentialsResponse(BaseModel):
    """Response containing NATS authentication credentials."""

    nats_auth_token: str = Field(
        ..., description="The shared NATS auth token for WebSocket connections"
    )


class EncryptionKeyRegisterRequest(BaseModel):
    """Request to register an X25519 public key for tunnel encryption."""

    encryption_public_key: str = Field(
        ...,
        description="Base64url-encoded X25519 public key (32 bytes, 43-44 chars when encoded)",
    )

    @field_validator("encryption_public_key")
    @classmethod
    def validate_x25519_public_key(cls, v: str) -> str:
        """Validate that the value is a valid base64url-encoded X25519 public key."""
        if not v:
            raise ValueError("encryption_public_key must not be empty")
        # Restore padding for standard base64 decoding
        padded = v + "=" * (4 - len(v) % 4) if len(v) % 4 else v
        try:
            key_bytes = base64.urlsafe_b64decode(padded)
        except Exception as exc:
            raise ValueError("encryption_public_key must be valid base64url") from exc
        if len(key_bytes) != 32:
            raise ValueError(
                f"X25519 public key must be exactly 32 bytes, got {len(key_bytes)}"
            )
        return v


class EncryptionKeyResponse(BaseModel):
    """Response containing a space's X25519 public key for tunnel encryption."""

    encryption_public_key: Optional[str] = Field(
        None,
        description="Base64url-encoded X25519 public key, or null if not registered",
    )
