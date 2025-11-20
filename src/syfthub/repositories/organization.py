"""Organization repository for database operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError

from syfthub.models.organization import OrganizationMemberModel, OrganizationModel
from syfthub.repositories.base import BaseRepository
from syfthub.schemas.organization import (
    Organization,
    OrganizationCreate,
    OrganizationMemberCreate,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationRole,
    OrganizationUpdate,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class OrganizationRepository(BaseRepository[OrganizationModel]):
    """Repository for organization database operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, OrganizationModel)

    def get_by_slug(self, slug: str) -> Optional[Organization]:
        """Get organization by slug."""
        try:
            stmt = select(self.model).where(self.model.slug == slug.lower())
            result = self.session.execute(stmt)
            org_model = result.scalar_one_or_none()

            if org_model:
                return Organization.model_validate(org_model)
            return None
        except SQLAlchemyError:
            return None

    def get_by_id(self, org_id: int) -> Optional[Organization]:
        """Get organization by ID."""
        try:
            org_model = self.session.get(self.model, org_id)
            if org_model:
                return Organization.model_validate(org_model)
            return None
        except SQLAlchemyError:
            return None

    def create_organization(
        self, org_data: OrganizationCreate
    ) -> Optional[Organization]:
        """Create a new organization."""
        try:
            org_model = OrganizationModel(
                name=org_data.name,
                slug=org_data.slug or self._generate_slug_from_name(org_data.name),
                description=org_data.description,
                avatar_url=org_data.avatar_url,
                is_active=org_data.is_active,
            )

            self.session.add(org_model)
            self.session.commit()
            self.session.refresh(org_model)

            return Organization.model_validate(org_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def update_organization(
        self, org_id: int, org_data: OrganizationUpdate
    ) -> Optional[Organization]:
        """Update organization information."""
        try:
            org_model = self.session.get(self.model, org_id)
            if not org_model:
                return None

            # Update fields if provided
            if org_data.name is not None:
                org_model.name = org_data.name
            if org_data.description is not None:
                org_model.description = org_data.description
            if org_data.avatar_url is not None:
                org_model.avatar_url = org_data.avatar_url
            if org_data.is_active is not None:
                org_model.is_active = org_data.is_active

            self.session.commit()
            self.session.refresh(org_model)

            return Organization.model_validate(org_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def slug_exists(self, slug: str, exclude_org_id: Optional[int] = None) -> bool:
        """Check if slug already exists."""
        try:
            stmt = select(self.model).where(self.model.slug == slug.lower())
            if exclude_org_id:
                stmt = stmt.where(self.model.id != exclude_org_id)

            result = self.session.execute(stmt.limit(1))
            return result.scalar() is not None
        except SQLAlchemyError:
            return False

    def _generate_slug_from_name(self, name: str) -> str:
        """Generate a URL-safe slug from organization name."""
        import re

        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())

        # Remove leading/trailing hyphens
        slug = slug.strip("-")

        # Ensure minimum length
        if len(slug) < 3:
            slug = f"org-{slug}"

        # Truncate if too long
        if len(slug) > 63:
            slug = slug[:63].rstrip("-")

        # Ensure uniqueness
        counter = 1
        original_slug = slug
        while self.slug_exists(slug):
            slug = f"{original_slug}-{counter}"
            counter += 1

        return slug


class OrganizationMemberRepository(BaseRepository[OrganizationMemberModel]):
    """Repository for organization member operations."""

    def __init__(self, session: Session):
        """Initialize repository with database session."""
        super().__init__(session, OrganizationMemberModel)

    def add_member(
        self, member_data: OrganizationMemberCreate, org_id: int
    ) -> Optional[OrganizationMemberResponse]:
        """Add a member to an organization."""
        try:
            # Check if membership already exists
            if self.is_member(org_id, member_data.user_id):
                return None

            member_model = OrganizationMemberModel(
                organization_id=org_id,
                user_id=member_data.user_id,
                role=member_data.role.value,
                is_active=member_data.is_active,
            )

            self.session.add(member_model)
            self.session.commit()
            self.session.refresh(member_model)

            return OrganizationMemberResponse.model_validate(member_model)
        except SQLAlchemyError:
            self.session.rollback()
            return None

    def remove_member(self, org_id: int, user_id: int) -> bool:
        """Remove a member from an organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id, self.model.user_id == user_id
                )
            )
            result = self.session.execute(stmt)
            member = result.scalar_one_or_none()

            if member:
                self.session.delete(member)
                self.session.commit()
                return True
            return False
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def update_member_role(
        self, org_id: int, user_id: int, role: OrganizationRole
    ) -> bool:
        """Update a member's role in an organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id, self.model.user_id == user_id
                )
            )
            result = self.session.execute(stmt)
            member = result.scalar_one_or_none()

            if member:
                member.role = role.value
                self.session.commit()
                return True
            return False
        except SQLAlchemyError:
            self.session.rollback()
            return False

    def is_member(self, org_id: int, user_id: int) -> bool:
        """Check if user is a member of an organization."""
        return self.exists(organization_id=org_id, user_id=user_id, is_active=True)

    def get_member_role(self, org_id: int, user_id: int) -> Optional[OrganizationRole]:
        """Get a member's role in an organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.user_id == user_id,
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            member = result.scalar_one_or_none()

            if member:
                return OrganizationRole(member.role)
            return None
        except SQLAlchemyError:
            return None

    def get_organization_members(self, org_id: int) -> List[OrganizationMemberResponse]:
        """Get all members of an organization."""
        try:
            stmt = (
                select(self.model)
                .where(and_(self.model.organization_id == org_id, self.model.is_active))
                .order_by(self.model.joined_at)
            )

            result = self.session.execute(stmt)
            members = result.scalars().all()

            return [
                OrganizationMemberResponse.model_validate(member) for member in members
            ]
        except SQLAlchemyError:
            return []

    def get_user_organizations(self, user_id: int) -> List[OrganizationResponse]:
        """Get all organizations a user is a member of."""
        try:
            stmt = (
                select(OrganizationModel)
                .join(self.model)
                .where(
                    and_(
                        self.model.user_id == user_id,
                        self.model.is_active,
                        OrganizationModel.is_active,
                    )
                )
                .order_by(OrganizationModel.name)
            )

            result = self.session.execute(stmt)
            organizations = result.scalars().all()

            return [OrganizationResponse.model_validate(org) for org in organizations]
        except SQLAlchemyError:
            return []

    def count_owners(self, org_id: int) -> int:
        """Count the number of active owners in an organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.role == OrganizationRole.OWNER.value,
                    self.model.is_active,
                )
            )

            result = self.session.execute(stmt)
            owners = result.scalars().all()

            return len(owners)
        except SQLAlchemyError:
            return 0

    def update_member(
        self, org_id: int, user_id: int, member_update: dict
    ) -> Optional[OrganizationMemberResponse]:
        """Update a member's data in an organization."""
        try:
            stmt = select(self.model).where(
                and_(
                    self.model.organization_id == org_id,
                    self.model.user_id == user_id,
                    self.model.is_active,
                )
            )
            result = self.session.execute(stmt)
            member = result.scalar_one_or_none()

            if not member:
                return None

            # Update fields if provided
            if "role" in member_update:
                member.role = (
                    member_update["role"].value
                    if hasattr(member_update["role"], "value")
                    else member_update["role"]
                )
            if "is_active" in member_update:
                member.is_active = member_update["is_active"]

            self.session.commit()
            self.session.refresh(member)

            return OrganizationMemberResponse.model_validate(member)
        except SQLAlchemyError:
            self.session.rollback()
            return None
