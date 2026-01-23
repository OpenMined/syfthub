"""Endpoint management business logic service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from fastapi import HTTPException, status

from syfthub.core.url_builder import transform_connection_urls
from syfthub.repositories.endpoint import EndpointRepository, EndpointStarRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.endpoint import (
    RESERVED_SLUGS,
    Endpoint,
    EndpointAdminUpdate,
    EndpointCreate,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointType,
    EndpointUpdate,
    EndpointVisibility,
    SyncEndpointsResponse,
    SyncValidationError,
    generate_slug_from_name,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User

logger = logging.getLogger(__name__)


class EndpointService(BaseService):
    """Endpoint service for handling endpoint operations."""

    def __init__(self, session: Session):
        """Initialize endpoint service."""
        super().__init__(session)
        self.endpoint_repository = EndpointRepository(session)
        self.star_repository = EndpointStarRepository(session)
        self.org_member_repository = OrganizationMemberRepository(session)
        self.org_repository = OrganizationRepository(session)
        self.user_repository = UserRepository(session)

    def _get_owner_domain(self, endpoint: Endpoint) -> str | None:
        """Get the domain for an endpoint's owner (user or organization)."""
        if endpoint.user_id:
            user = self.user_repository.get_by_id(endpoint.user_id)
            return user.domain if user else None
        elif endpoint.organization_id:
            org = self.org_repository.get_by_id(endpoint.organization_id)
            return org.domain if org else None
        return None

    def _to_response_with_urls(self, endpoint: Endpoint) -> EndpointResponse:
        """Convert Endpoint to EndpointResponse with transformed URLs."""
        domain = self._get_owner_domain(endpoint)

        # Transform connection URLs
        transformed_connect = transform_connection_urls(
            domain,
            [c.model_dump() for c in endpoint.connect] if endpoint.connect else [],
        )

        # Create response with transformed connections
        endpoint_dict = endpoint.model_dump()
        endpoint_dict["connect"] = transformed_connect
        return EndpointResponse.model_validate(endpoint_dict)

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

        # Auto-add the creating user as contributor if not already included
        # This ensures every endpoint has at least one contributor (the creator)
        if current_user and current_user.id not in valid_contributors:
            valid_contributors.append(current_user.id)

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
            type=endpoint_data.type,
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

        return self._to_response_with_urls(endpoint)

    def get_endpoint_by_user_and_slug(
        self, user_id: int, slug: str
    ) -> Optional[Endpoint]:
        """Get endpoint by user and slug."""
        return self.endpoint_repository.get_by_user_and_slug(user_id, slug)

    def endpoint_exists_for_user(self, slug: str, current_user: User) -> bool:
        """Check if endpoint exists for user."""
        endpoint = self.endpoint_repository.get_by_user_and_slug(current_user.id, slug)
        return endpoint is not None

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
        """Get user's endpoints with proper access control, search, and transformed URLs."""
        endpoints = self.endpoint_repository.get_user_endpoints(
            user_id, skip, limit, visibility, search
        )

        accessible_endpoints = []
        for endpoint in endpoints:
            if self._can_access_endpoint(endpoint, current_user, "user"):
                accessible_endpoints.append(self._to_response_with_urls(endpoint))

        return accessible_endpoints

    def get_organization_endpoints(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 10,
        visibility: Optional[EndpointVisibility] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointResponse]:
        """Get organization's endpoints with proper access control and transformed URLs."""
        endpoints = self.endpoint_repository.get_organization_endpoints(
            org_id, skip, limit, visibility
        )

        accessible_endpoints = []
        for endpoint in endpoints:
            if self._can_access_endpoint(endpoint, current_user, "organization"):
                accessible_endpoints.append(self._to_response_with_urls(endpoint))

        return accessible_endpoints

    def get_public_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointPublicResponse]:
        """Get public endpoints."""
        return self.endpoint_repository.get_public_endpoints(skip, limit, endpoint_type)

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
            # Ensure at least one contributor exists (the user performing the update)
            # For user-owned endpoints, the owner should always be included
            # For org-owned endpoints, ensure the updating user is included if list would be empty
            if endpoint.user_id and endpoint.user_id not in valid_contributors:
                valid_contributors.append(endpoint.user_id)
            elif not endpoint.user_id and current_user.id not in valid_contributors:
                # Org-owned endpoint: ensure at least the updating user is a contributor
                valid_contributors.append(current_user.id)
            endpoint_data.contributors = valid_contributors

        updated_endpoint = self.endpoint_repository.update_endpoint(
            endpoint_id, endpoint_data
        )
        if not updated_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint",
            )

        return self._to_response_with_urls(updated_endpoint)

    def update_endpoint_by_slug(
        self, endpoint_slug: str, endpoint_data: EndpointUpdate, current_user: User
    ) -> EndpointResponse:
        """Update endpoint by slug."""
        endpoint = self.endpoint_repository.get_by_user_and_slug(
            current_user.id, endpoint_slug
        )
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        if not self._can_modify_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        # Validate contributors if they are being updated
        if endpoint_data.contributors is not None:
            valid_contributors = self._validate_contributors(endpoint_data.contributors)
            # Ensure at least one contributor exists (the user performing the update)
            # For user-owned endpoints, the owner should always be included
            # For org-owned endpoints, ensure the updating user is included if list would be empty
            if endpoint.user_id and endpoint.user_id not in valid_contributors:
                valid_contributors.append(endpoint.user_id)
            elif not endpoint.user_id and current_user.id not in valid_contributors:
                # Org-owned endpoint: ensure at least the updating user is a contributor
                valid_contributors.append(current_user.id)
            endpoint_data.contributors = valid_contributors

        updated_endpoint = self.endpoint_repository.update_endpoint(
            endpoint.id, endpoint_data
        )
        if not updated_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint",
            )

        return self._to_response_with_urls(updated_endpoint)

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

        return self._to_response_with_urls(updated_endpoint)

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
        self,
        skip: int = 0,
        limit: int = 10,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointPublicResponse]:
        """List public endpoints - router-compatible wrapper."""
        return self.get_public_endpoints(
            skip=skip, limit=limit, endpoint_type=endpoint_type
        )

    def list_trending_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        min_stars: Optional[int] = None,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointPublicResponse]:
        """List trending public endpoints sorted by stars count with optional min_stars filter."""
        return self.endpoint_repository.get_trending_endpoints(
            skip, limit, min_stars, endpoint_type
        )

    def get_endpoint(self, endpoint_id: int, current_user: User) -> EndpointResponse:
        """Get endpoint by ID with access control and transformed URLs."""
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Determine owner type
        owner_type = "organization" if endpoint.organization_id else "user"

        # Check permissions
        if not self._can_access_endpoint(endpoint, current_user, owner_type):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Hide existence for security
                detail="Endpoint not found",
            )

        return self._to_response_with_urls(endpoint)

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

    def delete_endpoint_by_slug(self, endpoint_slug: str, current_user: User) -> bool:
        """Delete endpoint by slug."""
        endpoint = self.endpoint_repository.get_by_user_and_slug(
            current_user.id, endpoint_slug
        )
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        if not self._can_modify_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        success = self.endpoint_repository.delete_endpoint(endpoint.id)
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

    # ===========================================
    # SYNC OPERATIONS
    # ===========================================

    def _generate_unique_slug_for_batch(
        self,
        name: str,
        used_slugs: set[str],
    ) -> str:
        """Generate unique slug within a batch (no DB check needed).

        For sync operations, we're replacing all endpoints, so we only need
        to ensure uniqueness within the batch itself.

        Args:
            name: The endpoint name to generate slug from
            used_slugs: Set of slugs already used in this batch

        Returns:
            A unique slug for this batch
        """
        base_slug = generate_slug_from_name(name)

        # If base slug is available and not reserved, use it
        if base_slug not in used_slugs and base_slug not in RESERVED_SLUGS:
            return base_slug

        # Append counter until unique
        counter = 1
        while counter < 1000:
            new_slug = f"{base_slug}-{counter}"
            if (
                len(new_slug) <= 63
                and new_slug not in used_slugs
                and new_slug not in RESERVED_SLUGS
            ):
                return new_slug
            counter += 1

        # Fallback: timestamp suffix
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
        return f"{base_slug[:50]}-{timestamp}"

    def _validate_sync_batch(
        self,
        endpoints_data: List[EndpointCreate],
        current_user: User,
    ) -> tuple[List[dict[str, Any]], List[SyncValidationError]]:
        """Validate a batch of endpoints for sync operation.

        Performs all validation BEFORE any database changes:
        - Generates slugs for endpoints without explicit slugs
        - Checks for duplicate slugs within the batch
        - Checks for reserved slugs
        - Validates contributors

        Args:
            endpoints_data: List of EndpointCreate objects to validate
            current_user: The user performing the sync

        Returns:
            Tuple of (validated_endpoints, validation_errors)
            - validated_endpoints: List of dicts ready for database insertion
            - validation_errors: List of SyncValidationError objects
        """
        validation_errors: List[SyncValidationError] = []
        validated_endpoints: List[dict[str, Any]] = []
        used_slugs: set[str] = set()

        for index, endpoint_data in enumerate(endpoints_data):
            # Determine the slug
            if endpoint_data.slug:
                slug = endpoint_data.slug.lower()

                # Check reserved slugs
                if slug in RESERVED_SLUGS:
                    validation_errors.append(
                        SyncValidationError(
                            index=index,
                            field="slug",
                            error=f"'{slug}' is a reserved slug and cannot be used",
                        )
                    )
                    continue
            else:
                # Auto-generate slug
                slug = self._generate_unique_slug_for_batch(
                    endpoint_data.name, used_slugs
                )

            # Check for duplicate within batch
            if slug in used_slugs:
                validation_errors.append(
                    SyncValidationError(
                        index=index,
                        field="slug",
                        error=f"Duplicate slug '{slug}' in batch (first occurrence takes precedence)",
                    )
                )
                continue

            # Mark slug as used
            used_slugs.add(slug)

            # Validate contributors
            valid_contributors = self._validate_contributors(
                endpoint_data.contributors or []
            )
            # Always add current user as contributor
            if current_user.id not in valid_contributors:
                valid_contributors.append(current_user.id)

            # Prepare the validated endpoint data
            validated_endpoint = {
                "name": endpoint_data.name,
                "slug": slug,
                "description": endpoint_data.description or "",
                "type": endpoint_data.type.value,
                "visibility": endpoint_data.visibility.value,
                "version": endpoint_data.version,
                "readme": endpoint_data.readme or "",
                "tags": endpoint_data.tags or [],
                "contributors": valid_contributors,
                "policies": [p.model_dump() for p in endpoint_data.policies],
                "connect": [c.model_dump() for c in endpoint_data.connect],
            }
            validated_endpoints.append(validated_endpoint)

        return validated_endpoints, validation_errors

    def sync_user_endpoints(
        self,
        endpoints_data: List[EndpointCreate],
        current_user: User,
    ) -> SyncEndpointsResponse:
        """Synchronize user's endpoints with provided list.

        This operation is ATOMIC: either all endpoints are synced, or none are.
        It replaces ALL user-owned endpoints with the provided list.

        Organization endpoints are NOT affected.

        Flow:
        1. Validate all endpoints in the batch (no DB changes)
        2. If validation fails, return 400 with ALL errors
        3. Delete all existing user endpoints
        4. Create all new endpoints
        5. Commit transaction
        6. Return sync results

        Args:
            endpoints_data: List of endpoint specifications to sync
            current_user: The authenticated user performing the sync

        Returns:
            SyncEndpointsResponse with sync results

        Raises:
            HTTPException: 400 if validation fails, 500 if database error
        """
        logger.info(
            f"Sync requested by user {current_user.id} ({current_user.username}) "
            f"with {len(endpoints_data)} endpoints"
        )

        # Phase 1: Validation (no DB changes)
        validated_endpoints, validation_errors = self._validate_sync_batch(
            endpoints_data, current_user
        )

        if validation_errors:
            logger.warning(
                f"Sync validation failed for user {current_user.id}: "
                f"{len(validation_errors)} errors"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"Batch validation failed with {len(validation_errors)} error(s)",
                    "errors": [e.model_dump() for e in validation_errors],
                },
            )

        # Phase 2: Atomic database operation
        try:
            # Delete all existing user endpoints
            deleted_count = self.endpoint_repository.delete_all_user_endpoints(
                current_user.id
            )

            # Create all new endpoints
            if validated_endpoints:
                created_endpoints = self.endpoint_repository.bulk_create_endpoints(
                    validated_endpoints, current_user.id
                )
            else:
                created_endpoints = []

            # Commit the transaction (delete + creates)
            self.session.commit()

            logger.info(
                f"Sync completed for user {current_user.id}: "
                f"deleted={deleted_count}, created={len(created_endpoints)}"
            )

            # Transform URLs for response
            response_endpoints = [
                self._to_response_with_urls(ep) for ep in created_endpoints
            ]

            return SyncEndpointsResponse(
                synced=len(created_endpoints),
                deleted=deleted_count,
                endpoints=response_endpoints,
            )

        except Exception as e:
            # Rollback on any error
            self.session.rollback()
            logger.error(
                f"Sync failed for user {current_user.id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "SYNC_FAILED",
                    "message": "Failed to sync endpoints. Transaction rolled back.",
                },
            ) from e
