"""User management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from syfthub.auth.dependencies import (
    OwnershipChecker,
    fake_users_db,
    get_current_active_user,
)
from syfthub.schemas.auth import UserRole
from syfthub.schemas.user import User, UserResponse, UserUpdate

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
async def list_users(_: Annotated[bool, Depends(require_admin)]) -> list[UserResponse]:
    """List all users (admin only)."""
    return [UserResponse.model_validate(user) for user in fake_users_db.values()]


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
) -> UserResponse:
    """Get a user by ID (admin or self only)."""
    # Check if user exists
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check ownership or admin permissions
    target_user = fake_users_db[user_id]
    check_user_ownership(current_user, target_user.id)

    return UserResponse.model_validate(target_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Update current user's profile."""
    # Update user data
    update_data = user_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.now(timezone.utc)

    # Save to database
    fake_users_db[current_user.id] = current_user

    return UserResponse.model_validate(current_user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Update a user by ID (admin or self only)."""
    # Check if user exists
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check ownership or admin permissions
    target_user = fake_users_db[user_id]
    check_user_ownership(current_user, target_user.id)

    # Update user data
    update_data = user_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(target_user, field, value)

    target_user.updated_at = datetime.now(timezone.utc)

    # Save to database
    fake_users_db[user_id] = target_user

    return UserResponse.model_validate(target_user)


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int, _: Annotated[bool, Depends(require_admin)]
) -> UserResponse:
    """Deactivate a user (admin only)."""
    # Check if user exists
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user = fake_users_db[user_id]
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)


@router.patch("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: int, _: Annotated[bool, Depends(require_admin)]
) -> UserResponse:
    """Activate a user (admin only)."""
    # Check if user exists
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user = fake_users_db[user_id]
    user.is_active = True
    user.updated_at = datetime.now(timezone.utc)

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Delete a user (admin or self only)."""
    # Check if user exists
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check ownership or admin permissions
    target_user = fake_users_db[user_id]
    check_user_ownership(current_user, target_user.id)

    # Delete user
    del fake_users_db[user_id]
