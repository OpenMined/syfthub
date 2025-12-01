"""User management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.db_dependencies import (
    OwnershipChecker,
    get_current_active_user,
)
from syfthub.database.dependencies import get_user_service
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User, UserResponse, UserUpdate
from syfthub.services.user_service import UserService

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
