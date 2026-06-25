"""Collective management business logic.

Owns the membership state machine: a join request lands as ``pending`` (or
``approved`` when the collective has ``auto_approve`` set), an invitation lands
as ``invited``, and an owner review / endpoint-owner response moves it to
``approved`` or ``rejected``. See ``syfthub.schemas.collective.MembershipStatus``.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterator, List, Optional, Sequence

from fastapi import HTTPException, status

from syfthub.repositories.collective import (
    CollectiveMemberRepository,
    CollectiveRepository,
    CollectiveSharedEndpointMemberRepository,
    CollectiveSharedEndpointRepository,
)
from syfthub.repositories.endpoint import EndpointRepository
from syfthub.repositories.user import UserRepository
from syfthub.schemas.auth import UserRole
from syfthub.schemas.collective import (
    RESERVED_SHARED_ENDPOINT_SLUGS,
    CollectiveBillingSummaryResponse,
    CollectiveCreate,
    CollectiveMemberBilling,
    CollectiveMemberResponse,
    CollectiveResponse,
    CollectiveSharedEndpointCreate,
    CollectiveSharedEndpointMemberSummary,
    CollectiveSharedEndpointResponse,
    CollectiveSharedEndpointUpdate,
    CollectiveUpdate,
    InvitationDecision,
    InvitationEmailContext,
    MemberBillingDetail,
    MembershipStatus,
    MoneyBundle,
    PriceByCurrency,
    ReviewDecision,
    slugify_collective_name,
    slugify_shared_endpoint_name,
)
from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointType,
    EndpointVisibility,
    get_matching_types,
)
from syfthub.services.base import BaseService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from syfthub.schemas.user import User


# Endpoint types eligible for collective membership. A collective groups data
# sources, so model-only and agent endpoints cannot join; ``model_data_source``
# qualifies because it also exposes a data source.
_JOINABLE_ENDPOINT_TYPES: frozenset[str] = frozenset(
    get_matching_types(EndpointType.DATA_SOURCE)
)


# Policy ``type`` values that bill via publisher-side prepaid credits (the buyer
# funds a wallet with the publisher and we read/charge it). These map onto the
# chat PaymentGate / wallet-panel settlement UX.
_PREPAID_PROVIDERS: frozenset[str] = frozenset({"xendit", "stripe"})

# The single canonical pay-as-you-go (MPP) policy ``type`` — billed per request
# against the buyer's single Hub (MPP) wallet, with no upfront prepaid wallet per
# publisher. ``mpp`` is exactly what syft-space publishes: its publish handler
# overrides the policy type with the wallet provider (``mpp`` / ``xendit``). The
# legacy ``mpp_accounting`` / ``accounting`` / ``transaction`` spellings were
# collapsed into it by the ``unify_mpp_policy_type`` migration; keep in lockstep
# with the frontend ``MPP_BALANCE_TYPES`` set in ``policy-item.tsx``.
_MPP_POLICY_TYPES: frozenset[str] = frozenset({"mpp"})


def _is_url(value: Any) -> bool:
    """Whether ``value`` looks like an http(s) URL (mirrors the frontend guard)."""
    return isinstance(value, str) and (
        value.startswith("https://") or value.startswith("http://")
    )


def _pick(config: dict[str, Any], snake: str, camel: str) -> Any:
    """Read a config value by snake_case then camelCase key.

    Publisher policy ``config`` reaches us in either casing depending on the
    publish path, so accept both (matching ``parseXenditConfig`` on the client).
    """
    if snake in config:
        return config[snake]
    return config.get(camel)


def _parse_unit(config: dict[str, Any]) -> str:
    """Read the billing unit from a policy config, defaulting to ``request``."""
    unit_raw = _pick(config, "unit_type", "unitType")
    if isinstance(unit_raw, str) and unit_raw.lower() in ("request", "document"):
        return unit_raw.lower()
    return "request"


def _parse_prepaid_config(config: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Normalize a prepaid policy ``config`` into billing-detail kwargs.

    Returns ``None`` when the policy lacks the URLs needed to read a balance or
    purchase credits — such a policy can't drive settlement, so the member is
    treated as if it had no prepaid policy at all.
    """
    payment_url = _pick(config, "payment_url", "paymentUrl")
    credits_url = _pick(config, "credits_url", "creditsUrl")
    if not _is_url(payment_url) or not _is_url(credits_url):
        return None

    invoices_url = _pick(config, "invoices_url", "invoicesUrl")
    currency = config.get("currency")
    # New publishers send a generic ``price``; legacy policies used
    # ``price_per_request``. Either yields the per-unit price.
    price = config.get("price")
    if not isinstance(price, (int, float)):
        price = _pick(config, "price_per_request", "pricePerRequest")
    unit = _parse_unit(config)
    raw_bundles = config.get("bundles")
    bundles: list[MoneyBundle] = []
    if isinstance(raw_bundles, list):
        for entry in raw_bundles:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("name"), str)
                and isinstance(entry.get("amount"), (int, float))
            ):
                bundles.append(
                    MoneyBundle(name=entry["name"], amount=float(entry["amount"]))
                )

    return {
        "currency": currency if isinstance(currency, str) else "IDR",
        "price_per_unit": float(price) if isinstance(price, (int, float)) else None,
        "unit": unit,
        "payment_url": payment_url,
        "credits_url": credits_url,
        "invoices_url": invoices_url if _is_url(invoices_url) else None,
        "bundles": bundles,
    }


