"""Peer token endpoint for NATS P2P communication.

Provides temporary NATS credentials so the aggregator can communicate
with tunneling SyftAI Spaces via pub/sub messaging.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.auth.peer_tokens import create_guest_peer_token, create_peer_token
from syfthub.core.config import get_settings
from syfthub.core.redis_client import get_redis_client
from syfthub.schemas.peer import (
    GuestPeerTokenRequest,
    PeerTokenRequest,
    PeerTokenResponse,
)
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


async def _check_guest_peer_rate_limit(request: Request) -> None:
    """Check IP-based rate limit for guest peer token requests.

    Uses Redis INCR + EXPIRE for a sliding window rate limiter.

    Raises:
        HTTPException: 429 if rate limit exceeded.
    """
    settings = get_settings()
    redis = await get_redis_client()

    ip = request.client.host if request.client else "unknown"
    key = f"nats:guest-peer:rate:{ip}"

    # Pipeline SET NX + INCR in one round-trip: SET NX initialises the key with
    # TTL on the first request; INCR atomically returns the new count.
    # Using transaction=False (no MULTI/EXEC) is enough — both commands execute
    # server-side in order, avoiding the INCR/EXPIRE race of the naive approach.
    async with redis.pipeline(transaction=False) as pipe:
        pipe.set(
            key, 0, ex=settings.guest_peer_token_rate_limit_window_seconds, nx=True
        )
        pipe.incr(key)
        _, count = await pipe.execute()

    if count > settings.guest_peer_token_rate_limit_max:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Guest peer token rate limit exceeded. Try again later.",
        )


@router.post(
    "/nats/guest-peer-token",
    response_model=PeerTokenResponse,
    responses={
        200: {
            "description": "Guest peer token generated successfully",
            "model": PeerTokenResponse,
        },
        429: {
            "description": "Rate limit exceeded",
        },
        503: {
            "description": "NATS service not configured",
        },
    },
    summary="Generate Guest Peer Token for NATS Communication",
    description="""
Generate a temporary NATS peer token for unauthenticated (guest) users.

No authentication required. Rate-limited by IP address.

**Returns:**
- `peer_token`: Short-lived token for NATS authentication
- `peer_channel`: Unique reply channel for receiving responses
- `expires_in`: Seconds until token expires
- `nats_url`: NATS server URL for WebSocket connections
""",
)
async def generate_guest_peer_token(
    http_request: Request,
    request: GuestPeerTokenRequest,
) -> PeerTokenResponse:
    """Generate a temporary peer token for guest NATS P2P communication.

    Args:
        http_request: FastAPI Request for IP extraction.
        request: GuestPeerTokenRequest with optional target usernames.

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

    # Check rate limit
    await _check_guest_peer_rate_limit(http_request)

    redis = await get_redis_client()

    token_data = await create_guest_peer_token(
        target_usernames=request.target_usernames,
        redis=redis,
    )

    return PeerTokenResponse(
        peer_token=token_data.token,
        peer_channel=token_data.peer_channel,
        expires_in=token_data.expires_in,
        nats_url=settings.nats_ws_public_url,
    )
