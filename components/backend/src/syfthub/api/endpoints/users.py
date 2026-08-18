"""User management endpoints."""

import logging
from typing import Annotated, Union

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)

from syfthub.auth.db_dependencies import (
    OwnershipChecker,
    get_current_active_user,
    require_admin,
)
from syfthub.core.client_ip import get_client_ip
from syfthub.core.config import settings
from syfthub.database.dependencies import (
    get_email_change_service,
    get_user_service,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import (
    AdminEmailUpdateResponse,
    EmailUpdate,
    PublicUserProfile,
    TunnelCredentialsResponse,
    User,
    UserResponse,
    UserUpdate,
)
from syfthub.services.email_change_service import (
    ADMIN_SET_EMAIL_TEMPLATE,
    EmailChangeService,
)
from syfthub.services.email_service import send_otp_email
from syfthub.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()

# Ownership checker for user resources
check_user_ownership = OwnershipChecker()


@router.get("/", response_model=list[UserResponse])
def list_users(
    _: Annotated[bool, Depends(require_admin)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> list[UserResponse]:
    """List all users (admin only)."""
    return user_service.get_users_list(active_only=False)


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current user's profile."""
    return UserResponse.model_validate(current_user)


@router.get("/me/tunnel-credentials", response_model=TunnelCredentialsResponse)
async def get_tunnel_credentials(
    request: Request,
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
        client = request.app.state.http_client
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


@router.get("/check-username/{username}")
def check_username_availability(
    username: str,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Union[bool, str]]:
    """Check if a username is available (public endpoint)."""
    available = user_service.username_available(username.lower())
    return {"available": available, "username": username.lower()}


@router.get("/check-email/{email}")
def check_email_availability(
    email: str,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> dict[str, Union[bool, str]]:
    """Check if an email is available (public endpoint)."""
    available = user_service.email_available(email.lower())
    return {"available": available, "email": email.lower()}


@router.get(
    "/public/{username}",
    response_model=PublicUserProfile,
    summary="Get Public User Profile",
    description="""
Public, anonymous-accessible profile for a user.

**No Authentication Required.**

Returns a sanitized profile suitable for the ``/:username`` page. Email is
only present in the response when the user has opted in via
``is_email_public``. Returns 404 for unknown or deactivated accounts.
""",
)
def get_public_user_profile(
    username: str,
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> PublicUserProfile:
    """Return a sanitized public profile for ``username``."""
    profile = user_service.get_public_user_profile(username.lower())
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return profile


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
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
def update_current_user_profile(
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Update current user's profile.

    Does not accept `email`; changing an address requires proving control of it.
    Use `PUT /auth/me/email`. The response still reports `pending_email` so a
    client can render an in-flight change from any profile read.
    """
    return user_service.update_user_profile(current_user.id, user_data, current_user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Update a user by ID (admin or self only).

    Does not accept `email` — see `PUT /users/{user_id}/email` for the admin
    path, or `PUT /auth/me/email` for a user changing their own.
    """
    return user_service.update_user_profile(user_id, user_data, current_user)


@router.put("/{user_id}/email", response_model=AdminEmailUpdateResponse)
def set_user_email(
    user_id: int,
    body: EmailUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    email_change_service: Annotated[
        EmailChangeService, Depends(get_email_change_service)
    ],
) -> AdminEmailUpdateResponse:
    """Set a user's email address outright (admin only).

    Applies immediately and **clears `is_email_verified`**: an administrator has
    not proven the new address belongs to its owner, so the verified flag must not
    carry over from the old one.

    A verification code is sent to the new address in the same request. That
    email is what tells the user their address moved — the previous address stops
    resolving, so without it the change would be silent. On their next sign-in
    they are prompted for the code, and entering it both verifies the address and
    completes the login; no session is needed at any point, which matters because
    a never-verified user has none.

    Refuses when the target is the caller: this path clears the verified flag and
    login is refused while that is false, so an admin aiming it at their own
    account would lock themselves out. Use `PUT /auth/me/email` for that, which
    keeps the current address working until the new one is verified.
    """
    updated, address, code = email_change_service.admin_set_email(
        user_id, body.email, current_user, requester_ip=get_client_ip(request)
    )

    if not code:
        return AdminEmailUpdateResponse(
            user=updated,
            verification_sent_to=None,
            message="Address unchanged; nothing was sent.",
        )

    background_tasks.add_task(send_otp_email, address, code, ADMIN_SET_EMAIL_TEMPLATE)
    return AdminEmailUpdateResponse(
        user=updated,
        verification_sent_to=address,
        message=(
            f"Address set to {address} and a verification code sent there. "
            "The user must enter it at next sign-in before they can log in again."
        ),
    )


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
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
def activate_user(
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
def delete_user(
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