def _parse_per_request_price(
    config: dict[str, Any],
) -> tuple[str, Optional[float], str]:
    """Extract a per-request price + currency from a policy config.

    Every endpoint bills per request regardless of how it is settled, so MPP
    policies expose a flat price the same way prepaid ones do. Returns
    ``(currency, price, unit)`` with ``price`` ``None`` when no flat per-request
    price is published.
    """
    currency = config.get("currency")
    price = config.get("price")
    if not isinstance(price, (int, float)):
        price = _pick(config, "price_per_request", "pricePerRequest")
    if not isinstance(price, (int, float)):
        price = _pick(config, "price_per_call", "pricePerCall")
    unit = _parse_unit(config)
    return (
        currency if isinstance(currency, str) else "USD",
        float(price) if isinstance(price, (int, float)) else None,
        unit,
    )


def _policy_field(policy: Any, name: str, default: Any) -> Any:
    """Read a policy field from either a Pydantic ``Policy`` or a plain dict.

    Top-level policies reach us as ``Policy`` instances, but a composite
    policy nests its children as raw dicts inside ``config["policies"]`` (the
    schema's flexible ``config`` is never re-validated into ``Policy``), so the
    classifier must read both shapes uniformly.
    """
    if isinstance(policy, dict):
        return policy.get(name, default)
    return getattr(policy, name, default)


def _iter_billing_leaves(policies: Any) -> Iterator[Any]:
    """Yield every enabled *leaf* policy, descending into composite wrappers.

    Composite policies (``all_of`` / ``any_of`` / ``not`` / ``access_group``)
    carry their children under ``config["policies"]`` and are evaluated
    recursively by the policy runner. A pricing policy bundled with an access
    policy inside such a wrapper is therefore still active billing — so the
    billing classifier must look through the wrapper too, not just at the
    top-level ``type``. A disabled wrapper short-circuits its whole subtree.
    """
    for policy in policies or []:
        if not _policy_field(policy, "enabled", True):
            continue
        config = _policy_field(policy, "config", {}) or {}
        children = config.get("policies") if isinstance(config, dict) else None
        if isinstance(children, list) and children:
            yield from _iter_billing_leaves(children)
        else:
            yield policy


def _classify_billing(endpoint: Endpoint) -> MemberBillingDetail:
    """Reduce an endpoint's policies to a single normalized billing detail.

    Every endpoint bills per request; ``kind`` only records *how the buyer
    settles* — ``prepaid`` (a per-publisher Xendit/Stripe wallet) vs ``mpp``
    (the buyer's single Hub wallet) — or ``free`` when no billing policy is
    enabled. Precedence: a usable prepaid policy wins, then an MPP policy.
    Disabled policies are ignored, and a pricing policy nested inside a
    composite (``all_of`` / ``access_group`` / …) counts the same as a
    top-level one.
    """
    mpp_config: Optional[dict[str, Any]] = None
    for policy in _iter_billing_leaves(endpoint.policies):
        ptype = str(_policy_field(policy, "type", "")).lower()
        config = _policy_field(policy, "config", {}) or {}
        if ptype in _PREPAID_PROVIDERS:
            parsed = _parse_prepaid_config(config)
            if parsed is not None:
                return MemberBillingDetail(kind="prepaid", provider=ptype, **parsed)
        elif ptype in _MPP_POLICY_TYPES and mpp_config is None:
            mpp_config = config
    if mpp_config is not None:
        currency, price, unit = _parse_per_request_price(mpp_config)
        return MemberBillingDetail(
            kind="mpp", currency=currency, price_per_unit=price, unit=unit
        )
    return MemberBillingDetail(kind="free")


