"""NATS credentials endpoint.

Allows authenticated spaces to fetch the NATS auth token from the hub
so they can connect to NATS without needing a separate env var.

Also handles X25519 public key registration and lookup for E2E tunnel encryption.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.core.config import get_settings
from syfthub.database.dependencies import get_db_session
from syfthub.models.user import UserModel
from syfthub.schemas.nats import (
    EncryptionKeyRegisterRequest,
    EncryptionKeyResponse,
    NatsCredentialsResponse,
)
from syfthub.schemas.user import User

router = APIRouter()


@router.get(
    "/nats/credentials",
    response_model=NatsCredentialsResponse,
    responses={
        200: {
            "description": "NATS credentials retrieved successfully",
            "model": NatsCredentialsResponse,
        },
        401: {
            "description": "Unauthorized (invalid or expired session token)",
        },
        503: {
            "description": "NATS service not configured on this hub",
        },
    },
    summary="Get NATS Credentials",
    description="""
Retrieve the NATS authentication token for WebSocket connections.

Authenticated spaces call this after login to obtain the shared NATS
auth token, which they use to connect to the NATS server via WebSocket.
""",
)
async def get_nats_credentials(
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> NatsCredentialsResponse:
    """Return the NATS auth token for the authenticated user.

    Args:
        current_user: Authenticated user from session token.

    Returns:
        NatsCredentialsResponse with the NATS auth token.
    """
    settings = get_settings()

    if not settings.nats_auth_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NATS service is not configured.",
        )

    return NatsCredentialsResponse(nats_auth_token=settings.nats_auth_token)


@router.put(
    "/nats/encryption-key",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Encryption key registered successfully"},
        401: {"description": "Unauthorized (invalid or expired session token)"},
    },
    summary="Register Encryption Public Key",
    description="""
Register the X25519 public key for this space.

Tunneling spaces call this on startup after connecting to NATS. The hub stores
the key so the aggregator can encrypt tunnel request payloads destined for this
space. The key must be a base64url-encoded X25519 public key (32 bytes).
""",
)
async def register_encryption_key(
    body: EncryptionKeyRegisterRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, str]:
    """Store the caller's X25519 public key for tunnel encryption.

    Args:
        body: Request containing the base64url-encoded public key.
        current_user: Authenticated user from session token.
        session: Database session.

    Returns:
        Status dict {"status": "ok"}.
    """
    try:
        user_model = session.get(UserModel, current_user.id)
        if not user_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )
        user_model.encryption_public_key = body.encryption_public_key
        session.commit()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store encryption key.",
        ) from exc

    return {"status": "ok"}


@router.get(
    "/nats/encryption-key/{username}",
    response_model=EncryptionKeyResponse,
    responses={
        200: {
            "description": "Encryption key retrieved (may be null if not registered)"
        },
        404: {"description": "User not found"},
    },
    summary="Get Space Encryption Public Key",
    description="""
Look up the X25519 public key for a tunneling space by username.

Called by the aggregator before sending a tunnel request so it can
encrypt the payload. Public keys are safe to expose without authentication.
Returns null encryption_public_key if the space has not registered a key.
""",
)
async def get_space_encryption_key(
    username: str,
    session: Annotated[Session, Depends(get_db_session)],
) -> EncryptionKeyResponse:
    """Return the X25519 public key for the given username.

    Args:
        username: The space's username.
        session: Database session.

    Returns:
        EncryptionKeyResponse with the key or null.
    """
    stmt = select(UserModel).where(UserModel.username == username.lower())
    user_model = session.execute(stmt).scalar_one_or_none()

    if user_model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{username}' not found.",
        )

    return EncryptionKeyResponse(encryption_public_key=user_model.encryption_public_key)
