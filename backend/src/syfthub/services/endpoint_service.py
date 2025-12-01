"""Endpoint management business logic service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from fastapi import HTTPException, status

from syfthub.repositories.endpoint import EndpointRepository, EndpointStarRepository
from syfthub.repositories.organization import OrganizationMemberRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.endpoint import (
    RESERVED_SLUGS,
    Endpoint,
    EndpointAdminUpdate,
    EndpointCreate,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointUpdate,
    EndpointVisibility,
    generate_slug_from_name,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


class EndpointService(BaseService):
    """Endpoint service for handling endpoint operations."""

    def __init__(self, session: Session):
        """Initialize endpoint service."""
        super().__init__(session)
        self.endpoint_repository = EndpointRepository(session)
        self.star_repository = EndpointStarRepository(session)
        self.org_member_repository = OrganizationMemberRepository(session)
        self.user_repository = UserRepository(session)

    def _is_slug_available(
        self,
        slug: str,
        user_id: int,
        exclude_endpoint_id: Optional[int] = None,
    ) -> bool:
        """Check if a slug is available for a user."""
        if slug in RESERVED_SLUGS:
            return False

        # Use repository to check if slug exists for user
        exists = self.endpoint_repository.slug_exists_for_user(
            user_id, slug, exclude_endpoint_id
        )
        return not exists

    def _generate_unique_slug(
        self,
        name: str,
        owner_id: int,
        is_organization: bool = False,
    ) -> str:
        """Generate a unique slug for a user or organization."""
        base_slug = generate_slug_from_name(name)

        # Check if base slug is available
        if is_organization:
            slug_available = not self.endpoint_repository.slug_exists_for_organization(
                owner_id, base_slug
            )
        else:
            slug_available = self._is_slug_available(base_slug, owner_id)

        if slug_available:
            return base_slug

        # If base slug is taken, append numbers
        counter = 1
        while counter < 1000:  # Prevent infinite loops
            new_slug = f"{base_slug}-{counter}"
            if len(new_slug) <= 63:
                if is_organization:
                    if not self.endpoint_repository.slug_exists_for_organization(
                        owner_id, new_slug
                    ):
                        return new_slug
                else:
                    if self._is_slug_available(new_slug, owner_id):
                        return new_slug
            counter += 1

        # Fallback: use timestamp
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
        return f"{base_slug[:50]}-{timestamp}"

    def _validate_contributors(self, contributor_ids: List[int]) -> List[int]:
        """Validate that contributor user IDs exist and are active."""
        if not contributor_ids:
            return []

        # Remove duplicates while preserving order
        unique_ids = []
        seen = set()
        for user_id in contributor_ids:
            if user_id not in seen:
                unique_ids.append(user_id)
                seen.add(user_id)

        # Validate each user ID exists and is active
        valid_contributors = []
        for user_id in unique_ids:
            user = self.user_repository.get_by_id(user_id)
            if user and user.is_active:
                valid_contributors.append(user_id)
            else:
                # Log warning but don't fail - just skip invalid contributors
                continue

        return valid_contributors

    def create_endpoint(
        self,
        endpoint_data: EndpointCreate,
        owner_id: int,
        is_organization: bool = False,
        current_user: Optional[User] = None,
    ) -> EndpointResponse:
        """Create a new endpoint."""
        # Validate permissions for organization endpoints
        if (
            is_organization
            and current_user
            and not self.org_member_repository.is_member(owner_id, current_user.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: not a member of organization",
            )

        # Validate and sanitize contributors
        valid_contributors = self._validate_contributors(endpoint_data.contributors)

        # Auto-add owner as contributor if not already included
        if not is_organization and owner_id not in valid_contributors:
            valid_contributors.append(owner_id)

        # Auto-generate slug if not provided
        final_slug = endpoint_data.slug
        if final_slug is None:
            final_slug = self._generate_unique_slug(
                endpoint_data.name, owner_id, is_organization
            )

        if is_organization:
            if self.endpoint_repository.slug_exists_for_organization(
                owner_id, final_slug
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Endpoint slug already exists for this organization",
                )
        else:
            if self.endpoint_repository.slug_exists_for_user(owner_id, final_slug):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="slug already exists - already taken",
                )

        # Create a validated endpoint creation object that includes server-managed fields
        validated_data = EndpointCreate(
            name=endpoint_data.name,
            description=endpoint_data.description,
            visibility=endpoint_data.visibility,
            version=endpoint_data.version,
            readme=endpoint_data.readme,
            policies=endpoint_data.policies,
            connect=endpoint_data.connect,
            slug=final_slug,
            contributors=valid_contributors,
        )

        # Create endpoint with validated data
        endpoint = self.endpoint_repository.create_endpoint(
            validated_data, owner_id, is_organization
        )

        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create endpoint",
            )

        return EndpointResponse.model_validate(endpoint)

    def get_endpoint_by_user_and_slug(
        self, user_id: int, slug: str
    ) -> Optional[Endpoint]:
        """Get endpoint by user and slug."""
        return self.endpoint_repository.get_by_user_and_slug(user_id, slug)

    def get_endpoint_by_org_and_slug(
        self, org_id: int, slug: str
    ) -> Optional[Endpoint]:
        """Get endpoint by organization and slug."""
        return self.endpoint_repository.get_by_organization_and_slug(org_id, slug)

    def get_user_endpoints(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
        search: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointResponse]:
        """Get user's endpoints with proper access control and search."""
        endpoints = self.endpoint_repository.get_user_endpoints(
            user_id, skip, limit, visibility, search
        )

        accessible_endpoints = []
        for endpoint in endpoints:
            if self._can_access_endpoint(endpoint, current_user, "user"):
                if self._can_see_full_details(endpoint, current_user, "user"):
                    accessible_endpoints.append(
                        EndpointResponse.model_validate(endpoint)
                    )
                else:
                    accessible_endpoints.append(
                        EndpointResponse.model_validate(endpoint)
                    )

        return accessible_endpoints

    def get_organization_endpoints(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointResponse]:
        """Get organization's endpoints with proper access control."""
        endpoints = self.endpoint_repository.get_organization_endpoints(
            org_id, skip, limit, visibility
        )

        accessible_endpoints = []
        for endpoint in endpoints:
            if self._can_access_endpoint(endpoint, current_user, "organization"):
                if self._can_see_full_details(endpoint, current_user, "organization"):
                    accessible_endpoints.append(
                        EndpointResponse.model_validate(endpoint)
                    )
                else:
                    accessible_endpoints.append(
                        EndpointResponse.model_validate(endpoint)
                    )

        return accessible_endpoints

    def get_public_endpoints(
        self, skip: int = 0, limit: int = 10
    ) -> List[EndpointPublicResponse]:
        """Get public endpoints."""
        return self.endpoint_repository.get_public_endpoints(skip, limit)

    def update_endpoint(
        self, endpoint_id: int, endpoint_data: EndpointUpdate, current_user: User
    ) -> EndpointResponse:
        """Update endpoint."""
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Check permissions
        if not self._can_modify_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        # Validate contributors if they are being updated
        if endpoint_data.contributors is not None:
            valid_contributors = self._validate_contributors(endpoint_data.contributors)
            # Ensure the owner is always included as a contributor
            if endpoint.user_id and endpoint.user_id not in valid_contributors:
                valid_contributors.append(endpoint.user_id)
            endpoint_data.contributors = valid_contributors

        updated_endpoint = self.endpoint_repository.update_endpoint(
            endpoint_id, endpoint_data
        )
        if not updated_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint",
            )

        return EndpointResponse.model_validate(updated_endpoint)

    def admin_update_endpoint(
        self, endpoint_id: int, admin_data: EndpointAdminUpdate, current_user: User
    ) -> EndpointResponse:
        """Admin-only endpoint updates for server-managed fields."""
        # Verify admin role (redundant with endpoint check, but defensive)
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )

        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Use repository's admin update method (need to add this)
        updated_endpoint = self.endpoint_repository.admin_update_endpoint(
            endpoint_id, admin_data
        )
        if not updated_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint",
            )

        return EndpointResponse.model_validate(updated_endpoint)

    # Router-compatible methods
    def list_user_endpoints(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
        search: Optional[str] = None,
    ) -> List[EndpointResponse]:
        """List current user's endpoints - router-compatible wrapper."""
        return self.get_user_endpoints(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            visibility=visibility,
            search=search,
            current_user=current_user,
        )

    def list_public_endpoints(
        self, skip: int = 0, limit: int = 10
    ) -> List[EndpointPublicResponse]:
        """List public endpoints - router-compatible wrapper."""
        return self.get_public_endpoints(skip=skip, limit=limit)

    def list_trending_endpoints(
        self, skip: int = 0, limit: int = 10, min_stars: Optional[int] = None
    ) -> List[EndpointPublicResponse]:
        """List trending public endpoints sorted by stars count with optional min_stars filter."""
        return self.endpoint_repository.get_trending_endpoints(skip, limit, min_stars)

    def get_endpoint(self, endpoint_id: int, current_user: User) -> EndpointResponse:
        """Get endpoint by ID with access control."""
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Check permissions
        if not self._can_access_endpoint(endpoint, current_user, "user"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Hide existence for security
                detail="Endpoint not found",
            )

        return EndpointResponse.model_validate(endpoint)

    def delete_endpoint(self, endpoint_id: int, current_user: User) -> bool:
        """Delete endpoint."""
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Check permissions
        if not self._can_modify_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        success = self.endpoint_repository.delete_endpoint(endpoint_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete endpoint",
            )

        return True

    def star_endpoint(self, endpoint_id: int, current_user: User) -> bool:
        """Star a endpoint."""
        # Check if endpoint exists and is accessible
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        owner_type = "organization" if endpoint.organization_id else "user"
        if not self._can_access_endpoint(endpoint, current_user, owner_type):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Add star
        success = self.star_repository.star_endpoint(current_user.id, endpoint_id)
        if success:
            self.endpoint_repository.increment_stars(endpoint_id)

        return success

    def unstar_endpoint(self, endpoint_id: int, current_user: User) -> bool:
        """Unstar a endpoint."""
        success = self.star_repository.unstar_endpoint(current_user.id, endpoint_id)
        if success:
            self.endpoint_repository.decrement_stars(endpoint_id)

        return success

    def is_endpoint_starred(self, endpoint_id: int, current_user: User) -> bool:
        """Check if user has starred a endpoint."""
        return self.star_repository.is_starred(current_user.id, endpoint_id)

    def _can_access_endpoint(
        self, endpoint: Endpoint, current_user: Optional[User], owner_type: str
    ) -> bool:
        """Check if user can access endpoint."""
        # Public endpoints are always accessible
        if endpoint.visibility == EndpointVisibility.PUBLIC:
            return True

        # Unauthenticated users can only see public endpoints
        if current_user is None:
            return False

        # Admin can access everything
        if current_user.role == "admin":
            return True

        # For user-owned endpoints
        if owner_type == "user" and endpoint.user_id:
            # Owner can always access
            if endpoint.user_id == current_user.id:
                return True
            # Internal endpoints are accessible to any authenticated user
            # Private endpoints are only accessible to owner
            return endpoint.visibility == EndpointVisibility.INTERNAL

        # For organization-owned endpoints
        if owner_type == "organization" and endpoint.organization_id:
            if endpoint.visibility == EndpointVisibility.INTERNAL:
                return self.org_member_repository.is_member(
                    endpoint.organization_id, current_user.id
                )
            if endpoint.visibility == EndpointVisibility.PRIVATE:
                return self.org_member_repository.is_member(
                    endpoint.organization_id, current_user.id
                )

        return False

    def _can_see_full_details(
        self, endpoint: Endpoint, current_user: Optional[User], owner_type: str
    ) -> bool:
        """Check if user can see full endpoint details."""
        if current_user is None:
            return endpoint.visibility == EndpointVisibility.PUBLIC

        if current_user.role == "admin":
            return True

        # For user-owned endpoints
        if owner_type == "user" and endpoint.user_id:
            return endpoint.user_id == current_user.id

        # For organization-owned endpoints
        if owner_type == "organization" and endpoint.organization_id:
            return self.org_member_repository.is_member(
                endpoint.organization_id, current_user.id
            )

        return endpoint.visibility == EndpointVisibility.PUBLIC

    def _can_modify_endpoint(self, endpoint: Endpoint, current_user: User) -> bool:
        """Check if user can modify endpoint."""
        if current_user.role == "admin":
            return True

        # For user-owned endpoints
        if endpoint.user_id:
            return endpoint.user_id == current_user.id

        # For organization-owned endpoints
        if endpoint.organization_id:
            member_role = self.org_member_repository.get_member_role(
                endpoint.organization_id, current_user.id
            )
            from syfthub.schemas.organization import OrganizationRole

            return member_role in [OrganizationRole.OWNER, OrganizationRole.ADMIN]

        return False
