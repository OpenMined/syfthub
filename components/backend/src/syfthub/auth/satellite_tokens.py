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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

import jwt

from syfthub.core.config import settings
from syfthub.domain.exceptions import (
    AudienceInactiveError,
    AudienceNotFoundError,
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


@dataclass
class AudienceValidationResult:
    """Result of audience validation.

    Attributes:
        valid: Whether the audience is valid
        error: Error message if invalid
        error_code: Error code for programmatic handling
    """

    valid: bool
    error: Optional[str] = None
    error_code: Optional[str] = None


def validate_audience(
    audience: str,
    user_repo: Optional[UserRepository] = None,
) -> AudienceValidationResult:
    """Validate that the requested audience is a valid, active user.

    The audience must be the username of an active user account. This ensures
    that tokens can only be minted for registered services/users.

    When user_repo is provided (recommended), validation is done against the
    database. This is the dynamic audience validation approach where any
    active user's username is a valid audience.

    Args:
        audience: The requested service identifier (username)
        user_repo: User repository for database lookup. If None, falls back
                   to static config (deprecated behavior).

    Returns:
        AudienceValidationResult with validation status and error details
    """
    # Normalize to lowercase for comparison
    normalized_audience = audience.strip().lower()

    if user_repo is not None:
        # Dynamic validation: Check if audience is an active user's username
        try:
            user = user_repo.get_by_username(normalized_audience)
        except Exception as e:
            # Fail closed on database errors - deny access
            logger.error(f"Database error during audience validation: {e}")
            return AudienceValidationResult(
                valid=False,
                error="Unable to validate audience. Please try again.",
                error_code="validation_error",
            )

        if user is None:
            return AudienceValidationResult(
                valid=False,
                error=f"Audience '{audience}' is not a registered user.",
                error_code="audience_not_found",
            )

        if not user.is_active:
            return AudienceValidationResult(
                valid=False,
                error=f"Audience '{audience}' is inactive.",
                error_code="audience_inactive",
            )

        return AudienceValidationResult(valid=True)

    # Fallback to static config (deprecated)
    logger.warning(
        "Using deprecated static audience validation. "
        "Pass user_repo for dynamic validation."
    )
    if normalized_audience in settings.allowed_audiences:
        return AudienceValidationResult(valid=True)

    return AudienceValidationResult(
        valid=False,
        error=f"Audience '{audience}' is not in the allowed list.",
        error_code="invalid_audience",
    )


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


def create_guest_satellite_token(
    audience: str,
    key_manager: RSAKeyManager,
    user_repo: Optional[UserRepository] = None,
) -> str:
    """Create an audience-bound satellite token for a guest (unauthenticated) user.

    This function creates a short-lived, RS256-signed JWT for guest users who
    don't have a Hub account. Guest tokens allow unauthenticated access to
    policy-free endpoints.

    Token Claims:
    - sub: "guest" (special identifier for guests)
    - iss: Issuer URL (e.g., 'https://hub.syft.com')
    - aud: Target service identifier (username of target user/service)
    - exp: Expiration timestamp (short-lived, e.g., 60s)
    - iat: Issued at timestamp
    - role: "guest" (indicates unauthenticated user)

    When verified via /verify, the Hub returns email="guest@syfthub.org"
    and username="guest" for guest tokens.

    Args:
        audience: Target service identifier (username of target user/service)
        key_manager: RSA key manager for signing
        user_repo: User repository for audience validation. If provided,
                   validates that audience is an active user's username.

    Returns:
        RS256-signed JWT string

    Raises:
        AudienceNotFoundError: If audience is not a registered user
        AudienceInactiveError: If audience user is inactive
        KeyNotConfiguredError: If RSA keys are not configured
    """
    # Validate audience against database (dynamic) or config (deprecated)
    validation_result = validate_audience(audience, user_repo)
    if not validation_result.valid:
        if validation_result.error_code == "audience_inactive":
            raise AudienceInactiveError(audience)
        else:
            raise AudienceNotFoundError(audience)

    # Check that key manager is configured
    if not key_manager.is_configured:
        raise KeyNotConfiguredError()

    # Build token payload for guest user
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.satellite_token_expire_seconds)

    payload = {
        "sub": GUEST_SUB,  # Special identifier for guest users
        "iss": settings.issuer_url,  # Issuer URL
        "aud": audience.strip().lower(),  # Target service (normalized)
        "exp": expire,  # Expiration
        "iat": now,  # Issued at
        "role": GUEST_ROLE,  # Guest role for unauthenticated users
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


def create_satellite_token(
    user: User,
    audience: str,
    key_manager: RSAKeyManager,
    user_repo: Optional[UserRepository] = None,
) -> str:
    """Create an audience-bound satellite token for a user.

    This function creates a short-lived, RS256-signed JWT that satellite
    services can verify locally using the Hub's public keys.

    Token Claims (per FR-07):
    - sub: User's unique ID
    - iss: Issuer URL (e.g., 'https://hub.syft.com')
    - aud: Target service identifier (username of target user/service)
    - exp: Expiration timestamp (short-lived, e.g., 60s)
    - iat: Issued at timestamp
    - role: User's role (e.g., 'admin', 'user')

    Token Header (per FR-08):
    - alg: RS256
    - typ: JWT
    - kid: Key ID matching the signing key

    Args:
        user: The authenticated user requesting the token
        audience: Target service identifier (username of target user/service)
        key_manager: RSA key manager for signing
        user_repo: User repository for audience validation. If provided,
                   validates that audience is an active user's username.

    Returns:
        RS256-signed JWT string

    Raises:
        AudienceNotFoundError: If audience is not a registered user
        AudienceInactiveError: If audience user is inactive
        KeyNotConfiguredError: If RSA keys are not configured
    """
    # Validate audience against database (dynamic) or config (deprecated)
    validation_result = validate_audience(audience, user_repo)
    if not validation_result.valid:
        if validation_result.error_code == "audience_inactive":
            raise AudienceInactiveError(audience)
        else:
            raise AudienceNotFoundError(audience)

    # Check that key manager is configured
    if not key_manager.is_configured:
        raise KeyNotConfiguredError()

    # Build token payload (FR-07)
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.satellite_token_expire_seconds)

    payload = {
        "sub": str(user.id),  # User's unique ID (string per JWT spec)
        "iss": settings.issuer_url,  # Issuer URL
        "aud": audience.strip().lower(),  # Target service (normalized)
        "exp": expire,  # Expiration
        "iat": now,  # Issued at
        "role": user.role,  # User's role
    }

    # Build JWT headers with key ID (FR-08)
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
    authorized_audience: str,
) -> TokenVerificationResult:
    """Verify a satellite token for a specific service.

    This function verifies that:
    1. The token has a valid signature (signed by our private key)
    2. The token has not expired
    3. The token's audience matches the authorized_audience

    The authorized_audience is typically the service's username, ensuring
    that services can only verify tokens intended for them.

    Args:
        token: The JWT string to verify
        key_manager: RSA key manager for verification
        authorized_audience: The audience this service is authorized to verify
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

    # Decode and verify the token
    # We verify against the authorized_audience (service's username)
    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=authorized_audience,
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
            message=f"Token audience '{actual_aud}' does not match authorized audience "
            f"'{authorized_audience}'. You are not authorized to verify this token.",
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
