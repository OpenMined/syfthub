"""Satellite Token Service for Identity Provider.

This module provides functionality to create audience-bound, RS256-signed
JWT tokens for satellite services like SyftAI Space. These tokens allow
satellite services to verify user identity locally without calling
SyftHub for every request.

Token Flow:
1. User authenticates with SyftHub (gets HS256 Hub token)
2. User requests a satellite token for a specific audience
3. SyftHub validates audience against user database (audience = username)
4. SyftHub creates RS256-signed token with user claims
5. Satellite service verifies token using JWKS public keys

Audience Validation:
- Audiences are dynamically tied to user accounts
- A valid audience is any active user's username
- When a user is created, their username becomes a valid audience
- When a user is deactivated/deleted, their username becomes invalid
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

import jwt

from syfthub.core.config import settings
from syfthub.domain.exceptions import (
    KeyNotConfiguredError,
)

if TYPE_CHECKING:
    from syfthub.auth.keys import RSAKeyManager
    from syfthub.repositories.user import UserRepository
    from syfthub.schemas.user import User

logger = logging.getLogger(__name__)

# Constants for guest identity (unauthenticated users)
GUEST_SUB = "guest"
GUEST_EMAIL = "guest@syfthub.org"
GUEST_USERNAME = "guest"
GUEST_ROLE = "guest"


def get_allowed_audiences(
    user_repo: Optional[UserRepository] = None,
    limit: int = 100,
) -> set[str]:
    """Get the set of allowed audience identifiers.

    When user_repo is provided, returns usernames of active users.
    Otherwise, falls back to static config (deprecated).

    Args:
        user_repo: User repository for database lookup
        limit: Maximum number of usernames to return (for performance)

    Returns:
        Set of allowed audience strings (usernames)
    """
    if user_repo is not None:
        try:
            # Get active users from database
            users = user_repo.get_all(
                skip=0,
                limit=limit,
                filters={"is_active": True},
            )
            return {user.username.lower() for user in users}
        except Exception as e:
            logger.error(f"Failed to get allowed audiences from database: {e}")
            # Fall back to static config on error
            return settings.allowed_audiences

    # Fallback to static config (deprecated)
    return settings.allowed_audiences


def _mint_satellite_token(
    sub: str,
    role: str,
    audience: str,
    key_manager: RSAKeyManager,
) -> str:
    """Shared implementation for minting satellite-bound tokens.

    A pure claims-to-JWT transformation: it does no lookups and reaches no
    database. ``audience`` arrives already resolved — the caller has proved the
    satellite exists and belongs to the account it claims — which keeps this
    module free of repositories and keeps resolution in one place.

    Args:
        sub: Subject claim (user ID or "guest").
        role: Role claim (user role or "guest").
        audience: The **satellite's public_id**, as a string. Not a username:
            an account may run several hosts, so naming the account would let a
            token minted for one be accepted at another.
        key_manager: RSA key manager for signing.

    Returns:
        RS256-signed JWT string.

    Raises:
        KeyNotConfiguredError: If RSA keys are not configured.
    """
    # Check that key manager is configured
    if not key_manager.is_configured:
        raise KeyNotConfiguredError()

    # Build token payload
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.satellite_token_expire_seconds)

    payload = {
        "sub": sub,
        "iss": settings.issuer_url,
        "aud": audience,
        "exp": expire,
        "iat": now,
        "role": role,
    }

    # Build JWT headers with key ID
    headers = {
        "kid": key_manager.current_key_id,
    }

    # Sign token with RS256 using private key
    token: str = jwt.encode(
        payload,
        key_manager.private_key,
        algorithm="RS256",
        headers=headers,
    )

    return token


def create_guest_satellite_token(
    audience: str,
    key_manager: RSAKeyManager,
) -> str:
    """Create an audience-bound satellite token for a guest (unauthenticated) user.

    This function creates a short-lived, RS256-signed JWT for guest users who
    don't have a Hub account. Guest tokens allow unauthenticated access to
    policy-free endpoints.

    Args:
        audience: The target satellite's public_id, already resolved
        key_manager: RSA key manager for signing

    Returns:
        RS256-signed JWT string

    Raises:
        KeyNotConfiguredError: If RSA keys are not configured
    """
    return _mint_satellite_token(
        sub=GUEST_SUB,
        role=GUEST_ROLE,
        audience=audience,
        key_manager=key_manager,
    )


def create_satellite_token(
    user: User,
    audience: str,
    key_manager: RSAKeyManager,
) -> str:
    """Create an audience-bound satellite token for a user.

    This function creates a short-lived, RS256-signed JWT that satellite
    services can verify locally using the Hub's public keys.

    Args:
        user: The authenticated user requesting the token
        audience: The target satellite's public_id, already resolved
        key_manager: RSA key manager for signing

    Returns:
        RS256-signed JWT string

    Raises:
        KeyNotConfiguredError: If RSA keys are not configured
    """
    return _mint_satellite_token(
        sub=str(user.id),
        role=user.role,
        audience=audience,
        key_manager=key_manager,
    )


def decode_satellite_token(
    token: str,
    key_manager: RSAKeyManager,
    audience: str,
) -> dict[str, Any]:
    """Decode and verify a satellite token.

    This function is primarily for testing and debugging. Satellite services
    should use the JWKS endpoint to get public keys and verify tokens locally.

    Args:
        token: The JWT string to decode
        key_manager: RSA key manager for verification
        audience: Expected audience claim

    Returns:
        Decoded token payload

    Raises:
        jwt.InvalidTokenError: If token is invalid or verification fails
        KeyNotConfiguredError: If RSA keys are not configured
    """
    if not key_manager.is_configured:
        raise KeyNotConfiguredError()

    # Get the key ID from the token header
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")

    if not kid:
        raise jwt.InvalidTokenError("Token missing 'kid' header")

    # Get the public key for this key ID
    public_key = key_manager.get_public_key(kid)
    if not public_key:
        raise jwt.InvalidTokenError(f"Unknown key ID: {kid}")

    # Decode and verify the token
    payload: dict[str, Any] = jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=settings.issuer_url,
    )

    return payload


class TokenVerificationResult:
    """Result of token verification for a service.

    Attributes:
        valid: Whether the token is valid
        payload: Decoded token payload (if valid)
        error: Error code (if invalid)
        message: Error message (if invalid)
    """

    def __init__(
        self,
        valid: bool,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
        message: str | None = None,
    ) -> None:
        self.valid = valid
        self.payload = payload or {}
        self.error = error
        self.message = message


def verify_satellite_token_for_service(
    token: str,
    key_manager: RSAKeyManager,
    authorized_audiences: list[str],
) -> TokenVerificationResult:
    """Verify a satellite token for a specific service.

    This function verifies that:
    1. The token has a valid signature (signed by our private key)
    2. The token has not expired
    3. The token's audience is one of authorized_audiences

    The audiences are the caller's satellites, ensuring
    that services can only verify tokens intended for them.

    Args:
        token: The JWT string to verify
        key_manager: RSA key manager for verification
        authorized_audiences: The audiences this caller may verify for
                           (typically the service's username)

    Returns:
        TokenVerificationResult with valid=True and payload if successful,
        or valid=False with error details if verification fails.
    """
    if not key_manager.is_configured:
        return TokenVerificationResult(
            valid=False,
            error="idp_not_configured",
            message="Identity Provider is not configured. RSA keys are unavailable.",
        )

    # Get the key ID from the token header
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.DecodeError as e:
        return TokenVerificationResult(
            valid=False,
            error="invalid_token_format",
            message=f"Token is malformed: {e}",
        )

    kid = unverified_header.get("kid")
    if not kid:
        return TokenVerificationResult(
            valid=False,
            error="missing_kid",
            message="Token is missing 'kid' header.",
        )

    # Get the public key for this key ID
    public_key = key_manager.get_public_key(kid)
    if not public_key:
        return TokenVerificationResult(
            valid=False,
            error="unknown_key",
            message=f"Unknown key ID: {kid}. The token may be from a different issuer.",
        )

    # Decode and verify. PyJWT accepts a list for `audience` and passes when
    # the token's aud is any one of them — which is the membership test we want.
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=authorized_audiences,
            issuer=settings.issuer_url,
        )
        return TokenVerificationResult(valid=True, payload=payload)

    except jwt.ExpiredSignatureError:
        return TokenVerificationResult(
            valid=False,
            error="token_expired",
            message="The token has expired.",
        )

    except jwt.InvalidAudienceError:
        # Decode without audience verification to get the actual audience
        try:
            unverified_payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
                issuer=settings.issuer_url,
            )
            actual_aud = unverified_payload.get("aud", "unknown")
        except Exception:
            actual_aud = "unknown"

        return TokenVerificationResult(
            valid=False,
            error="audience_mismatch",
            message=f"Token audience '{actual_aud}' is not one of yours. "
            "You are not authorized to verify this token.",
        )

    except jwt.InvalidIssuerError:
        return TokenVerificationResult(
            valid=False,
            error="invalid_issuer",
            message=f"Token issuer does not match expected issuer '{settings.issuer_url}'.",
        )

    except jwt.InvalidSignatureError:
        return TokenVerificationResult(
            valid=False,
            error="invalid_signature",
            message="Token signature verification failed. The token may have been tampered with.",
        )

    except jwt.DecodeError as e:
        return TokenVerificationResult(
            valid=False,
            error="decode_error",
            message=f"Failed to decode token: {e}",
        )

    except Exception as e:
        return TokenVerificationResult(
            valid=False,
            error="verification_error",
            message=f"Token verification failed: {e}",
        )
