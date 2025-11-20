"""Authentication endpoints."""

from typing import Annotated, Dict, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    OAuth2PasswordRequestForm,
)

from syfthub.auth.db_dependencies import (
    get_current_active_user,
    security,
)
from syfthub.auth.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    generate_ed25519_key_pair,
    hash_password,
    verify_password,
    verify_token,
)
from syfthub.database.dependencies import get_user_repository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import (
    Ed25519KeyPair,
    KeyRegenerationResponse,
    PasswordChange,
    RefreshTokenRequest,
    RegistrationResponse,
    Token,
    UserRegister,
)
from syfthub.schemas.user import User, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    user_data: UserRegister,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> RegistrationResponse:
    """Register a new user."""
    # Check if username already exists
    if user_repo.username_exists(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists
    if user_repo.email_exists(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user using repository
    password_hash = hash_password(user_data.password)
    key_pair = generate_ed25519_key_pair()

    user_create = UserCreate(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        age=user_data.age,
        is_active=True,
    )

    user = user_repo.create_user(
        user_data=user_create,
        password_hash=password_hash,
        public_key=key_pair.public_key,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "username": user.username}
    )

    # Return response
    user_dict: Dict[str, Union[str, int, bool, None]] = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }

    # Create key pair response
    keys = Ed25519KeyPair(
        private_key=key_pair.private_key,
        public_key=key_pair.public_key,
    )

    return RegistrationResponse(
        user=user_dict,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        keys=keys,
    )


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Token:
    """OAuth2 compatible token login, get an access token for future requests."""
    # Authenticate user
    user = authenticate_user(form_data.username, form_data.password, user_repo)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    # Create tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> Token:
    """Refresh access token using refresh token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Verify refresh token
    payload = verify_token(refresh_request.refresh_token, token_type="refresh")
    if payload is None:
        raise credentials_exception

    # Get user info from token
    user_id_str = payload.get("sub")
    username = payload.get("username")

    if user_id_str is None or username is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception from None

    # Get user from database
    user = user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    # Blacklist old refresh token
    blacklist_token(refresh_request.refresh_token)

    # Create new tokens
    access_token = create_access_token(
        data={"sub": str(user.id), "username": user.username, "role": user.role}
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id), "username": user.username}
    )

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[User, Depends(get_current_active_user)],  # noqa: ARG001
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> None:
    """Logout user by blacklisting their tokens."""
    # Blacklist the current access token
    blacklist_token(credentials.credentials)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current user profile information."""
    return UserResponse.model_validate(current_user)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: PasswordChange,
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> None:
    """Change current user's password."""
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password"
        )

    # Update password
    new_password_hash = hash_password(password_data.new_password)
    user_repo.update_password(current_user.id, new_password_hash)


@router.post("/regenerate-keys", response_model=KeyRegenerationResponse)
async def regenerate_user_keys(
    current_user: Annotated[User, Depends(get_current_active_user)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> KeyRegenerationResponse:
    """Regenerate Ed25519 key pair for the current user."""
    # Generate new key pair
    key_pair = generate_ed25519_key_pair()

    # Update user's public key in database
    user_repo.update_public_key(current_user.id, key_pair.public_key)

    # Create key pair response
    keys = Ed25519KeyPair(
        private_key=key_pair.private_key,
        public_key=key_pair.public_key,
    )

    return KeyRegenerationResponse(keys=keys)


def authenticate_user(
    username: str, password: str, user_repo: UserRepository
) -> Optional[User]:
    """Authenticate a user by username/email and password."""
    # Try to find user by username or email
    user = user_repo.get_by_username(username)
    if not user:
        user = user_repo.get_by_email(username)

    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
