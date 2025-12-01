"""Satellite token minting and verification endpoints.

This module provides the token exchange and verification endpoints for the
SyftHub Identity Provider. Users exchange their Hub session tokens for
audience-bound satellite tokens. Satellite services can either:
1. Verify tokens locally using JWKS public keys (stateless)
2. Call the /verify endpoint for server-side verification (stateful)

Per the OpenAPI spec:
- GET /api/v1/token?aud={audience} - Mint a satellite token
- POST /api/v1/verify - Verify a satellite token (server-side)
- Requires valid Hub session (Bearer token)
- Returns RS256-signed satellite token
"""

from typing import Annotated, Any, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.auth.keys import key_manager
from syfthub.auth.satellite_tokens import (
    TokenVerificationResult,
    create_satellite_token,
    get_allowed_audiences,
    validate_audience,
    verify_satellite_token_for_service,
)
from syfthub.core.config import settings
from syfthub.database.dependencies import get_user_repository
from syfthub.domain.exceptions import InvalidAudienceError, KeyNotConfiguredError
from syfthub.repositories.user import UserRepository
from syfthub.schemas.satellite import (
    SatelliteTokenErrorResponse,
    SatelliteTokenResponse,
    TokenVerifyErrorResponse,
    TokenVerifyRequest,
    TokenVerifySuccessResponse,
)
from syfthub.schemas.user import User

router = APIRouter()


@router.get(
    "/token",
    response_model=SatelliteTokenResponse,
    responses={
        200: {
            "description": "Token generated successfully",
            "model": SatelliteTokenResponse,
        },
        400: {
            "description": "Missing parameter or Invalid Audience requested",
            "model": SatelliteTokenErrorResponse,
        },
        401: {
            "description": "Unauthorized (Invalid or Expired Hub Token)",
        },
        503: {
            "description": "Service Unavailable (Identity Provider not configured)",
        },
    },
    summary="Exchange Hub Session for Satellite Token",
    description="""
Mint a new, short-lived JWT specifically for a target service (Audience).
The returned token is signed by the Hub's Private Key using RS256.

**Token Claims:**
- `sub`: User's unique ID
- `iss`: Issuer URL (Hub URL)
- `aud`: The target service identifier
- `exp`: Expiration timestamp (short-lived, typically 60 seconds)
- `role`: User's role (admin, user, etc.)

**Security:**
- Requires valid Hub session token
- Audience must be in the allowlist
- Token cannot be refreshed - request a new one when expired
""",
)
async def get_satellite_token(
    current_user: Annotated[User, Depends(get_current_active_user)],
    aud: str = Query(
        ...,
        description="Identifier of target service (e.g., 'syftai-space')",
        examples=["syftai-space"],
    ),
) -> SatelliteTokenResponse:
    """Exchange Hub session for an audience-bound satellite token.

    This endpoint allows authenticated users to obtain a short-lived,
    RS256-signed JWT token for use with satellite services. The token
    can be verified locally by satellite services using the JWKS endpoint.

    Args:
        current_user: Authenticated user from Hub session token
        aud: Target service identifier (must be in allowlist)

    Returns:
        SatelliteTokenResponse containing the RS256-signed JWT

    Raises:
        HTTPException: 400 if audience is invalid
        HTTPException: 401 if user is not authenticated (handled by dependency)
        HTTPException: 503 if RSA keys are not configured
    """
    # Check if Identity Provider is configured
    if not key_manager.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity Provider not configured. RSA keys are unavailable.",
        )

    # Validate audience parameter
    if not aud or not aud.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "missing_audience",
                "message": "The 'aud' query parameter is required.",
            },
        )

    # Validate audience against allowlist (FR-06)
    if not validate_audience(aud):
        allowed = ", ".join(sorted(get_allowed_audiences()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_audience",
                "message": f"The requested audience '{aud}' is not a registered service. "
                f"Allowed audiences: {allowed}",
            },
        )

    try:
        # Create satellite token
        target_token = create_satellite_token(
            user=current_user,
            audience=aud,
            key_manager=key_manager,
        )

        return SatelliteTokenResponse(
            target_token=target_token,
            expires_in=settings.satellite_token_expire_seconds,
        )

    except InvalidAudienceError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_audience",
                "message": str(e.message),
            },
        ) from e

    except KeyNotConfiguredError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e.message),
        ) from e


