"""User management endpoints."""

import logging
from typing import Annotated, Union

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.db_dependencies import (
    OwnershipChecker,
    get_current_active_user,
)
from syfthub.core.config import settings
from syfthub.database.dependencies import get_user_service
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import (
    HeartbeatRequest,
    HeartbeatResponse,
    TunnelCredentialsResponse,
    User,
    UserResponse,
    UserUpdate,
)
from syfthub.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()

# Ownership checker for user resources
check_user_ownership = OwnershipChecker()


def require_admin(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> bool:
    """Require admin role."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted"
        )
    return True


@router.get("/", response_model=list[UserResponse])
async def list_users(
    _: Annotated[bool, Depends(require_admin)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> list[UserResponse]:
    """List all users (admin only)."""
    return user_service.get_users_list(active_only=False)


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current user's profile."""
    return UserResponse.model_validate(current_user)


@router.get("/me/tunnel-credentials", response_model=TunnelCredentialsResponse)
async def get_tunnel_credentials(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TunnelCredentialsResponse:
    """Get tunnel credentials for the authenticated user.

    Proxies to the ngrok REST API to create a fresh authtoken scoped
    to the user's reserved tunnel domain. The token is NOT persisted
    in SyftHub — each call creates a new credential.
    """
    if not settings.ngrok_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tunnel credentials service is not configured",
        )

    domain = f"{current_user.username}.{settings.ngrok_base_domain}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.ngrok.com/credentials",
                headers={
                    "Authorization": f"Bearer {settings.ngrok_api_key}",
                    "Content-Type": "application/json",
                    "ngrok-version": "2",
                },
                json={
                    "description": f"SyftHub tunnel credential for {current_user.username}",
                    "acl": [f"bind:{domain}"],
                },
            )
    except httpx.RequestError as exc:
        logger.warning("Failed to connect to ngrok API", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to tunnel credential service",
        ) from exc

    if response.status_code != 201:
        logger.warning("ngrok API returned status %d", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Tunnel credential service returned an error",
        )

    token = response.json().get("token")
    if not token:
        logger.warning("ngrok API response missing token field")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response from tunnel credential service",
        )

    return TunnelCredentialsResponse(auth_token=token, domain=domain)


@router.post("/me/heartbeat", response_model=HeartbeatResponse)
async def send_heartbeat(
    heartbeat_data: HeartbeatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> HeartbeatResponse:
    """Send heartbeat to indicate domain is online.

    .. deprecated::
        Use ``POST /api/v1/endpoints/health`` instead, which reports per-endpoint
        health status and also updates the owner heartbeat (subsumes this endpoint).
        This endpoint will be removed in a future release.

    This endpoint is called periodically by domain clients
    to indicate they are online and reachable. The heartbeat updates:
    - User's domain (extracted from URL)
    - last_heartbeat_at timestamp
    - heartbeat_expires_at timestamp

    The TTL is capped at the server's maximum TTL setting.
    """
    return user_service.send_heartbeat(
        user_id=current_user.id,
        url=heartbeat_data.url,
        ttl_seconds=heartbeat_data.ttl_seconds,
    )


@router.get("/check-username/{username}")
async def check_username_availability(
    username: str,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Union[bool, str]]:
    """Check if a username is available (public endpoint)."""
    available = user_service.username_available(username.lower())
    return {"available": available, "username": username.lower()}


@router.get("/check-email/{email}")
async def check_email_availability(
    email: str,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Union[bool, str]]:
    """Check if an email is available (public endpoint)."""
    available = user_service.email_available(email.lower())
    return {"available": available, "email": email.lower()}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Get a user by ID (admin or self only)."""
    # Check ownership or admin permissions
    check_user_ownership(current_user, user_id)

    user_profile = user_service.get_user_profile(user_id)
    if not user_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user_profile


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Update current user's profile."""
    return user_service.update_user_profile(current_user.id, user_data, current_user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Update a user by ID (admin or self only)."""
    return user_service.update_user_profile(user_id, user_data, current_user)


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Deactivate a user (admin only)."""
    user_service.deactivate_user(user_id, current_user)

    # Get updated user to return
    updated_user = user_service.get_user_profile(user_id)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    return updated_user


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Activate a user (admin only)."""
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted"
        )

    # Use repository directly for activate since service doesn't have this method
    user_repo = user_service.user_repository
    success = user_repo.activate_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Get updated user to return
    updated_user = user_service.get_user_profile(user_id)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user",
        )

    return updated_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> None:
    """Delete a user (admin or self only)."""
    # Check ownership or admin permissions
    check_user_ownership(current_user, user_id)

    # Use repository directly for delete since service doesn't have this method
    user_repo = user_service.user_repository
    success = user_repo.delete(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
