"""User endpoints."""

from fastapi import APIRouter, HTTPException, status

from syfthub.schemas.user import User, UserCreate, UserResponse

router = APIRouter()

# Mock database
fake_users_db: dict[int, User] = {}
user_id_counter = 1


@router.get("/", response_model=list[UserResponse])
async def list_users() -> list[UserResponse]:
    """List all users."""
    return [UserResponse.model_validate(user) for user in fake_users_db.values()]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int) -> UserResponse:
    """Get a user by ID."""
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserResponse.model_validate(fake_users_db[user_id])


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user."""
    global user_id_counter

    # Check if email already exists
    for existing_user in fake_users_db.values():
        if existing_user.email == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    user = User(id=user_id_counter, **user_data.model_dump())
    fake_users_db[user_id_counter] = user
    user_id_counter += 1

    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_data: UserCreate) -> UserResponse:
    """Update a user."""
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user = User(id=user_id, **user_data.model_dump())
    fake_users_db[user_id] = user

    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int) -> None:
    """Delete a user."""
    if user_id not in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    del fake_users_db[user_id]