@router.get(
    "/token/audiences",
    response_model=dict[str, Any],
    summary="List Allowed Audiences",
    description="Returns the list of allowed audience identifiers for satellite tokens.",
)
async def list_allowed_audiences(
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, Any]:
    """List allowed audience identifiers.

    This endpoint returns the list of service identifiers that can be
    used when requesting satellite tokens. Only authenticated users
    can view this list.

    Returns:
        Dictionary containing the list of allowed audiences
    """
    return {
        "allowed_audiences": sorted(get_allowed_audiences()),
        "idp_configured": key_manager.is_configured,
    }


# ===========================================
# TOKEN VERIFICATION ENDPOINT
# ===========================================


@router.post(
    "/verify",
    response_model=Union[TokenVerifySuccessResponse, TokenVerifyErrorResponse],
    responses={
        200: {
            "description": "Token verification result (success or failure)",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Valid token",
                            "value": {
                                "valid": True,
                                "sub": "123",
                                "email": "alice@om.org",
                                "username": "alice",
                                "role": "admin",
                                "aud": "syftai-space",
                                "exp": 1699999999,
                                "iat": 1699999939,
                            },
                        },
                        "expired": {
                            "summary": "Expired token",
                            "value": {
                                "valid": False,
                                "error": "token_expired",
                                "message": "The token has expired.",
                            },
                        },
                        "audience_mismatch": {
                            "summary": "Wrong audience",
                            "value": {
                                "valid": False,
                                "error": "audience_mismatch",
                                "message": "Token audience 'other-service' does not match...",
                            },
                        },
                    }
                }
            },
        },
        401: {
            "description": "Unauthorized (Invalid or Expired Service Token)",
        },
        503: {
            "description": "Service Unavailable (Identity Provider not configured)",
        },
    },
    summary="Verify Satellite Token (Server-Side)",
    description="""
Verify a satellite token and retrieve user context.

This endpoint allows satellite services to verify tokens server-side instead of
using JWKS for local verification. The calling service must authenticate with
their own Hub session token.

**Authorization:**
The calling service's username determines which audience they can verify.
For example, a service account with username `syftai-space` can only verify
tokens where `aud=syftai-space`.

**Verification Checks:**
1. Token signature (RS256 with Hub's private key)
2. Token expiry (exp claim)
3. Token audience matches calling service's authorized audience
4. Token issuer matches Hub URL

**Response:**
- `valid: true` with user context if verification succeeds
- `valid: false` with error details if verification fails
""",
)
async def verify_satellite_token(
    request: TokenVerifyRequest,
    service: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Union[TokenVerifySuccessResponse, TokenVerifyErrorResponse]:
    """Verify a satellite token and return user context.

    This endpoint allows satellite services to verify tokens server-side.
    The calling service is identified by their Hub session token, and they
    can only verify tokens where the audience matches their username.

    Args:
        request: TokenVerifyRequest containing the token to verify
        service: The authenticated service (from SERVICE_TOKEN)
        user_repo: User repository for looking up user details

    Returns:
        TokenVerifySuccessResponse if valid, TokenVerifyErrorResponse if invalid
    """
    # Check if Identity Provider is configured
    if not key_manager.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity Provider not configured. RSA keys are unavailable.",
        )

    # The service's username is their authorized audience
    # This ensures services can only verify tokens intended for them
    authorized_audience = service.username

    # Verify the token
    result: TokenVerificationResult = verify_satellite_token_for_service(
        token=request.token,
        key_manager=key_manager,
        authorized_audience=authorized_audience,
    )

    if not result.valid:
        return TokenVerifyErrorResponse(
            valid=False,
            error=result.error or "verification_failed",
            message=result.message or "Token verification failed.",
        )

    # Token is valid - look up user from database to get email
    user_id = result.payload.get("sub")
    if not user_id:
        return TokenVerifyErrorResponse(
            valid=False,
            error="invalid_token",
            message="Token is missing 'sub' claim.",
        )

    # Look up user in database
    try:
        user = user_repo.get_by_id(int(user_id))
    except (ValueError, TypeError):
        return TokenVerifyErrorResponse(
            valid=False,
            error="invalid_user_id",
            message=f"Invalid user ID in token: {user_id}",
        )

    if not user:
        return TokenVerifyErrorResponse(
            valid=False,
            error="user_not_found",
            message=f"User with ID {user_id} not found.",
        )

    # Return success response with user context
    return TokenVerifySuccessResponse(
        valid=True,
        sub=str(user.id),
        email=user.email,
        username=user.username,
        role=result.payload.get("role", user.role),
        aud=result.payload.get("aud", authorized_audience),
        exp=result.payload.get("exp", 0),
        iat=result.payload.get("iat", 0),
    )
