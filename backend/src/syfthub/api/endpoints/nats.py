"""NATS credentials endpoint.

Allows authenticated spaces to fetch the NATS auth token from the hub
so they can connect to NATS without needing a separate env var.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.core.config import get_settings
from syfthub.schemas.nats import NatsCredentialsResponse
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
