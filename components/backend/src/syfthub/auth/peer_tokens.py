"""Peer token management for NATS P2P communication.

Peer tokens are short-lived, Redis-backed credentials that grant the aggregator
temporary access to communicate with tunneling SyftAI Spaces via NATS pub/sub.

Flow:
1. Authenticated user calls POST /api/v1/peer-token with target_usernames
2. Backend generates a random token + unique peer_channel, stores in Redis
3. User passes peer_token in POST /chat/stream to the aggregator
4. Aggregator validates the token via Redis to get channel info + NATS auth
5. Aggregator connects to NATS, publishes to space channels, subscribes to peer_channel
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from syfthub.core.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


@dataclass
class PeerTokenData:
    """Internal representation of a peer token's associated data."""

    token: str
    peer_channel: str
    user_id: int
    target_usernames: List[str]
    expires_in: int
    nats_url: str
    nats_auth_token: str


def _generate_peer_channel(namespace: str) -> str:
    """Generate a unique peer channel ID, namespaced by the requesting user.

    Namespacing (``{namespace}.{uuid}``) lets a host's NATS credential be
    subscribe-scoped to ``syfthub.peer.{namespace}.>`` — so a symmetric desktop
    (host + client over one connection) can receive its own client sessions'
    replies without being able to read anyone else's peer channels.
    """
    return f"{namespace}.{uuid.uuid4().hex}"


def _generate_peer_token() -> str:
    """Generate a cryptographically secure peer token string."""
    return f"pt_{secrets.token_urlsafe(32)}"


def _generate_host_token() -> str:
    """Generate a cryptographically secure host token string."""
    return f"ht_{secrets.token_urlsafe(32)}"


async def create_peer_token(
    user_id: int,
    username: str,
    target_usernames: List[str],
    redis: Redis,
) -> PeerTokenData:
    """Create a new peer token and store it in Redis.

    Args:
        user_id: ID of the authenticated user requesting the token.
        username: Username of the requesting user; namespaces the peer channel.
        target_usernames: Usernames of tunneling spaces to communicate with.
        redis: Async Redis client.

    Returns:
        PeerTokenData with the generated token, channel, and connection info.
    """
    settings = get_settings()

    token = _generate_peer_token()
    peer_channel = _generate_peer_channel(username)
    expires_in = settings.peer_token_expire_seconds

    # Store token data in Redis with TTL
    token_data = {
        "user_id": user_id,
        "peer_channel": peer_channel,
        "target_usernames": target_usernames,
        "nats_url": settings.nats_url,
        "nats_auth_token": settings.nats_auth_token,
    }

    redis_key = f"nats:peer:{token}"
    await redis.set(redis_key, json.dumps(token_data), ex=expires_in)

    return PeerTokenData(
        token=token,
        peer_channel=peer_channel,
        user_id=user_id,
        target_usernames=target_usernames,
        expires_in=expires_in,
        nats_url=settings.nats_url,
        nats_auth_token=settings.nats_auth_token,
    )


async def create_guest_peer_token(
    target_usernames: List[str],
    redis: Redis,
) -> PeerTokenData:
    """Create a peer token for an unauthenticated (guest) user.

    Uses user_id=0 to mark as guest and a distinct Redis key prefix
    (nats:guest-peer:) for easier monitoring and separation.

    Args:
        target_usernames: Usernames of tunneling spaces (for auditing).
        redis: Async Redis client.

    Returns:
        PeerTokenData with the generated token, channel, and connection info.
    """
    settings = get_settings()

    token = _generate_peer_token()
    peer_channel = _generate_peer_channel("guest")
    expires_in = settings.guest_peer_token_expire_seconds

    # Store token data in Redis with TTL
    token_data = {
        "user_id": 0,
        "peer_channel": peer_channel,
        "target_usernames": target_usernames,
        "nats_url": settings.nats_url,
        "nats_auth_token": settings.nats_auth_token,
    }

    redis_key = f"nats:guest-peer:{token}"
    await redis.set(redis_key, json.dumps(token_data), ex=expires_in)

    return PeerTokenData(
        token=token,
        peer_channel=peer_channel,
        user_id=0,
        target_usernames=target_usernames,
        expires_in=expires_in,
        nats_url=settings.nats_url,
        nats_auth_token=settings.nats_auth_token,
    )


async def validate_peer_token(
    token: str,
    redis: Redis,
) -> Optional[PeerTokenData]:
    """Validate a peer token by looking it up in Redis.

    Args:
        token: The peer token string to validate.
        redis: Async Redis client.

    Returns:
        PeerTokenData if valid, None if expired or not found.
    """
    redis_key = f"nats:peer:{token}"
    raw = await redis.get(redis_key)

    if raw is None:
        return None

    data = json.loads(raw)

    # Get remaining TTL for expires_in
    ttl = await redis.ttl(redis_key)
    if ttl < 0:
        return None

    return PeerTokenData(
        token=token,
        peer_channel=data["peer_channel"],
        user_id=data["user_id"],
        target_usernames=data["target_usernames"],
        expires_in=ttl,
        nats_url=data["nats_url"],
        nats_auth_token=data["nats_auth_token"],
    )


async def revoke_peer_token(token: str, redis: Redis) -> bool:
    """Revoke a peer token by deleting it from Redis.

    Args:
        token: The peer token string to revoke.
        redis: Async Redis client.

    Returns:
        True if the token was found and deleted, False otherwise.
    """
    redis_key = f"nats:peer:{token}"
    deleted: int = await redis.delete(redis_key)
    return deleted > 0


# Host tokens are long-lived NATS credentials for a space serving agent
# endpoints. The space presents the token as its NATS connection token; the
# nats-auth callout service resolves nats:host:{token} -> username and grants
# the connection a JWT scoped to that space's own subjects.
#
# A long-running host that suffers a reconnect after the token's TTL has
# elapsed must re-fetch GET /api/v1/nats/credentials; see the design doc.
_HOST_TOKEN_EXPIRE_SECONDS = 86400


async def create_host_token(username: str, redis: Redis) -> str:
    """Mint a host token for a tunneling space and store it in Redis.

    Args:
        username: The space's username.
        redis: Async Redis client.

    Returns:
        The ``ht_…`` host token string, presented as the NATS connection token.
    """
    token = _generate_host_token()
    redis_key = f"nats:host:{token}"
    await redis.set(
        redis_key,
        json.dumps({"username": username}),
        ex=_HOST_TOKEN_EXPIRE_SECONDS,
    )
    return token
