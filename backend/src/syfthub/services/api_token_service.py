"""API Token management business logic service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from syfthub.auth.api_tokens import generate_api_token
from syfthub.repositories.api_token import APITokenRepository
from syfthub.schemas.api_token import (
    APIToken,
    APITokenCreate,
    APITokenCreateResponse,
    APITokenListResponse,
    APITokenUpdate,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User

# Maximum number of active tokens per user
MAX_TOKENS_PER_USER = 50


class APITokenService(BaseService):
    """Service for handling API token management operations.

    This service provides business logic for creating, listing, updating,
    and revoking API tokens. All operations verify user ownership.
    """

    def __init__(self, session: Session):
        """Initialize API token service."""
        super().__init__(session)
        self.api_token_repository = APITokenRepository(session)

    def create_token(
        self,
        user: User,
        data: APITokenCreate,
    ) -> APITokenCreateResponse:
        """Create a new API token for a user.

        IMPORTANT: The returned response contains the full token value.
        This is the ONLY time the token is shown - it cannot be retrieved later.

        Args:
            user: The authenticated user creating the token.
            data: Token creation data (name, scopes, expiration).

        Returns:
            APITokenCreateResponse with the full token (shown once!).

        Raises:
            HTTPException: If token limit exceeded or creation fails.
        """
        # Check token limit
        active_count = self.api_token_repository.count_user_tokens(user.id)
        if active_count >= MAX_TOKENS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum number of API tokens ({MAX_TOKENS_PER_USER}) reached. "
                "Please revoke unused tokens before creating new ones.",
            )

        # Generate the token
        full_token, token_hash, token_prefix = generate_api_token()

        # Ensure hash doesn't already exist (extremely unlikely)
        if self.api_token_repository.hash_exists(token_hash):
            # Regenerate if collision (practically impossible)
            full_token, token_hash, token_prefix = generate_api_token()
            if self.api_token_repository.hash_exists(token_hash):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate unique token. Please try again.",
                )

        # Convert scopes to string list
        scopes = [scope.value for scope in data.scopes]

        # Create the token record
        token_model = self.api_token_repository.create_token(
            user_id=user.id,
            name=data.name,
            token_prefix=token_prefix,
            token_hash=token_hash,
            scopes=scopes,
            expires_at=data.expires_at,
        )

        if token_model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create API token. Please try again.",
            )

        # Build response with the full token (only shown this once!)
        base_token = APIToken.model_validate(token_model)
        return APITokenCreateResponse(**base_token.model_dump(), token=full_token)

    def list_tokens(
        self,
        user: User,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> APITokenListResponse:
        """List all API tokens for a user.

        Args:
            user: The authenticated user.
            include_inactive: Whether to include revoked tokens.
            skip: Number of records to skip (pagination).
            limit: Maximum number of records to return.

        Returns:
            APITokenListResponse with list of tokens and total count.
        """
        token_models = self.api_token_repository.get_user_tokens(
            user_id=user.id,
            include_inactive=include_inactive,
            skip=skip,
            limit=limit,
        )

        tokens = [APIToken.model_validate(model) for model in token_models]

        total = self.api_token_repository.count_user_tokens(
            user.id, active_only=not include_inactive
        )

        return APITokenListResponse(tokens=tokens, total=total)

    def get_token(self, user: User, token_id: int) -> APIToken:
        """Get a single API token by ID.

        Args:
            user: The authenticated user.
            token_id: The token ID.

        Returns:
            APIToken if found and owned by user.

        Raises:
            HTTPException: If token not found or not owned by user.
        """
        token_model = self.api_token_repository.get_by_id_for_user(token_id, user.id)

        if token_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found",
            )

        return APIToken.model_validate(token_model)

    def update_token(
        self,
        user: User,
        token_id: int,
        data: APITokenUpdate,
    ) -> APIToken:
        """Update an API token's name.

        Only the name can be updated. Scopes and expiration cannot be
        changed after creation for security reasons.

        Args:
            user: The authenticated user.
            token_id: The token ID.
            data: Update data (name only).

        Returns:
            Updated APIToken.

        Raises:
            HTTPException: If token not found or not owned by user.
        """
        token_model = self.api_token_repository.update_name(
            token_id=token_id,
            user_id=user.id,
            name=data.name,
        )

        if token_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found",
            )

        return APIToken.model_validate(token_model)

    def revoke_token(self, user: User, token_id: int) -> None:
        """Revoke an API token (soft delete).

        The token becomes immediately unusable but is kept for audit purposes.

        Args:
            user: The authenticated user.
            token_id: The token ID.

        Raises:
            HTTPException: If token not found or not owned by user.
        """
        success = self.api_token_repository.revoke(token_id, user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found",
            )

    def delete_token(self, user: User, token_id: int) -> None:
        """Permanently delete an API token.

        This is a hard delete - the token record is removed entirely.
        Consider using revoke_token() instead to keep audit trail.

        Args:
            user: The authenticated user.
            token_id: The token ID.

        Raises:
            HTTPException: If token not found or not owned by user.
        """
        success = self.api_token_repository.delete_token(token_id, user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API token not found",
            )