class CollectiveService(BaseService):
    """Service for collective and membership operations."""

    def __init__(self, session: Session):
        """Initialize the service with its repositories."""
        super().__init__(session)
        self.collective_repo = CollectiveRepository(session)
        self.member_repo = CollectiveMemberRepository(session)
        self.endpoint_repo = EndpointRepository(session)
        self.user_repo = UserRepository(session)
        self.shared_endpoint_repo = CollectiveSharedEndpointRepository(session)
        self.shared_endpoint_member_repo = CollectiveSharedEndpointMemberRepository(
            session
        )

    # ------------------------------------------------------------------
    # Collective CRUD
    # ------------------------------------------------------------------

    def create_collective(
        self, data: CollectiveCreate, current_user: User
    ) -> CollectiveResponse:
        """Create a new collective owned by the current user."""
        slug = self._resolve_slug(data)
        collective = self.collective_repo.create_collective(
            owner_id=current_user.id,
            name=data.name,
            slug=slug,
            description=data.description,
            about=data.about,
            auto_approve=data.auto_approve,
            icon_url=data.icon_url,
            tags=data.tags,
        )
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create collective",
            )
        return self._with_counts(collective)

    def get_collective(self, collective_id: int) -> CollectiveResponse:
        """Get a collective by ID. Collectives are publicly viewable."""
        return self._with_counts(self._get_collective_or_404(collective_id))

    def get_collective_by_slug(self, slug: str) -> CollectiveResponse:
        """Get a collective by slug. Collectives are publicly viewable."""
        collective = self.collective_repo.get_by_slug(slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return self._with_counts(collective)

    def get_collective_endpoint_paths(self, slug: str) -> List[str]:
        """Return owner/slug paths of all approved member endpoints.

        Called by the SDK's collective-resolution step to expand a
        ``collective/<slug>`` (or the equivalent ``collective/<slug>/all``)
        path into the individual endpoint paths that participate in the
        aggregator request.
        """
        collective = self.collective_repo.get_by_slug(slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return self._collective_approved_paths(collective.id)

    def get_shared_endpoint_paths(
        self, collective_slug: str, shared_slug: str
    ) -> List[str]:
        """Resolve a ``collective/<X>/<Y>`` path to owner/slug endpoint paths.

        The result is the intersection of the configured endpoint set with the
        parent collective's currently approved members — endpoints that have
        since left the collective are silently filtered out. The ``all`` slug
        short-circuits to "every approved member".
        """
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        if shared_slug == "all":
            return self._collective_approved_paths(collective.id)

        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective.id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        configured_ids = self.shared_endpoint_member_repo.list_endpoint_ids(shared.id)
        approved_ids = self._approved_endpoint_ids(collective.id)
        active_ids = [eid for eid in configured_ids if eid in approved_ids]
        return self._resolve_endpoint_paths(active_ids)

    def get_billing_summary(
        self, collective_slug: str, shared_slug: Optional[str] = None
    ) -> CollectiveBillingSummaryResponse:
        """Aggregate pricing + per-member settlement metadata for a shared endpoint.

        Resolves the participating (approved) member endpoints — all members
        when ``shared_slug`` is ``None`` or ``"all"``, otherwise the configured
        subset intersected with approved members — and classifies each into a
        prepaid / mpp / free billing bucket. The estimated price sums prepaid
        per-request prices grouped by currency; metered and free members do not
        contribute to it. Public, like the ``endpoint-paths`` resolution.
        """
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )

        if shared_slug is None or shared_slug == "all":
            memberships = self.member_repo.list_members(
                collective.id, [MembershipStatus.APPROVED.value]
            )
            endpoint_ids = [m.endpoint_id for m in memberships]
        else:
            shared = self.shared_endpoint_repo.get_by_collective_and_slug(
                collective.id, shared_slug
            )
            if shared is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Shared endpoint not found",
                )
            configured_ids = self.shared_endpoint_member_repo.list_endpoint_ids(
                shared.id
            )
            approved_ids = self._approved_endpoint_ids(collective.id)
            endpoint_ids = [eid for eid in configured_ids if eid in approved_ids]

        return self._build_billing_summary(endpoint_ids)

    def _build_billing_summary(
        self, endpoint_ids: Sequence[int]
    ) -> CollectiveBillingSummaryResponse:
        """Classify the given endpoints and aggregate their prepaid prices."""
        endpoints = {
            ep.id: ep for ep in self.endpoint_repo.get_by_ids(list(endpoint_ids))
        }
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }

        members: List[CollectiveMemberBilling] = []
        # Sum per-request prices per currency without converting between
        # currencies — distinct currencies surface as separate line items.
        # Both prepaid and MPP members bill per request, so both contribute;
        # only the settlement route differs.
        price_by_currency: dict[str, float] = {}
        free_count = prepaid_count = mpp_count = 0

        for endpoint_id in endpoint_ids:
            endpoint = endpoints.get(endpoint_id)
            if endpoint is None:
                continue  # endpoint left / was soft-deleted since approval
            owner = owners.get(endpoint.user_id)
            detail = _classify_billing(endpoint)

            if detail.kind == "prepaid":
                prepaid_count += 1
            elif detail.kind == "mpp":
                mpp_count += 1
            else:
                free_count += 1

            if detail.price_per_unit is not None and detail.currency:
                price_by_currency[detail.currency] = (
                    price_by_currency.get(detail.currency, 0.0) + detail.price_per_unit
                )

            members.append(
                CollectiveMemberBilling(
                    endpoint_id=endpoint.id,
                    endpoint_name=endpoint.name,
                    endpoint_slug=endpoint.slug,
                    endpoint_owner_username=(
                        owner.username if owner is not None else None
                    ),
                    endpoint_owner_full_name=(
                        owner.full_name if owner is not None else None
                    ),
                    endpoint_type=endpoint.type.value,
                    billing=detail,
                )
            )

        estimated_price = [
            PriceByCurrency(currency=currency, amount=amount)
            for currency, amount in price_by_currency.items()
        ]
        return CollectiveBillingSummaryResponse(
            members=members,
            estimated_price=estimated_price,
            free_count=free_count,
            prepaid_count=prepaid_count,
            mpp_count=mpp_count,
        )

    def list_collectives(
        self,
        skip: int = 0,
        limit: int = 50,
        owner_username: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[CollectiveResponse]:
        """List collectives, newest first.

        Optionally filtered by ``owner_username`` (resolved to an owner_id
        internally) and/or a ``search`` string. Returns an empty list when
        ``owner_username`` is provided but does not match any user.
        """
        owner_id: Optional[int] = None
        if owner_username is not None:
            owner = self.user_repo.get_by_username(owner_username)
            if owner is None:
                return []
            owner_id = owner.id
        collectives = self.collective_repo.list_collectives(
            skip, limit, owner_id, search
        )
        # Grouped queries for all counts instead of N per-row queries.
        ids = [c.id for c in collectives]
        approved = MembershipStatus.APPROVED.value
        member_counts = self.member_repo.count_members_bulk(ids, approved)
        owner_counts = self.member_repo.count_owners_bulk(ids, approved)
        for collective in collectives:
            collective.member_count = member_counts.get(collective.id, 0)
            collective.owner_count = owner_counts.get(collective.id, 0)
        return collectives

    def list_collectives_for_user_endpoints(
        self, username: str
    ) -> List[CollectiveResponse]:
        """List distinct collectives where any endpoint owned by ``username`` is an approved member.

        Public-readable. Returns only ``APPROVED`` memberships. Returns an
        empty list when the username does not exist or has no memberships.
        """
        owner = self.user_repo.get_by_username(username)
        if owner is None:
            return []
        collectives = self.member_repo.list_collectives_for_user(
            owner.id, [MembershipStatus.APPROVED.value]
        )
        ids = [c.id for c in collectives]
        approved = MembershipStatus.APPROVED.value
        member_counts = self.member_repo.count_members_bulk(ids, approved)
        owner_counts = self.member_repo.count_owners_bulk(ids, approved)
        for collective in collectives:
            collective.member_count = member_counts.get(collective.id, 0)
            collective.owner_count = owner_counts.get(collective.id, 0)
        return collectives

    def list_collectives_for_endpoint(
        self, owner_username: str, slug: str
    ) -> List[CollectiveResponse]:
        """List approved collectives an ``owner/slug`` endpoint belongs to.

        Public-readable. Returns only ``APPROVED`` memberships so pending /
        invited / rejected state never leaks to non-owners — mirrors the
        non-owner view of ``list_members``.
        """
        owner = self.user_repo.get_by_username(owner_username)
        if owner is None:
            return []
        endpoint = self.endpoint_repo.get_by_user_and_slug(owner.id, slug)
        if endpoint is None:
            return []
        collectives = self.member_repo.list_collectives_for_endpoint(
            endpoint.id, [MembershipStatus.APPROVED.value]
        )
        ids = [c.id for c in collectives]
        approved = MembershipStatus.APPROVED.value
        member_counts = self.member_repo.count_members_bulk(ids, approved)
        owner_counts = self.member_repo.count_owners_bulk(ids, approved)
        for collective in collectives:
            collective.member_count = member_counts.get(collective.id, 0)
            collective.owner_count = owner_counts.get(collective.id, 0)
        return collectives

    def update_collective(
        self, collective_id: int, data: CollectiveUpdate, current_user: User
    ) -> CollectiveResponse:
        """Update a collective. Owner (or admin) only."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        fields = data.model_dump(exclude_unset=True)
        if fields:
            updated = self.collective_repo.update_collective(collective_id, fields)
            if updated is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update collective",
                )
            collective = updated
        return self._with_counts(collective)

    def delete_collective(self, collective_id: int, current_user: User) -> None:
        """Delete a collective and all its memberships. Owner (or admin) only."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        if not self.collective_repo.delete(collective_id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete collective",
            )

    # ------------------------------------------------------------------
    # Membership — joining
    # ------------------------------------------------------------------

    def request_join(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> CollectiveMemberResponse:
        """Request that an endpoint join a collective (endpoint owner action).

        With ``auto_approve`` the membership is approved immediately; otherwise
        it lands as ``pending`` for the collective owner to review.

        Only data-source endpoints (``data_source`` / ``model_data_source``)
        are eligible; a model-only or agent endpoint is rejected with 400.
        """
        collective = self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_endpoint_owner(endpoint, current_user)
        self._require_joinable_endpoint(endpoint)
        if endpoint.archived:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archived endpoints cannot join collectives",
            )

        existing = self.member_repo.get_membership(collective_id, endpoint_id)
        now = datetime.now(timezone.utc)

        if existing is not None:
            if existing.status == MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Endpoint is already a member of this collective",
                )
            if existing.status == MembershipStatus.PENDING:
                # Idempotent — a request is already awaiting review.
                return self._enrich(existing)
            if existing.status == MembershipStatus.INVITED:
                # The owner already invited this endpoint; requesting to join
                # accepts that standing invitation.
                return self._apply(
                    existing.id,
                    MembershipStatus.APPROVED,
                    responded_at=now,
                    reviewed_by_user_id=current_user.id,
                )
            # rejected -> a fresh request reopens the membership below.

        join_status, responded_at = self._join_outcome(collective, now)
        if existing is not None:
            return self._apply(
                existing.id,
                join_status,
                requested_at=now,
                responded_at=responded_at,
                reviewed_by_user_id=None,
            )
        member = self.member_repo.create_membership(
            collective_id=collective_id,
            endpoint_id=endpoint_id,
            status=join_status.value,
            responded_at=responded_at,
        )
        return self._member_response(member)

    def invite_endpoint(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> tuple[CollectiveMemberResponse, Optional[InvitationEmailContext]]:
        """Invite an endpoint into a collective (collective owner action).

        The invited endpoint's owner must accept before the membership becomes
        active. If the endpoint had already requested to join, the invitation
        is treated as an approval.

        Returns the membership plus, when an invitation is (re)issued, the
        context for the notification email the caller should send. The email
        context is ``None`` when no invitation email is warranted — e.g. the
        invite approved a standing join request, or the endpoint has no
        individual owner to notify.

        Only data-source endpoints (``data_source`` / ``model_data_source``)
        are eligible; inviting a model-only or agent endpoint is rejected
        with 400.
        """
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        # The owner need not own the endpoint to invite it — just confirm it exists.
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_joinable_endpoint(endpoint)

        existing = self.member_repo.get_membership(collective_id, endpoint_id)
        now = datetime.now(timezone.utc)
        email_context = self._build_invitation_context(
            collective, endpoint, current_user
        )

        if existing is not None:
            if existing.status == MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Endpoint is already a member of this collective",
                )
            if existing.status == MembershipStatus.INVITED:
                # Idempotent — re-notify so the owner gets a fresh link.
                return self._enrich(existing), email_context
            if existing.status == MembershipStatus.PENDING:
                # The endpoint already asked to join — inviting it approves it,
                # so no invitation email is warranted.
                approved = self._apply(
                    existing.id,
                    MembershipStatus.APPROVED,
                    responded_at=now,
                    reviewed_by_user_id=current_user.id,
                )
                return approved, None
            # rejected -> reissue the invitation.
            reissued = self._apply(
                existing.id,
                MembershipStatus.INVITED,
                requested_at=now,
                responded_at=None,
                reviewed_by_user_id=None,
            )
            return reissued, email_context

        member = self.member_repo.create_membership(
            collective_id=collective_id,
            endpoint_id=endpoint_id,
            status=MembershipStatus.INVITED.value,
        )
        return self._member_response(member), email_context

    # ------------------------------------------------------------------
    # Membership — review / response / removal
    # ------------------------------------------------------------------

    def review_request(
        self,
        collective_id: int,
        endpoint_id: int,
        decision: ReviewDecision,
        current_user: User,
    ) -> CollectiveMemberResponse:
        """Approve or reject a pending join request (collective owner action)."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )
        if membership.status != MembershipStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This membership has no pending join request to review",
            )

        new_status = (
            MembershipStatus.APPROVED
            if decision == ReviewDecision.APPROVE
            else MembershipStatus.REJECTED
        )
        return self._apply(
            membership.id,
            new_status,
            responded_at=datetime.now(timezone.utc),
            reviewed_by_user_id=current_user.id,
        )

    def respond_to_invitation(
        self,
        collective_id: int,
        endpoint_id: int,
        decision: InvitationDecision,
        current_user: User,
    ) -> CollectiveMemberResponse:
        """Accept or decline a collective invitation (endpoint owner action)."""
        self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)
        self._require_endpoint_owner(endpoint, current_user)

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )
        if membership.status != MembershipStatus.INVITED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="There is no pending invitation for this endpoint",
            )

        new_status = (
            MembershipStatus.APPROVED
            if decision == InvitationDecision.ACCEPT
            else MembershipStatus.REJECTED
        )
        return self._apply(
            membership.id,
            new_status,
            responded_at=datetime.now(timezone.utc),
            reviewed_by_user_id=current_user.id,
        )

    def invite_endpoint_by_path(
        self,
        collective_id: int,
        owner_username: str,
        slug: str,
        current_user: User,
    ) -> tuple[CollectiveMemberResponse, Optional[InvitationEmailContext]]:
        """Invite an endpoint identified by ``owner/slug``.

        Resolves the path to an endpoint id and delegates to ``invite_endpoint``.
        Only public endpoints are resolvable here (this is how the admin UI
        finds them); 404 otherwise.
        """
        owner = self.user_repo.get_by_username(owner_username)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{owner_username}' not found",
            )
        endpoint = self.endpoint_repo.get_by_owner_and_slug_any_state(owner.id, slug)
        if endpoint is None or endpoint.visibility != EndpointVisibility.PUBLIC:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Endpoint '{owner_username}/{slug}' not found",
            )
        return self.invite_endpoint(collective_id, endpoint.id, current_user)

    def get_invitation(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> CollectiveMemberResponse:
        """Return the membership row for an invitation.

        Used by the invitation-response landing page so the recipient can see
        the invite even before they accept. Readable by the endpoint owner,
        the collective owner, and admins; everyone else gets 403. A row that
        does not exist (or has been removed) yields 404. The status is not
        constrained — the caller may want to render an "already accepted" or
        "declined" state.
        """
        collective = self._get_collective_or_404(collective_id)
        endpoint = self._get_endpoint_or_404(endpoint_id)

        allowed = (
            self._is_admin(current_user)
            or collective.owner_id == current_user.id
            or endpoint.user_id == current_user.id
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner or the endpoint owner "
                "can view this invitation",
            )

        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found",
            )
        return self._enrich(membership)

    def remove_member(
        self, collective_id: int, endpoint_id: int, current_user: User
    ) -> None:
        """Remove an endpoint from a collective.

        Allowed for the collective owner (remove) or the endpoint owner (leave).
        """
        collective = self._get_collective_or_404(collective_id)
        membership = self.member_repo.get_membership(collective_id, endpoint_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Membership not found",
            )

        allowed = self._is_admin(current_user) or collective.owner_id == current_user.id
        if not allowed:
            endpoint = self.endpoint_repo.get_by_id(endpoint_id)
            allowed = endpoint is not None and endpoint.user_id == current_user.id
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner or the endpoint owner "
                "can remove this membership",
            )

        if not self.member_repo.delete(membership.id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to remove membership",
            )

    def list_members(
        self,
        collective_id: int,
        current_user: Optional[User],
        status_filter: Optional[MembershipStatus] = None,
    ) -> List[CollectiveMemberResponse]:
        """List a collective's memberships.

        Anonymous and non-owner viewers see only ``approved`` members, and only
        those whose endpoint is visible to them. The collective owner (and
        admins) see every membership in every status.
        """
        collective = self._get_collective_or_404(collective_id)
        is_manager = current_user is not None and (
            self._is_admin(current_user) or collective.owner_id == current_user.id
        )

        if status_filter is not None:
            if not is_manager and status_filter != MembershipStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only the collective owner can view "
                    "non-approved memberships",
                )
            statuses: Optional[List[str]] = [status_filter.value]
        elif is_manager:
            statuses = None  # all statuses
        else:
            statuses = [MembershipStatus.APPROVED.value]

        memberships = self.member_repo.list_members(collective_id, statuses)
        if is_manager:
            return self._enrich_many(memberships)

        # Non-managers must not learn that a private/internal endpoint exists.
        # Batch-fetch all endpoints once — used for both visibility filtering
        # and enrichment so each endpoint is fetched at most once.
        viewer_id = current_user.id if current_user is not None else None
        endpoint_map = {
            ep.id: ep
            for ep in self.endpoint_repo.get_by_ids(
                list({m.endpoint_id for m in memberships})
            )
        }
        visible: List[CollectiveMemberResponse] = []
        for membership in memberships:
            endpoint = endpoint_map.get(membership.endpoint_id)
            if endpoint is None:
                continue  # endpoint deactivated or removed
            if (
                endpoint.visibility == EndpointVisibility.PUBLIC
                or endpoint.user_id == viewer_id
            ):
                visible.append(membership)
        return self._enrich_many(visible, endpoints=endpoint_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_admin(user: User) -> bool:
        """Whether the user is a platform admin."""
        return user.role == UserRole.ADMIN

    def _get_collective_or_404(self, collective_id: int) -> CollectiveResponse:
        """Load a collective or raise 404."""
        collective = self.collective_repo.get_by_id(collective_id)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        return collective

    def _get_endpoint_or_404(self, endpoint_id: int) -> Endpoint:
        """Load an active endpoint or raise 404."""
        endpoint = self.endpoint_repo.get_by_id(endpoint_id)
        if endpoint is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Endpoint not found",
            )
        return endpoint

    def _require_owner(self, collective: CollectiveResponse, user: User) -> None:
        """Raise 403 unless the user owns the collective (or is an admin)."""
        if not self._is_admin(user) and collective.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the collective owner can perform this action",
            )

    def _require_endpoint_owner(self, endpoint: Endpoint, user: User) -> None:
        """Raise 403 unless the user owns the endpoint (or is an admin)."""
        if not self._is_admin(user) and endpoint.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only manage memberships for your own endpoints",
            )

    @staticmethod
    def _require_joinable_endpoint(endpoint: Endpoint) -> None:
        """Raise 400 unless the endpoint type is eligible for a collective.

        Collectives group data sources, so model-only and agent endpoints
        cannot join. ``model_data_source`` qualifies because it also exposes a
        data source. This is the single guard for both membership entry points
        (``request_join`` and ``invite_endpoint``) — together they are the only
        paths that create a membership row, so an ineligible endpoint can never
        become (or be invited to become) a member.
        """
        if endpoint.type.value not in _JOINABLE_ENDPOINT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only data source endpoints can join a collective; "
                "model and agent endpoints are not eligible",
            )

    @staticmethod
    def _join_outcome(
        collective: CollectiveResponse, now: datetime
    ) -> tuple[MembershipStatus, Optional[datetime]]:
        """Resolve the status of a fresh join request from ``auto_approve``."""
        if collective.auto_approve:
            return MembershipStatus.APPROVED, now
        return MembershipStatus.PENDING, None

    def _apply(
        self,
        membership_id: int,
        new_status: MembershipStatus,
        *,
        requested_at: Optional[datetime] = None,
        responded_at: Optional[datetime] = None,
        reviewed_by_user_id: Optional[int] = None,
    ) -> CollectiveMemberResponse:
        """Update a membership row's status fields and return the response."""
        fields: dict[str, Any] = {
            "status": new_status.value,
            "responded_at": responded_at,
            "reviewed_by_user_id": reviewed_by_user_id,
        }
        if requested_at is not None:
            fields["requested_at"] = requested_at
        return self._member_response(
            self.member_repo.update_membership(membership_id, **fields)
        )

    def _with_counts(self, collective: CollectiveResponse) -> CollectiveResponse:
        """Populate a collective's approved-member and distinct-owner counts."""
        approved = MembershipStatus.APPROVED.value
        collective.member_count = self.member_repo.count_members(
            collective.id, approved
        )
        collective.owner_count = self.member_repo.count_owners(collective.id, approved)
        return collective

    def _member_response(
        self,
        member: Optional[CollectiveMemberResponse],
    ) -> CollectiveMemberResponse:
        """Return the enriched membership response, or raise 500 if the write failed."""
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update membership",
            )
        return self._enrich(member)

    def _enrich(self, member: CollectiveMemberResponse) -> CollectiveMemberResponse:
        """Populate a single membership with its endpoint's identity."""
        return self._enrich_many([member])[0]

    def _enrich_many(
        self,
        members: List[CollectiveMemberResponse],
        endpoints: Optional[dict[int, Endpoint]] = None,
    ) -> List[CollectiveMemberResponse]:
        """Populate memberships with endpoint name/slug/owner/type in bulk."""
        if not members:
            return members
        if endpoints is None:
            endpoint_list = self.endpoint_repo.get_by_ids(
                list({m.endpoint_id for m in members})
            )
            endpoints = {ep.id: ep for ep in endpoint_list}
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }
        result: List[CollectiveMemberResponse] = []
        for member in members:
            endpoint = endpoints.get(member.endpoint_id)
            if endpoint is None:
                result.append(member)
                continue  # endpoint removed since the membership was created
            update: dict[str, str | None] = {
                "endpoint_name": endpoint.name,
                "endpoint_description": endpoint.description,
                "endpoint_slug": endpoint.slug,
                "endpoint_type": endpoint.type.value,
            }
            owner = owners.get(endpoint.user_id)
            if owner is not None:
                update["endpoint_owner_username"] = owner.username
                update["endpoint_owner_full_name"] = owner.full_name
            result.append(member.model_copy(update=update))
        return result

    def _build_invitation_context(
        self,
        collective: CollectiveResponse,
        endpoint: Endpoint,
        inviter: User,
    ) -> Optional[InvitationEmailContext]:
        """Build the notification-email context for an invited endpoint.

        Returns ``None`` when there is nobody to notify: an inviter who owns
        the endpoint themselves, or an owner with no email on file.
        """
        if endpoint.user_id == inviter.id:
            return None
        owner = self.user_repo.get_by_id(endpoint.user_id)
        if owner is None or not owner.email:
            return None
        return InvitationEmailContext(
            to_email=owner.email,
            recipient_name=owner.full_name or owner.username,
            inviter_name=inviter.full_name or inviter.username,
            collective_name=collective.name,
            collective_slug=collective.slug,
            endpoint_name=endpoint.name,
            endpoint_id=endpoint.id,
        )

    def _resolve_slug(self, data: CollectiveCreate) -> str:
        """Determine a unique slug for a new collective."""
        if data.slug:
            if self.collective_repo.slug_exists(data.slug):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Collective slug already taken",
                )
            return data.slug

        base = slugify_collective_name(data.name)
        if not self.collective_repo.slug_exists(base):
            return base
        # Collision on the derived slug — append a short random suffix.
        for _ in range(5):
            candidate = f"{base[:56]}-{secrets.token_hex(3)}"
            if not self.collective_repo.slug_exists(candidate):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not generate a unique slug; please supply one explicitly",
        )

    # ------------------------------------------------------------------
    # Shared endpoints — curated subsets of approved members
    # ------------------------------------------------------------------

    def list_shared_endpoints(
        self, collective_id: int
    ) -> List[CollectiveSharedEndpointResponse]:
        """List a collective's shared endpoints with active/inactive enrichment."""
        self._get_collective_or_404(collective_id)
        rows = self.shared_endpoint_repo.list_for_collective(collective_id)
        return self._enrich_shared_endpoints(collective_id, rows)

    def list_shared_endpoints_bulk(
        self, collective_ids: Sequence[int]
    ) -> List[CollectiveSharedEndpointResponse]:
        """Bulk-list shared endpoints for several collectives in one shot.

        Powers the chat-view's add-sources modal — a single request replaces
        the prior fan-out of one GET per collective. Unknown collective ids
        are silently skipped (they contribute zero rows) rather than 404ing
        the whole batch.
        """
        if not collective_ids:
            return []
        rows = self.shared_endpoint_repo.list_for_collectives(collective_ids)
        # Enrichment is per-collective (active membership is collective-
        # scoped), so bucket rows by parent before enriching.
        by_collective: dict[int, List[CollectiveSharedEndpointResponse]] = {}
        for row in rows:
            by_collective.setdefault(row.collective_id, []).append(row)
        enriched: List[CollectiveSharedEndpointResponse] = []
        for collective_id, group in by_collective.items():
            enriched.extend(self._enrich_shared_endpoints(collective_id, group))
        return enriched

    def list_shared_endpoints_by_slug(
        self, collective_slug: str
    ) -> List[CollectiveSharedEndpointResponse]:
        """List shared endpoints by parent collective slug (public)."""
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        rows = self.shared_endpoint_repo.list_for_collective(collective.id)
        return self._enrich_shared_endpoints(collective.id, rows)

    def get_shared_endpoint(
        self, collective_id: int, shared_slug: str
    ) -> CollectiveSharedEndpointResponse:
        """Get one shared endpoint by collective id + slug."""
        self._get_collective_or_404(collective_id)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        return self._enrich_shared_endpoint(collective_id, shared)

    def get_shared_endpoint_by_slugs(
        self, collective_slug: str, shared_slug: str
    ) -> CollectiveSharedEndpointResponse:
        """Get one shared endpoint by collective slug + own slug (public)."""
        collective = self.collective_repo.get_by_slug(collective_slug)
        if collective is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Collective not found",
            )
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective.id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        return self._enrich_shared_endpoint(collective.id, shared)

    def create_shared_endpoint(
        self,
        collective_id: int,
        data: CollectiveSharedEndpointCreate,
        current_user: User,
    ) -> CollectiveSharedEndpointResponse:
        """Create a shared endpoint under a collective.

        Validates that every ``endpoint_ids`` entry is currently an approved
        member of the collective — owners can't smuggle in pending, rejected,
        or unrelated endpoints. Slug is auto-derived from the name when
        omitted, with collision resolution mirroring the collective slug
        helper.
        """
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)

        approved_ids = self._approved_endpoint_ids(collective_id)
        unknown = [eid for eid in data.endpoint_ids if eid not in approved_ids]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Every endpoint must be an approved member of this "
                    "collective. Not approved: "
                    f"{', '.join(str(eid) for eid in unknown)}"
                ),
            )

        slug = self._resolve_shared_endpoint_slug(collective_id, data)
        created = self.shared_endpoint_repo.create_shared_endpoint(
            collective_id=collective_id,
            name=data.name,
            slug=slug,
            description=data.description,
            endpoint_ids=data.endpoint_ids,
            collective_slug=collective.slug,
        )
        if created is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create shared endpoint",
            )
        return self._enrich_shared_endpoint(collective_id, created)

    def update_shared_endpoint(
        self,
        collective_id: int,
        shared_slug: str,
        data: CollectiveSharedEndpointUpdate,
        current_user: User,
    ) -> CollectiveSharedEndpointResponse:
        """Update a shared endpoint's name/description and (optionally) members."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )

        endpoint_ids: Optional[List[int]] = None
        if data.endpoint_ids is not None:
            approved_ids = self._approved_endpoint_ids(collective_id)
            unknown = [eid for eid in data.endpoint_ids if eid not in approved_ids]
            if unknown:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Every endpoint must be an approved member of this "
                        "collective. Not approved: "
                        f"{', '.join(str(eid) for eid in unknown)}"
                    ),
                )
            endpoint_ids = list(data.endpoint_ids)

        fields = data.model_dump(exclude_unset=True, exclude={"endpoint_ids"})
        if not fields and endpoint_ids is None:
            return self._enrich_shared_endpoint(collective_id, shared)

        updated = self.shared_endpoint_repo.update_shared_endpoint(
            shared.id,
            fields=fields,
            endpoint_ids=endpoint_ids,
            collective_slug=collective.slug,
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update shared endpoint",
            )
        return self._enrich_shared_endpoint(collective_id, updated)

    def delete_shared_endpoint(
        self,
        collective_id: int,
        shared_slug: str,
        current_user: User,
    ) -> None:
        """Delete a shared endpoint (cascades to its member rows)."""
        collective = self._get_collective_or_404(collective_id)
        self._require_owner(collective, current_user)
        shared = self.shared_endpoint_repo.get_by_collective_and_slug(
            collective_id, shared_slug
        )
        if shared is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared endpoint not found",
            )
        if not self.shared_endpoint_repo.delete_shared_endpoint(shared.id):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete shared endpoint",
            )

    # ------------------------------------------------------------------
    # Shared-endpoint helpers
    # ------------------------------------------------------------------

    def _resolve_shared_endpoint_slug(
        self, collective_id: int, data: CollectiveSharedEndpointCreate
    ) -> str:
        """Determine a unique slug for a new shared endpoint within a collective."""
        if data.slug:
            if self.shared_endpoint_repo.slug_exists(collective_id, data.slug):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Shared endpoint slug already taken in this collective",
                )
            return data.slug

        base = slugify_shared_endpoint_name(data.name)
        # Reserved slugs (e.g. ``all``) short-circuit the resolver before the
        # row is consulted, so a persisted reserved slug is unreachable. Treat
        # the collision the same way as a duplicate and fall through.
        if (
            base not in RESERVED_SHARED_ENDPOINT_SLUGS
            and not self.shared_endpoint_repo.slug_exists(collective_id, base)
        ):
            return base
        # Strip the trailing '-' that ``[:56]`` may have exposed so the
        # appended random token doesn't introduce a forbidden '--' sequence.
        prefix = base[:56].rstrip("-") or "shared"
        for _ in range(5):
            candidate = f"{prefix}-{secrets.token_hex(3)}"
            if (
                candidate not in RESERVED_SHARED_ENDPOINT_SLUGS
                and not self.shared_endpoint_repo.slug_exists(collective_id, candidate)
            ):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not generate a unique slug; please supply one explicitly",
        )

    def _approved_endpoint_ids(self, collective_id: int) -> set[int]:
        """Set of endpoint ids currently approved in the collective."""
        memberships = self.member_repo.list_members(
            collective_id, [MembershipStatus.APPROVED.value]
        )
        return {m.endpoint_id for m in memberships}

    def _collective_approved_paths(self, collective_id: int) -> List[str]:
        """Owner/slug paths of every approved member endpoint."""
        memberships = self.member_repo.list_members(
            collective_id, [MembershipStatus.APPROVED.value]
        )
        enriched = self._enrich_many(memberships)
        return [
            f"{m.endpoint_owner_username}/{m.endpoint_slug}"
            for m in enriched
            if m.endpoint_owner_username and m.endpoint_slug
        ]

    def _resolve_endpoint_paths(self, endpoint_ids: Sequence[int]) -> List[str]:
        """Resolve endpoint ids to ``owner/slug`` strings, preserving input order."""
        if not endpoint_ids:
            return []
        endpoints = {
            ep.id: ep for ep in self.endpoint_repo.get_by_ids(list(endpoint_ids))
        }
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoints.values()})
            )
        }
        paths: List[str] = []
        for endpoint_id in endpoint_ids:
            endpoint = endpoints.get(endpoint_id)
            if endpoint is None:
                continue
            owner = owners.get(endpoint.user_id)
            if owner is None:
                continue
            paths.append(f"{owner.username}/{endpoint.slug}")
        return paths

    def _enrich_shared_endpoint(
        self,
        collective_id: int,
        shared: CollectiveSharedEndpointResponse,
    ) -> CollectiveSharedEndpointResponse:
        """Populate ``members``, ``member_count`` and ``active_member_count``."""
        return self._enrich_shared_endpoints(collective_id, [shared])[0]

    def _enrich_shared_endpoints(
        self,
        collective_id: int,
        rows: List[CollectiveSharedEndpointResponse],
    ) -> List[CollectiveSharedEndpointResponse]:
        """Bulk-enrich shared endpoints with member summaries + counts."""
        if not rows:
            return rows
        approved_ids = self._approved_endpoint_ids(collective_id)
        configured = self.shared_endpoint_member_repo.list_endpoint_ids_bulk(
            [row.id for row in rows]
        )
        endpoint_ids_all: set[int] = set()
        for ids in configured.values():
            endpoint_ids_all.update(ids)
        endpoint_map = {
            ep.id: ep for ep in self.endpoint_repo.get_by_ids(list(endpoint_ids_all))
        }
        owners = {
            owner.id: owner
            for owner in self.user_repo.get_by_ids(
                list({ep.user_id for ep in endpoint_map.values()})
            )
        }

        enriched: List[CollectiveSharedEndpointResponse] = []
        for row in rows:
            ids = configured.get(row.id, [])
            members: List[CollectiveSharedEndpointMemberSummary] = []
            active = 0
            for endpoint_id in ids:
                endpoint = endpoint_map.get(endpoint_id)
                if endpoint is None:
                    # Endpoint is configured but missing from endpoint_repo —
                    # owner soft-deleted it (is_active=False) so the join row
                    # outlived the endpoint. Emit a placeholder so the owner
                    # can still see and remove the dangling configuration; an
                    # endpoint that is missing cannot be approved, so it
                    # contributes to ``member_count`` but never to
                    # ``active_member_count``.
                    members.append(
                        CollectiveSharedEndpointMemberSummary(
                            endpoint_id=endpoint_id,
                            endpoint_name=None,
                            endpoint_slug=None,
                            endpoint_owner_username=None,
                            endpoint_type=None,
                            is_active=False,
                        )
                    )
                    continue
                is_active = endpoint_id in approved_ids
                if is_active:
                    active += 1
                owner = owners.get(endpoint.user_id)
                members.append(
                    CollectiveSharedEndpointMemberSummary(
                        endpoint_id=endpoint.id,
                        endpoint_name=endpoint.name,
                        endpoint_slug=endpoint.slug,
                        endpoint_owner_username=(
                            owner.username if owner is not None else None
                        ),
                        endpoint_type=endpoint.type.value,
                        is_active=is_active,
                    )
                )
            enriched.append(
                row.model_copy(
                    update={
                        "members": members,
                        # ``len(ids)`` rather than ``len(members)`` so the
                        # count matches the schema's "Total configured
                        # members" contract even when an endpoint is missing.
                        "member_count": len(ids),
                        "active_member_count": active,
                    }
                )
            )
        return enriched
