"""Authentication business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException, status

from syfthub.auth.security import (
    create_access_token,
    create_refresh_token,
    generate_ed25519_key_pair,
    hash_password,
    verify_password,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import (
    AuthResponse,
    Ed25519KeyPair,
    KeyRegenerationResponse,
    RefreshTokenRequest,
    RegistrationResponse,
    Token,
    UserLogin,
    UserRegister,
)
from syfthub.schemas.user import User, UserCreate
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class AuthService(BaseService):
    """Authentication service for handling user authentication operations."""

    def __init__(self, session: Session):
        """Initialize auth service."""
        super().__init__(session)
        self.user_repository = UserRepository(session)

    def register_user(self, register_data: UserRegister) -> RegistrationResponse:
        """Register a new user and return authentication tokens."""
        # Validate input data
        if not register_data.username or len(register_data.username) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username must be at least 3 characters long",
            )

        if not register_data.password or len(register_data.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long",
            )

        # Check if user already exists
        if self.user_repository.username_exists(register_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        if self.user_repository.email_exists(register_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

        # Generate password hash and Ed25519 key pair
        password_hash = hash_password(register_data.password)
        key_pair = generate_ed25519_key_pair()

        # Create user data
        user_data = UserCreate(
            username=register_data.username,
            email=register_data.email,
            full_name=register_data.full_name,
            age=register_data.age,
            is_active=True,
        )

        # Create user in database
        user = self.user_repository.create_user(
            user_data=user_data,
            password_hash=password_hash,
            public_key=key_pair.public_key,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account",
            )

        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )

        return RegistrationResponse(
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            },
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            keys=Ed25519KeyPair(
                private_key=key_pair.private_key,
                public_key=key_pair.public_key,
            ),
        )

    def login_user(self, login_data: UserLogin) -> AuthResponse:
        """Authenticate user and return tokens."""
        # Get user by username or email
        user = None
        if "@" in login_data.username:
            user = self.user_repository.get_by_email(login_data.username)
        else:
            user = self.user_repository.get_by_username(login_data.username)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Verify password
        if not verify_password(login_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated",
            )

        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )

        return AuthResponse(
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            },
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    def refresh_tokens(self, refresh_data: RefreshTokenRequest) -> AuthResponse:
        """Refresh access token using refresh token."""
        from syfthub.auth.security import verify_token

        # Verify refresh token
        payload = verify_token(refresh_data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        # Get user from token
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user ID in token",
            ) from None

        user = self.user_repository.get_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Create new tokens
        access_token = create_access_token(
            data={"sub": str(user.id), "username": user.username, "role": user.role}
        )
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id), "username": user.username}
        )

        return AuthResponse(
            user={
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
            },
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
        )

    def verify_ed25519_signature(
        self, username: str, signature: str, message: str
    ) -> Optional[User]:
        """Verify Ed25519 signature and return user if valid."""
        from syfthub.auth.security import verify_ed25519_signature as verify_sig

        user = self.user_repository.get_by_username(username)
        if not user or not user.is_active:
            return None

        # Verify the signature
        if verify_sig(message.encode("utf-8"), signature, user.public_key):
            return user

        return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.user_repository.get_by_username(username)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.user_repository.get_by_email(email)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.user_repository.get_by_id(user_id)

    # Router-compatible methods
    def register(self, user_data: UserRegister) -> RegistrationResponse:
        """Register a new user - router-compatible wrapper."""
        return self.register_user(user_data)

    def login(self, username: str, password: str) -> Token:
        """Login user and return tokens - router-compatible wrapper."""
        login_data = UserLogin(username=username, password=password)
        auth_response = self.login_user(login_data)
        return Token(
            access_token=auth_response.access_token,
            refresh_token=auth_response.refresh_token,
            token_type=auth_response.token_type,
        )

    def refresh_token(self, refresh_token: str) -> Token:
        """Refresh access token - router-compatible wrapper."""
        refresh_request = RefreshTokenRequest(refresh_token=refresh_token)
        auth_response = self.refresh_tokens(refresh_request)
        return Token(
            access_token=auth_response.access_token,
            refresh_token=auth_response.refresh_token,
            token_type=auth_response.token_type,
        )

    def change_password(
        self, current_user: User, current_password: str, new_password: str
    ) -> None:
        """Change user's password."""
        # Verify current password
        if not verify_password(current_password, current_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Validate new password
        if len(new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long",
            )

        # Hash new password and update
        new_password_hash = hash_password(new_password)
        self.user_repository.update_password(current_user.id, new_password_hash)

    def regenerate_keys(self, current_user: User) -> KeyRegenerationResponse:
        """Regenerate Ed25519 key pair for user."""
        # Generate new key pair
        key_pair = generate_ed25519_key_pair()

        # Update user's public key in database
        self.user_repository.update_public_key(current_user.id, key_pair.public_key)

        return KeyRegenerationResponse(
            keys=Ed25519KeyPair(
                private_key=key_pair.private_key,
                public_key=key_pair.public_key,
            )
        )
