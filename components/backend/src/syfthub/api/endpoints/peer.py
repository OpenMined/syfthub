"""Peer token endpoint for NATS P2P communication.

Provides temporary NATS credentials so the aggregator can communicate
with tunneling SyftAI Spaces via pub/sub messaging.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.auth.peer_tokens import create_peer_token
from syfthub.core.config import get_settings
from syfthub.core.redis_client import get_redis_client
from syfthub.schemas.peer import PeerTokenRequest, PeerTokenResponse
from syfthub.schemas.user import User

router = APIRouter()


@router.post(
    "/peer-token",
    response_model=PeerTokenResponse,
    responses={
        200: {
            "description": "Peer token generated successfully",
            "model": PeerTokenResponse,
        },
        400: {
            "description": "Invalid request (empty target list)",
        },
        401: {
            "description": "Unauthorized (invalid or expired session token)",
        },
        503: {
            "description": "NATS service not configured",
        },
    },
    summary="Generate Peer Token for NATS Communication",
    description="""
Generate a temporary NATS peer token for the aggregator to communicate
with tunneling SyftAI Spaces via pub/sub.

**Flow:**
1. Client calls this endpoint with target space usernames
2. Backend generates a short-lived token + unique reply channel
3. Client passes the peer_token in POST /chat/stream
4. Aggregator uses the token to authenticate with NATS and exchange messages

**Returns:**
- `peer_token`: Short-lived token for NATS authentication
- `peer_channel`: Unique reply channel for receiving responses
- `expires_in`: Seconds until token expires
- `nats_url`: NATS server URL for WebSocket connections
""",
)
async def generate_peer_token(
    request: PeerTokenRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PeerTokenResponse:
    """Generate a temporary peer token for NATS P2P communication.

    Args:
        request: PeerTokenRequest with target usernames.
        current_user: Authenticated user from session token.

    Returns:
        PeerTokenResponse with token, channel, expiry, and NATS URL.
    """
    settings = get_settings()

    # Check that NATS is configured
    if not settings.nats_auth_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NATS service is not configured.",
        )

    redis = await get_redis_client()

    token_data = await create_peer_token(
        user_id=current_user.id,
        target_usernames=request.target_usernames,
        redis=redis,
    )

    return PeerTokenResponse(
        peer_token=token_data.token,
        peer_channel=token_data.peer_channel,
        expires_in=token_data.expires_in,
        nats_url=settings.nats_ws_public_url,
    )
