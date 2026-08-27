"""Endpoint management business logic service."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional
from urllib.parse import urlparse

from fastapi import HTTPException, status

from syfthub.core.config import settings
from syfthub.core.url_builder import transform_connection_urls
from syfthub.domain.base_url import TUNNELING_PREFIX
from syfthub.repositories.endpoint import EndpointRepository, EndpointStarRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.endpoint import (
    CLUSTER_POLICY_TYPE,
    PREPAID_POLICY_TYPES,
    RESERVED_SLUGS,
    Endpoint,
    EndpointAdminUpdate,
    EndpointCreate,
    EndpointHealthItem,
    EndpointHealthResponse,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointType,
    EndpointUpdate,
    EndpointUptimeResponse,
    EndpointVisibility,
    GroupedEndpointsResponse,
    OwnersListResponse,
    Policy,
    SyncEndpointsResponse,
    SyncValidationError,
    UptimeBucket,
    filter_visible_policies,
    generate_slug_from_name,
    get_matching_types,
)
from syfthub.schemas.search import EndpointSearchResponse, EndpointSearchResult
from syfthub.services.base import BaseService
from syfthub.services.rag_service import RAGService, get_rag_service
from syfthub.services.satellite_service import SatelliteService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User

logger = logging.getLogger(__name__)


def _viewer_email(user: Optional[User]) -> Optional[str]:
    return user.email if user else None


class EndpointService(BaseService):
    """Endpoint service for handling endpoint operations."""

    def __init__(self, session: Session):
        """Initialize endpoint service."""
        super().__init__(session)
        self.endpoint_repository = EndpointRepository(session)
        self.star_repository = EndpointStarRepository(session)
        self.user_repository = UserRepository(session)
        self.satellite_service = SatelliteService(session)
        self.rag_service: RAGService = get_rag_service()

    def _get_owner_domain(self, endpoint: Endpoint) -> str | None:
        """Get the domain for an endpoint's owner."""
        user = self.user_repository.get_by_id(endpoint.user_id)
        return user.domain if user else None

    def _to_response_with_urls(
        self,
        endpoint: Endpoint,
        owner_domain: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> EndpointResponse:
        """Convert Endpoint to EndpointResponse with transformed URLs.

        Args:
            endpoint: The endpoint model to convert.
            owner_domain: Pre-fetched owner domain. When provided, skips the
                per-endpoint DB lookup (use in listing methods to avoid N+1).
            current_user: The authenticated viewer. Used to filter policies
                whose `config.applied_to` does not include the viewer.
        """
        domain = (
            owner_domain
            if owner_domain is not None
            else self._get_owner_domain(endpoint)
        )

        # Transform connection URLs
        transformed_connect = transform_connection_urls(
            domain,
            [c.model_dump() for c in endpoint.connect] if endpoint.connect else [],
        )

        viewer_email = current_user.email if current_user else None

        endpoint_dict = endpoint.model_dump()
        endpoint_dict["connect"] = transformed_connect
        endpoint_dict["policies"] = filter_visible_policies(
            endpoint_dict.get("policies") or [], viewer_email
        )
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
    ) -> str:
        """Generate a unique slug for a user."""
        base_slug = generate_slug_from_name(name)

        # Check if base slug is available
        if self._is_slug_available(base_slug, owner_id):
            return base_slug

        # If base slug is taken, append numbers
        counter = 1
        while counter < 1000:  # Prevent infinite loops
            new_slug = f"{base_slug}-{counter}"
            if len(new_slug) <= 63 and self._is_slug_available(new_slug, owner_id):
                return new_slug
            counter += 1

        # Fallback: use timestamp
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-6:]
        return f"{base_slug[:50]}-{timestamp}"

    def _validate_contributors(self, contributor_ids: List[int]) -> List[int]:
        """Validate that contributor user IDs exist and are active.

        Uses a single batch query instead of N individual lookups.
        """
        if not contributor_ids:
            return []

        # Remove duplicates while preserving order
        seen: set[int] = set()
        unique_ids: List[int] = []
        for uid in contributor_ids:
            if uid not in seen:
                unique_ids.append(uid)
                seen.add(uid)

        # Batch fetch all users in one query
        users = self.user_repository.get_by_ids(unique_ids)
        active_ids = {u.id for u in users if u.is_active}

        return [uid for uid in unique_ids if uid in active_ids]

    @staticmethod
    def _inject_prepaid_tag(tags: list[str], policies: list[Policy]) -> list[str]:
        """Inject 'prepaid' tag if a prepaid-credits policy is present.

        Uses the same traversal as cluster validation and billing
        classification, so a prepaid policy nested inside a composite
        wrapper tags the endpoint exactly like a top-level one, and a
        disabled policy never does.

        Silently skips if the tags list already has 10 or more entries and
        'prepaid' is not present (preserves the 10-tag soft limit for
        user-supplied tags without rejecting the request).
        """
        has_prepaid_policy = any(
            ptype.lower() in PREPAID_POLICY_TYPES
            for ptype, _ in EndpointService._iter_policy_configs(policies)
        )
        if has_prepaid_policy and "prepaid" not in tags:
            if len(tags) >= 10:
                return tags
            return [*tags, "prepaid"]
        return tags

    @staticmethod
    def _iter_policy_configs(policies: Any) -> Any:
        """Yield ``(type, config)`` for every enabled policy, wrappers included.

        Accepts both shapes a policy arrives in: validated ``Policy`` models
        (top-level entries) and raw dicts (children that composite policies
        nest under ``config["policies"]``). Composite wrappers (``all_of`` /
        ``any_of`` / …) are yielded too, then descended into — consumers
        filter on ``type``, so wrapper entries are inert to them.

        The parent is yielded even when it has children: a policy can carry
        a billing ``type`` *and* a nested ``policies`` list, and consumers
        that read policies at the top level would treat it as live billing —
        skipping it here would let a publisher dodge cluster validation by
        attaching a dummy child list. A disabled policy (or wrapper) skips
        its whole subtree.

        Yielded configs are the live dicts: mutating one mutates the policy
        that will be stored.
        """
        for policy in policies or []:
            if isinstance(policy, dict):
                ptype = policy.get("type", "")
                enabled = policy.get("enabled", True)
                config = policy.get("config") or {}
            else:
                ptype = policy.type
                enabled = policy.enabled
                config = policy.config
            if not enabled or not isinstance(config, dict):
                continue
            yield str(ptype), config
            children = config.get("policies")
            if isinstance(children, list) and children:
                yield from EndpointService._iter_policy_configs(children)

    @staticmethod
    def _host_under_domain(url: str, domain_host: str) -> bool:
        """Whether ``url``'s host equals or is a subdomain of ``domain_host``.

        ``domain_host`` must be a bare lowercase hostname (no scheme or port).
        For ``domain_host="spaces.openmined.org"``:

        - ``https://spaces.openmined.org/api/...`` → True (exact match)
        - ``https://wallet.spaces.openmined.org/...`` → True (subdomain)
        - ``https://spaces.openmined.org.evil.com/...`` → False
        """
        host = (urlparse(url).hostname or "").lower()
        return bool(host) and (host == domain_host or host.endswith("." + domain_host))

    # Server-owned: names the satellite-token audience and is derived from the
    # verified ``wallet_owner`` id. Publishers never send it (syft-space
    # publishes the id), so any incoming value is dropped on every policy type
    # before validation re-injects the real one.
    _SERVER_OWNED_CONFIG_KEYS = ("wallet_owner_username", "walletOwnerUsername")

    # Legitimately publisher-supplied, but only meaningful under a verified
    # cluster claim; dropped from other prepaid policies (see
    # _process_cluster_policies).
    _CLUSTER_ONLY_CONFIG_KEYS = (
        "wallet_id",
        "walletId",
        "wallet_owner",
        "walletOwner",
    )

    def _process_cluster_policies(self, policies: list[Policy]) -> Optional[str]:
        """Validate ``cluster`` (station-hosted shared wallet) policies in place.

        Runs on every publish path (create, update, sync) before policies are
        stored. A ``cluster`` policy claims its wallet is hosted by another
        Hub account (``wallet_owner``), and buyers' satellite tokens are
        minted for that account — so the claim is verified here, not trusted:

        1. ``wallet_id`` must be a non-empty string.
        2. ``wallet_owner`` must be the id of an existing, active user.
        3. ``payment_url`` and ``credits_url`` (plus ``invoices_url`` when
           present) must be http(s) URLs whose hosts fall under the wallet
           owner's registered ``domain``. This stops a malicious publisher
           from routing buyers' satellite tokens to a host the wallet owner
           doesn't control.

        On success, each cluster config is enriched **in place** with the
        server-derived ``wallet_owner_username`` — the audience the frontend
        mints satellite tokens for. Any client-supplied value is overwritten:
        usernames are mutable and reusable on SyftHub, so the id stays
        canonical and the username is re-derived on every publish. Accepted
        camelCase spellings are rewritten to the canonical snake_case keys,
        so stored configs always have one shape.

        Non-``cluster`` prepaid policies get the wallet identity/audience
        fields **stripped**: the frontend mints satellite tokens for
        ``wallet_owner_username`` whenever it is present on any prepaid
        policy, and self-hosted policy URLs are not domain-verified — left
        in place, a publisher could route tokens minted for an arbitrary
        account to a host they control (token exfiltration).

        Returns:
            The first failed check as a human-readable message (callers
            surface it as a 422 or a sync validation error), or ``None``
            when every cluster policy validates. Endpoints with no cluster
            policy always pass.
        """
        for ptype, config in self._iter_policy_configs(policies):
            # No publisher may name the token audience, on any policy type.
            for key in self._SERVER_OWNED_CONFIG_KEYS:
                config.pop(key, None)

            ptype_lower = ptype.lower()
            if ptype_lower != CLUSTER_POLICY_TYPE:
                if ptype_lower in PREPAID_POLICY_TYPES:
                    for key in self._CLUSTER_ONLY_CONFIG_KEYS:
                        config.pop(key, None)
                continue

            wallet_id = config.get("wallet_id") or config.get("walletId")
            if not isinstance(wallet_id, str) or not wallet_id.strip():
                return "cluster policy requires a non-empty 'wallet_id'"

            raw_owner = config.get("wallet_owner")
            if raw_owner is None:
                raw_owner = config.get("walletOwner")
            if isinstance(raw_owner, str) and raw_owner.isdigit():
                raw_owner = int(raw_owner)
            if not isinstance(raw_owner, int) or isinstance(raw_owner, bool):
                return "cluster policy requires 'wallet_owner' (Hub user id)"

            owner = self.user_repository.get_by_id(raw_owner)
            if owner is None or not owner.is_active:
                return (
                    f"cluster policy 'wallet_owner' {raw_owner} does not "
                    "resolve to an active user"
                )
            if not owner.domain:
                return (
                    f"cluster wallet owner '{owner.username}' has no registered "
                    "domain on SyftHub; the wallet URLs cannot be verified"
                )
            if owner.domain.startswith(TUNNELING_PREFIX):
                # Tunneling spaces have no public hostname, so host-based
                # wallet URL verification can never succeed — reject clearly
                # instead of failing against a bogus "tunneling" host.
                return (
                    f"cluster wallet owner '{owner.username}' uses a tunneling "
                    "domain; cluster wallet URLs require a public http(s) domain"
                )
            domain = owner.domain
            if "://" not in domain:
                domain = f"https://{domain}"
            domain_host = (urlparse(domain).hostname or "").lower()
            if not domain_host:
                return (
                    f"cluster wallet owner '{owner.username}' has an invalid "
                    "registered domain"
                )

            payment_url = config.get("payment_url") or config.get("paymentUrl")
            credits_url = config.get("credits_url") or config.get("creditsUrl")
            invoices_url = config.get("invoices_url") or config.get("invoicesUrl")
            for field_name, url, required in (
                ("payment_url", payment_url, True),
                ("credits_url", credits_url, True),
                ("invoices_url", invoices_url, False),
            ):
                if url is None and not required:
                    continue
                if not isinstance(url, str) or not url.startswith(
                    ("https://", "http://")
                ):
                    return f"cluster policy requires a valid http(s) '{field_name}'"
                if not self._host_under_domain(url, domain_host):
                    return (
                        f"cluster policy '{field_name}' host is not under the "
                        f"wallet owner's registered domain '{domain_host}'"
                    )

            # Canonicalize to snake_case + server-derived enrichment (the
            # frontend uses the username as the satellite-token audience).
            # camelCase spellings are dropped so stored configs have exactly
            # one shape.
            for camel_key in (
                "walletId",
                "walletOwner",
                "walletOwnerUsername",
                "paymentUrl",
                "creditsUrl",
                "invoicesUrl",
            ):
                config.pop(camel_key, None)
            config["wallet_id"] = wallet_id
            config["wallet_owner"] = owner.id
            config["wallet_owner_username"] = owner.username
            config["payment_url"] = payment_url
            config["credits_url"] = credits_url
            if invoices_url is not None:
                config["invoices_url"] = invoices_url

        return None

    def create_endpoint(
        self,
        endpoint_data: EndpointCreate,
        owner_id: int,
        current_user: Optional[User] = None,
        satellite_id: Optional[uuid.UUID] = None,
    ) -> EndpointResponse:
        """Create a new endpoint."""
        # Validate and sanitize contributors
        valid_contributors = self._validate_contributors(endpoint_data.contributors)

        # Auto-add the creating user as contributor if not already included
        # This ensures every endpoint has at least one contributor (the creator)
        if current_user and current_user.id not in valid_contributors:
            valid_contributors.append(current_user.id)

        cluster_error = self._process_cluster_policies(endpoint_data.policies)
        if cluster_error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=cluster_error,
            )

        # Auto-generate slug if not provided
        final_slug = endpoint_data.slug
        if final_slug is None:
            final_slug = self._generate_unique_slug(endpoint_data.name, owner_id)

        if self.endpoint_repository.slug_exists_for_user(owner_id, final_slug):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="slug already exists - already taken",
            )

        final_tags = self._inject_prepaid_tag(
            endpoint_data.tags, endpoint_data.policies
        )

        # Force private visibility for archived endpoints so they vanish from public listings
        effective_visibility = (
            EndpointVisibility.PRIVATE
            if endpoint_data.archived
            else endpoint_data.visibility
        )

        # Create a validated endpoint creation object that includes server-managed fields
        validated_data = EndpointCreate(
            name=endpoint_data.name,
            description=endpoint_data.description,
            type=endpoint_data.type,
            visibility=effective_visibility,
            archived=endpoint_data.archived,
            version=endpoint_data.version,
            readme=endpoint_data.readme,
            tags=final_tags,
            policies=endpoint_data.policies,
            connect=endpoint_data.connect,
            slug=final_slug,
            contributors=valid_contributors,
        )

        # Which satellite serves it. None when the account has registered none,
        # which leaves the endpoint unattached exactly as it would be today.
        satellite = self.satellite_service.resolve_existing(owner_id, satellite_id)

        # Create endpoint with validated data
        endpoint = self.endpoint_repository.create_endpoint(
            validated_data, owner_id, space_id=satellite.id if satellite else None
        )

        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create endpoint",
            )

        # Ingest to RAG if public (best effort - non-blocking)
        if endpoint.visibility == EndpointVisibility.PUBLIC:
            self._ingest_to_rag(endpoint.id)

        return self._to_response_with_urls(endpoint, current_user=current_user)

    def get_endpoint_by_user_and_slug(
        self, user_id: int, slug: str
    ) -> Optional[Endpoint]:
        """Get endpoint by user and slug."""
        return self.endpoint_repository.get_by_user_and_slug(user_id, slug)

    def endpoint_exists_for_user(self, slug: str, current_user: User) -> bool:
        """Check if endpoint exists for user."""
        endpoint = self.endpoint_repository.get_by_user_and_slug(current_user.id, slug)
        return endpoint is not None

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

        # Look up user domain once for all endpoints (avoids N+1)
        user = self.user_repository.get_by_id(user_id)
        user_domain = user.domain if user else None

        accessible_endpoints = []
        for endpoint in endpoints:
            if self._can_access_endpoint(endpoint, current_user):
                accessible_endpoints.append(
                    self._to_response_with_urls(
                        endpoint,
                        owner_domain=user_domain,
                        current_user=current_user,
                    )
                )

        return accessible_endpoints

    def get_public_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        endpoint_type: Optional[EndpointType] = None,
        search: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointPublicResponse]:
        """Get public endpoints with optional search filtering."""
        return self.endpoint_repository.get_public_endpoints(
            skip,
            limit,
            endpoint_type,
            search,
            viewer_email=_viewer_email(current_user),
        )

    def _apply_endpoint_update(
        self, endpoint: Endpoint, endpoint_data: EndpointUpdate, current_user: User
    ) -> EndpointResponse:
        """Apply validated update data to an already-fetched endpoint.

        Shared implementation for update_endpoint and update_endpoint_by_slug.
        Assumes permission check has already been performed by the caller.
        """
        old_visibility = endpoint.visibility.value

        # Validate contributors if they are being updated
        if endpoint_data.contributors is not None:
            valid_contributors = self._validate_contributors(endpoint_data.contributors)
            # Ensure the owner is always included as a contributor
            if endpoint.user_id not in valid_contributors:
                valid_contributors.append(endpoint.user_id)
            endpoint_data.contributors = valid_contributors

        if endpoint_data.policies is not None:
            cluster_error = self._process_cluster_policies(endpoint_data.policies)
            if cluster_error:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=cluster_error,
                )
            effective_tags = (
                endpoint_data.tags
                if endpoint_data.tags is not None
                else (endpoint.tags or [])
            )
            new_tags = self._inject_prepaid_tag(effective_tags, endpoint_data.policies)
            if new_tags != effective_tags:
                endpoint_data.tags = new_tags

        # Force private visibility when archiving
        if endpoint_data.archived:
            endpoint_data.visibility = EndpointVisibility.PRIVATE

        updated_endpoint = self.endpoint_repository.update_endpoint(
            endpoint.id, endpoint_data
        )
        if not updated_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint",
            )

        new_visibility = updated_endpoint.visibility.value
        self._update_rag_on_visibility_change(
            endpoint.id, old_visibility, new_visibility
        )

        return self._to_response_with_urls(updated_endpoint, current_user=current_user)

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

        if not self._can_modify_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied: insufficient permissions",
            )

        return self._apply_endpoint_update(endpoint, endpoint_data, current_user)

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

        return self._apply_endpoint_update(endpoint, endpoint_data, current_user)

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

        return self._to_response_with_urls(updated_endpoint, current_user=current_user)

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
        search: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointPublicResponse]:
        """List public endpoints - router-compatible wrapper."""
        return self.get_public_endpoints(
            skip=skip,
            limit=limit,
            endpoint_type=endpoint_type,
            search=search,
            current_user=current_user,
        )

    def list_public_endpoints_by_owner(
        self,
        owner_slug: str,
        skip: int = 0,
        limit: int = 100,
        current_user: Optional[User] = None,
    ) -> List[EndpointPublicResponse]:
        """List public endpoints for a specific owner.

        Args:
            owner_slug: The username.
            skip: Number of endpoints to skip (for pagination).
            limit: Maximum number of endpoints to return.

        Returns:
            List of EndpointPublicResponse objects for the owner.
        """
        return self.endpoint_repository.get_public_endpoints_by_owner(
            owner_slug=owner_slug,
            skip=skip,
            limit=limit,
            viewer_email=_viewer_email(current_user),
        )

    def get_public_endpoint_by_path(
        self,
        owner_username: str,
        slug: str,
        current_user: Optional[User] = None,
    ) -> EndpointPublicResponse:
        """Get a single public endpoint by owner username and slug.

        Args:
            owner_username: The username of the endpoint owner
            slug: The endpoint slug
            current_user: Optional authenticated viewer for policy personalization

        Returns:
            EndpointPublicResponse

        Raises:
            HTTPException: 404 if endpoint is not found
        """
        endpoint = self.endpoint_repository.get_public_endpoint_by_owner_and_slug(
            owner_username,
            slug,
            viewer_email=_viewer_email(current_user),
        )
        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )
        return endpoint

    def list_trending_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        min_stars: Optional[int] = None,
        endpoint_type: Optional[EndpointType] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointPublicResponse]:
        """List trending public endpoints sorted by stars count with optional min_stars filter."""
        return self.endpoint_repository.get_trending_endpoints(
            skip,
            limit,
            min_stars,
            endpoint_type,
            viewer_email=_viewer_email(current_user),
        )

    def list_guest_accessible_endpoints(
        self,
        skip: int = 0,
        limit: int = 10,
        endpoint_type: Optional[EndpointType] = None,
        current_user: Optional[User] = None,
    ) -> List[EndpointPublicResponse]:
        """List endpoints accessible to guest (unauthenticated) users.

        Guest users can only access endpoints that are:
        - Public visibility
        - Active (is_active=True)
        - Have no policies attached (policies is empty list)

        This ensures guests can only use free, unrestricted endpoints.

        Args:
            skip: Number of endpoints to skip (pagination)
            limit: Maximum number of endpoints to return
            endpoint_type: Optional filter by endpoint type (model or data_source)

        Returns:
            List of EndpointPublicResponse objects for guest-accessible endpoints
        """
        return self.endpoint_repository.get_guest_accessible_endpoints(
            skip=skip,
            limit=limit,
            endpoint_type=endpoint_type,
            viewer_email=_viewer_email(current_user),
        )

    def list_public_endpoints_grouped(
        self,
        max_per_owner: int = 15,
        current_user: Optional[User] = None,
    ) -> GroupedEndpointsResponse:
        """List public endpoints grouped by owner with a limit per owner.

        This method returns endpoints organized by their owner, with at most
        max_per_owner endpoints shown per owner. This prevents a single owner
        with many endpoints from dominating the display (e.g., in Global Directory).

        Args:
            max_per_owner: Maximum number of endpoints to return per owner (default 15)

        Returns:
            GroupedEndpointsResponse with groups ordered by total endpoint count (descending)
        """
        return self.endpoint_repository.get_public_endpoints_grouped(
            max_per_owner=max_per_owner,
            viewer_email=_viewer_email(current_user),
        )

    def list_public_endpoint_owners(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> OwnersListResponse:
        """List owners with public endpoints and their endpoint counts.

        This is an efficient endpoint that returns only owner usernames and
        aggregated counts, without fetching full endpoint data. Optimized
        for CLI directory listing (syft ls).

        Args:
            skip: Number of owners to skip (pagination)
            limit: Maximum number of owners to return

        Returns:
            OwnersListResponse with owner summaries ordered by endpoint count
        """
        from syfthub.schemas.endpoint import OwnersListResponse, OwnerSummary

        owners_data, total_count = self.endpoint_repository.get_public_endpoint_owners(
            skip=skip, limit=limit
        )

        owners = [
            OwnerSummary(
                username=o["username"],
                endpoint_count=o["endpoint_count"],
                model_count=o["model_count"],
                data_source_count=o["data_source_count"],
            )
            for o in owners_data
        ]

        return OwnersListResponse(owners=owners, total_count=total_count)

    # ===========================================
    # RAG INTEGRATION METHODS
    # ===========================================

    def _ingest_to_rag(self, endpoint_id: int) -> None:
        """Ingest endpoint to RAG vector store (best effort).

        This is a non-blocking operation - failures are logged but don't
        affect the main operation.

        Args:
            endpoint_id: The endpoint ID to ingest.
        """
        if not self.rag_service.is_available:
            return

        try:
            endpoint_model = self.endpoint_repository.get_endpoint_model(endpoint_id)
            if not endpoint_model:
                logger.warning(f"Cannot ingest endpoint {endpoint_id}: not found")
                return

            # Only ingest public endpoints
            if endpoint_model.visibility != EndpointVisibility.PUBLIC.value:
                return

            file_id = self.rag_service.ingest_endpoint(endpoint_model)
            if file_id:
                self.endpoint_repository.update_rag_file_id(endpoint_id, file_id)
                logger.debug(
                    f"Ingested endpoint {endpoint_id} to RAG (file: {file_id})"
                )
        except Exception as e:
            logger.warning(f"Failed to ingest endpoint {endpoint_id} to RAG: {e}")

    def _remove_from_rag(self, endpoint_id: int) -> None:
        """Remove endpoint from RAG vector store (best effort).

        Args:
            endpoint_id: The endpoint ID to remove.
        """
        if not self.rag_service.is_available:
            return

        try:
            file_id = self.endpoint_repository.get_rag_file_id(endpoint_id)
            if file_id:
                self.rag_service.remove_endpoint(file_id)
                self.endpoint_repository.update_rag_file_id(endpoint_id, None)
                logger.debug(
                    f"Removed endpoint {endpoint_id} from RAG (file: {file_id})"
                )
        except Exception as e:
            logger.warning(f"Failed to remove endpoint {endpoint_id} from RAG: {e}")

    def _update_rag_on_visibility_change(
        self,
        endpoint_id: int,
        old_visibility: str,
        new_visibility: str,
    ) -> None:
        """Handle RAG updates when endpoint visibility changes.

        Args:
            endpoint_id: The endpoint ID.
            old_visibility: The previous visibility value.
            new_visibility: The new visibility value.
        """
        if not self.rag_service.is_available:
            return

        was_public = old_visibility == EndpointVisibility.PUBLIC.value
        is_public = new_visibility == EndpointVisibility.PUBLIC.value

        if was_public and not is_public:
            # Was public, now private/internal -> remove from RAG
            self._remove_from_rag(endpoint_id)
        elif not was_public and is_public:
            # Was private/internal, now public -> add to RAG
            self._ingest_to_rag(endpoint_id)
        elif was_public and is_public:
            # Still public, might need to update content
            self._update_in_rag(endpoint_id)

    def _update_in_rag(self, endpoint_id: int) -> None:
        """Update endpoint content in RAG (remove and re-add).

        Args:
            endpoint_id: The endpoint ID to update.
        """
        if not self.rag_service.is_available:
            return

        try:
            endpoint_model = self.endpoint_repository.get_endpoint_model(endpoint_id)
            if not endpoint_model:
                return

            # Only update if public
            if endpoint_model.visibility != EndpointVisibility.PUBLIC.value:
                return

            old_file_id = endpoint_model.rag_file_id
            new_file_id = self.rag_service.update_endpoint(endpoint_model, old_file_id)
            if new_file_id:
                self.endpoint_repository.update_rag_file_id(endpoint_id, new_file_id)
                logger.debug(
                    f"Updated endpoint {endpoint_id} in RAG (file: {new_file_id})"
                )
        except Exception as e:
            logger.warning(f"Failed to update endpoint {endpoint_id} in RAG: {e}")

    def search_endpoints(
        self,
        query: str,
        top_k: int = 10,
        endpoint_type: Optional[EndpointType] = None,
        current_user: Optional[User] = None,
    ) -> EndpointSearchResponse:
        """Search endpoints using semantic search (RAG).

        Args:
            query: Natural language search query.
            top_k: Maximum number of results to return.
            endpoint_type: Optional filter by endpoint type.

        Returns:
            EndpointSearchResponse with matching endpoints and relevance scores.
        """
        if not self.rag_service.is_available:
            logger.debug("RAG service not available, returning empty results")
            return EndpointSearchResponse(results=[], total=0, query=query)

        # Get endpoint IDs with relevance scores from RAG search
        search_results = self.rag_service.search(query, max_results=top_k * 2)

        if not search_results:
            return EndpointSearchResponse(results=[], total=0, query=query)

        # Create a map of endpoint_id -> relevance_score
        score_map: dict[int, float] = dict(search_results)
        endpoint_ids = list(score_map.keys())

        # Fetch endpoints from database (preserves ranking order)
        endpoints = self.endpoint_repository.get_public_endpoints_by_ids(
            endpoint_ids,
            viewer_email=_viewer_email(current_user),
        )

        # Filter by type if specified (inclusive: model_data_source matches both)
        if endpoint_type:
            matching_types = get_matching_types(endpoint_type)
            endpoints = [ep for ep in endpoints if ep.type in matching_types]

        # Limit to top_k
        endpoints = endpoints[:top_k]

        # Convert to EndpointSearchResult with relevance scores
        results: List[EndpointSearchResult] = []
        for ep_index, ep in enumerate(endpoints):
            if ep_index < len(endpoint_ids):
                score = score_map.get(endpoint_ids[ep_index], 0.0)
            else:
                score = 0.0

            results.append(
                EndpointSearchResult(
                    name=ep.name,
                    slug=ep.slug,
                    description=ep.description,
                    type=ep.type,
                    owner_username=ep.owner_username,
                    contributors_count=ep.contributors_count,
                    version=ep.version,
                    readme=ep.readme,
                    tags=ep.tags,
                    stars_count=ep.stars_count,
                    policies=ep.policies,
                    connect=ep.connect,
                    created_at=ep.created_at,
                    updated_at=ep.updated_at,
                    relevance_score=score,
                )
            )

        return EndpointSearchResponse(
            results=results,
            total=len(results),
            query=query,
        )

    def get_endpoint(self, endpoint_id: int, current_user: User) -> EndpointResponse:
        """Get endpoint by ID with access control and transformed URLs."""
        endpoint = self.endpoint_repository.get_by_id(endpoint_id)
        if not endpoint:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        # Check permissions
        if not self._can_access_endpoint(endpoint, current_user):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # Hide existence for security
                detail="Endpoint not found",
            )

        return self._to_response_with_urls(endpoint, current_user=current_user)

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

        # Remove from RAG before deleting (best effort)
        self._remove_from_rag(endpoint_id)

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

        # Remove from RAG before deleting (best effort)
        self._remove_from_rag(endpoint.id)

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

        if not self._can_access_endpoint(endpoint, current_user):
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
        self, endpoint: Endpoint, current_user: Optional[User]
    ) -> bool:
        """Check if user can access endpoint."""
        # Public endpoints are always accessible
        if endpoint.visibility == EndpointVisibility.PUBLIC:
            return True

        # Unauthenticated users can only see public endpoints
        if current_user is None:
            return False

        # Admin can access everything
        if current_user.role == UserRole.ADMIN:
            return True

        # Owner can access; non-owners cannot — INTERNAL behaves like PRIVATE
        # for user accounts (no "members" concept)
        return endpoint.user_id == current_user.id

    def _can_see_full_details(
        self, endpoint: Endpoint, current_user: Optional[User]
    ) -> bool:
        """Check if user can see full endpoint details."""
        if current_user is None:
            return endpoint.visibility == EndpointVisibility.PUBLIC

        if current_user.role == UserRole.ADMIN:
            return True

        if endpoint.user_id == current_user.id:
            return True

        return endpoint.visibility == EndpointVisibility.PUBLIC

    def _can_modify_endpoint(self, endpoint: Endpoint, current_user: User) -> bool:
        """Check if user can modify endpoint."""
        if current_user.role == UserRole.ADMIN:
            return True
        return endpoint.user_id == current_user.id

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

            # Validate + enrich cluster (shared wallet) policies
            cluster_error = self._process_cluster_policies(endpoint_data.policies)
            if cluster_error:
                validation_errors.append(
                    SyncValidationError(
                        index=index, field="policies", error=cluster_error
                    )
                )
                continue

            # Prepare the validated endpoint data
            final_tags = self._inject_prepaid_tag(
                endpoint_data.tags or [], endpoint_data.policies
            )
            validated_endpoint = {
                "name": endpoint_data.name,
                "slug": slug,
                "description": endpoint_data.description or "",
                "type": endpoint_data.type.value,
                "visibility": endpoint_data.visibility.value,
                "version": endpoint_data.version,
                "readme": endpoint_data.readme or "",
                "tags": final_tags,
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
        satellite_id: Optional[uuid.UUID] = None,
    ) -> SyncEndpointsResponse:
        """Synchronize user's endpoints with provided list.

        This operation is ATOMIC: either all endpoints are synced, or none are.
        It replaces the endpoints served by ONE satellite — not the account's
        entire catalogue, which is what it used to do and which meant one space
        syncing wiped another's endpoints.

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

        # Which satellite is this sync for? None means the account owns none, so
        # the endpoints stay unattached exactly as they would today.
        satellite = self.satellite_service.resolve_existing(
            current_user.id, satellite_id
        )
        space_id = satellite.id if satellite else None

        # Phase 2: Remove old endpoints from the search index (best effort,
        # before the DB delete). Scoped the same way as the delete below: an
        # unscoped sweep would drop another space's endpoints out of Meilisearch
        # permanently, since Phase 4 only re-indexes what this sync creates.
        if self.rag_service.is_available:
            old_rag_files = self.endpoint_repository.get_rag_file_ids_for_space(
                current_user.id, space_id
            )
            for endpoint_id, file_id in old_rag_files:
                try:
                    self.rag_service.remove_endpoint(file_id)
                    logger.debug(f"Removed endpoint {endpoint_id} from RAG during sync")
                except Exception as e:
                    logger.warning(
                        f"Failed to remove endpoint {endpoint_id} from RAG during sync: {e}"
                    )

        # Phase 3: Atomic database operation
        try:
            # Delete only the endpoints this satellite serves
            deleted_count = self.endpoint_repository.delete_endpoints_for_space(
                current_user.id, space_id
            )

            # Create all new endpoints, attached to the resolved satellite
            if validated_endpoints:
                created_endpoints = self.endpoint_repository.bulk_create_endpoints(
                    validated_endpoints, current_user.id, space_id=space_id
                )
            else:
                created_endpoints = []

            # Commit the transaction (delete + creates)
            self.session.commit()

            logger.info(
                f"Sync completed for user {current_user.id}: "
                f"deleted={deleted_count}, created={len(created_endpoints)}"
            )

            # Phase 4: Ingest new public endpoints to RAG (best effort, after commit)
            if self.rag_service.is_available:
                for endpoint in created_endpoints:
                    if endpoint.visibility == EndpointVisibility.PUBLIC:
                        self._ingest_to_rag(endpoint.id)

            # Transform URLs for response (look up user domain once)
            user = self.user_repository.get_by_id(current_user.id)
            user_domain = user.domain if user else None
            response_endpoints = [
                self._to_response_with_urls(
                    ep, owner_domain=user_domain, current_user=current_user
                )
                for ep in created_endpoints
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

    # ===========================================
    # ENDPOINT HEALTH REPORTING
    # ===========================================

    def report_endpoint_health(
        self,
        endpoints_health: List[EndpointHealthItem],
        url: str,
        current_user: User,
        ttl_seconds: Optional[int] = None,
        satellite_id: Optional[uuid.UUID] = None,
    ) -> EndpointHealthResponse:
        """Report per-endpoint health status from client.

        This method:
        1. Caps TTL at server max
        2. Resolves which satellite the report is for and records its origin
        3. Matches slugs against the user's endpoints
        4. Updates health_status, health_checked_at, health_ttl_seconds per endpoint

        Args:
            endpoints_health: List of EndpointHealthItem with slug, status, checked_at
            url: The reporting satellite's origin
            current_user: The authenticated user
            ttl_seconds: Requested TTL (optional, capped by server max)
            satellite_id: Which satellite is reporting. Optional — the URL
                identifies it for any account owning fewer than two.

        Returns:
            EndpointHealthResponse with updated and ignored counts
        """
        # --- TTL calculation ---
        requested_ttl = ttl_seconds or settings.health_default_ttl_seconds
        effective_ttl = min(requested_ttl, settings.health_max_ttl_seconds)

        # --- Satellite origin ---
        # Replaces the account-wide users.domain write. BaseUrl also validates
        # and canonicalises, which the old scheme://netloc extraction did not.
        self.satellite_service.record_heartbeat(
            user_id=current_user.id,
            reported_url=url,
            satellite_id=satellite_id,
        )

        # --- Bulk slug match (single query, no is_active filter) ---
        slugs = [item.slug for item in endpoints_health]
        matched_endpoints = self.endpoint_repository.get_endpoints_by_slugs_for_health(
            user_id=current_user.id,
            slugs=slugs,
        )

        # Build slug -> endpoint model mapping
        slug_to_endpoint = {ep.slug: ep for ep in matched_endpoints}

        # --- Build health updates ---
        health_updates = []

        for item in endpoints_health:
            slug = item.slug.lower()
            endpoint = slug_to_endpoint.get(slug)  # type: ignore[call-overload]
            if endpoint is None:
                continue

            health_updates.append(
                {
                    "endpoint_id": endpoint.id,
                    "health_status": item.status.value,
                    "health_checked_at": item.checked_at,
                    "health_ttl_seconds": effective_ttl,
                }
            )

        # --- Bulk update per-endpoint health status ---
        updated = 0
        if health_updates:
            updated = self.endpoint_repository.bulk_update_health_status(health_updates)

        ignored = len(endpoints_health) - updated

        # --- Commit all changes ---
        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            logger.error(
                f"Failed to commit endpoint health update for user "
                f"{current_user.id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update endpoint health",
            ) from e

        logger.info(
            f"Endpoint health reported by user {current_user.id}: "
            f"updated={updated}, ignored={ignored}"
        )

        return EndpointHealthResponse(
            updated=updated,
            ignored=ignored,
        )

    # ===========================================
    # ENDPOINT UPTIME / TELEMETRY
    # ===========================================

    def get_endpoint_uptime(
        self,
        owner_username: str,
        slug: str,
        window_hours: int,
        current_user: Optional[User],
    ) -> EndpointUptimeResponse:
        """Return bucketed uptime + latency series for one endpoint.

        Visibility mirrors the rest of the endpoint read path:
        - Public endpoints are readable by anyone (including guests)
        - INTERNAL/PRIVATE endpoints require the viewer to be the owner.

        Args:
            owner_username: User username
            slug: Endpoint slug
            window_hours: Rolling window in hours (1..2160 enforced at route)
            current_user: Authenticated viewer (optional for public reads)

        Returns:
            EndpointUptimeResponse with one entry per bucket (oldest first)

        Raises:
            HTTPException: 404 if endpoint is not found or not accessible
        """
        normalized_slug = slug.lower()

        # Resolve owner. Use the any-state lookup so a chart can be rendered
        # even when the health monitor has flipped the endpoint to
        # is_active=False.
        owner_user = self.user_repository.get_by_username(owner_username)
        endpoint_model = None
        if owner_user is not None:
            endpoint_model = self.endpoint_repository.get_by_owner_and_slug_any_state(
                user_id=owner_user.id,
                slug=normalized_slug,
            )

        if endpoint_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        if not self._can_access_endpoint(endpoint_model, current_user):
            # Hide existence for security
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )

        bucket_seconds = max(1, settings.uptime_bucket_seconds)
        samples = self.endpoint_repository.get_uptime_samples(
            endpoint_id=endpoint_model.id,
            window_hours=window_hours,
        )

        buckets: list[UptimeBucket] = []
        for s in samples:
            total = s.total_checks or 0
            healthy = s.healthy_checks or 0
            uptime_pct = (100.0 * healthy / total) if total > 0 else 0.0
            # bucket_start is NOT NULL in the schema; assert narrows the type
            # so mypy stops treating it as Optional[datetime].
            bucket_start = s.bucket_start
            assert bucket_start is not None
            buckets.append(
                UptimeBucket(
                    bucket_start=bucket_start,
                    samples=total,
                    healthy_samples=healthy,
                    uptime_pct=round(uptime_pct, 2),
                )
            )

        return EndpointUptimeResponse(
            endpoint_id=endpoint_model.id,
            owner_username=owner_username,
            slug=endpoint_model.slug,
            bucket_seconds=bucket_seconds,
            window_hours=window_hours,
            buckets=buckets,
        )
