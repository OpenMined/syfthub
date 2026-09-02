"""User management endpoints."""

import logging
from typing import Annotated, Optional, Union

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
    get_email_verification_service,
    get_user_service,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import (
    PublicUserProfile,
    TunnelCredentialsResponse,
    User,
    UserResponse,
    UserUpdate,
)
from syfthub.services.email_service import send_email_changed_notice, send_otp_email
from syfthub.services.email_verification_service import (
    EMAIL_VERIFY_PURPOSE,
    EmailVerificationService,
)
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
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    """Get current user's profile.

    Goes through the service so ``domain`` is derived from the account's oldest
    space rather than read from the column, which is no longer written.
    """
    profile = user_service.get_user_profile(current_user.id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return profile


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


def _after_email_change(
    updated: UserResponse,
    previous_email: Optional[str],
    request: Request,
    background_tasks: BackgroundTasks,
    verification: EmailVerificationService,
) -> None:
    """Send what an address change owes the user, if it changed at all.

    Two messages, to two different inboxes, for two different reasons:

    - a code to the **new** address, so the account can claim it is verified
      again (the write cleared that state); and
    - a notice to the **old** address, the only inbox the account holder is known
      to control at this moment. Without it the change is silent, and a typo goes
      unnoticed until a password reset can no longer reach them.

    Both are best-effort background sends, and both are skipped when email
    delivery is not configured — in that deployment the address simply stays
    unverified, which is the honest state rather than a claimed proof.
    """
    if previous_email is None:
        return

    background_tasks.add_task(send_email_changed_notice, previous_email, updated.email)

    if not settings.smtp_configured:
        return

    code = verification.otp_service.generate_otp(
        updated.email, EMAIL_VERIFY_PURPOSE, requester_ip=get_client_ip(request)
    )
    background_tasks.add_task(send_otp_email, updated.email, code, EMAIL_VERIFY_PURPOSE)


@router.put("/me", response_model=UserResponse)
def update_current_user_profile(
    user_data: UserUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    verification: Annotated[
        EmailVerificationService, Depends(get_email_verification_service)
    ],
) -> UserResponse:
    """Update current user's profile.

    `email` is an ordinary field here and applies immediately. Doing so clears
    its verified state, sends a code to the new address, and tells the old
    address it was replaced. Nothing is gated on being verified — the account
    keeps working either way — so `is_email_verified` in the response is the
    signal for a client to prompt.
    """
    updated, previous_email = user_service.update_user_profile(
        current_user.id, user_data, current_user
    )
    _after_email_change(
        updated, previous_email, request, background_tasks, verification
    )
    return updated


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    verification: Annotated[
        EmailVerificationService, Depends(get_email_verification_service)
    ],
) -> UserResponse:
    """Update a user by ID (admin or self only).

    An admin changing someone else's `email` behaves exactly as a user changing
    their own: it applies, the verified state is cleared, and the same two
    messages go out. There is no separate admin mechanism, and no way for this to
    lock the target out.
    """
    updated, previous_email = user_service.update_user_profile(
        user_id, user_data, current_user
    )
    _after_email_change(
        updated, previous_email, request, background_tasks, verification
    )
    return updated


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
