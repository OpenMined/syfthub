"""Main FastAPI application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional, Union

import markdown
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from syfthub import __version__
from syfthub.api.router import api_router
from syfthub.auth.db_dependencies import get_optional_current_user
from syfthub.core.config import settings
from syfthub.database.connection import create_tables
from syfthub.database.dependencies import (
    get_datasite_repository,
    get_organization_member_repository,
    get_organization_repository,
    get_user_repository,
)
from syfthub.repositories.datasite import DatasiteRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.datasite import (
    Datasite,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteVisibility,
)
from syfthub.schemas.organization import Organization
from syfthub.schemas.user import User

# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# Local helper functions to avoid circular imports
def can_access_datasite(datasite: Datasite, current_user: Optional[User]) -> bool:
    """Check if user can access a datasite based on visibility."""
    if datasite.visibility == DatasiteVisibility.PUBLIC:
        return True

    if current_user is None:
        return False

    # Owner can always access
    if current_user.id == datasite.user_id:
        return True

    # Admin can access everything
    return current_user.role == "admin"


def is_organization_member(
    org_id: int, user_id: int, member_repo: OrganizationMemberRepository
) -> bool:
    """Check if user is member of organization."""
    return member_repo.is_member(org_id, user_id)


def resolve_owner(
    owner_slug: str, user_repo: UserRepository, org_repo: OrganizationRepository
) -> tuple[Optional[Union[User, Organization]], str]:
    """Resolve owner slug to either user or organization.

    Returns:
        Tuple of (owner_object, owner_type) where owner_type is 'user' or 'organization'
    """
    # Try to find user first
    user = user_repo.get_by_username(owner_slug.lower())
    if user:
        return user, "user"

    # Try to find organization
    organization = org_repo.get_by_slug(owner_slug.lower())
    if organization and organization.is_active:
        return organization, "organization"

    return None, ""


def get_owner_datasites(
    owner: Union[User, Organization], owner_type: str, datasite_repo: DatasiteRepository
) -> list[Datasite]:
    """Get datasites for an owner (user or organization)."""
    if owner_type == "user":
        # Get user's datasites
        return datasite_repo.get_user_datasites(owner.id)
    elif owner_type == "organization":
        # Get organization's datasites
        return datasite_repo.get_organization_datasites(owner.id)
    return []


def get_datasite_by_owner_and_slug(
    owner: Union[User, Organization],
    owner_type: str,
    slug: str,
    datasite_repo: DatasiteRepository,
) -> Optional[Datasite]:
    """Get datasite by owner and slug."""
    if owner_type == "user":
        return datasite_repo.get_by_user_and_slug(owner.id, slug)
    elif owner_type == "organization":
        return datasite_repo.get_by_organization_and_slug(owner.id, slug)
    return None


def is_browser_request(request: Request) -> bool:
    """Check if request is from a browser (wants HTML) vs API client (wants JSON)."""
    accept_header = request.headers.get("accept", "")
    user_agent = request.headers.get("user-agent", "")

    # Check if client specifically wants HTML
    if "text/html" in accept_header:
        return True

    # Check if it's a browser user agent
    browser_indicators = ["Mozilla", "Chrome", "Safari", "Firefox", "Edge"]
    return any(indicator in user_agent for indicator in browser_indicators)


def can_access_datasite_with_org(
    datasite: Datasite,
    current_user: Optional[User],
    owner_type: str,
    member_repo: Optional[OrganizationMemberRepository] = None,
) -> bool:
    """Check if user can access datasite, considering organization membership."""
    # Public datasites are always accessible
    if datasite.visibility == DatasiteVisibility.PUBLIC:
        return True

    # Unauthenticated users can only see public datasites
    if current_user is None:
        return False

    # Admin can access everything
    if current_user.role == "admin":
        return True

    # For user-owned datasites, use existing logic
    if owner_type == "user" and datasite.user_id:
        return can_access_datasite(datasite, current_user)

    # For organization-owned datasites
    if owner_type == "organization" and datasite.organization_id:
        # If no member_repo provided, cannot check organization membership
        if member_repo is None:
            return False

        # Owner/members can access internal datasites
        if datasite.visibility == DatasiteVisibility.INTERNAL:
            return is_organization_member(
                datasite.organization_id, current_user.id, member_repo
            )

        # Private datasites only for organization members
        if datasite.visibility == DatasiteVisibility.PRIVATE:
            return is_organization_member(
                datasite.organization_id, current_user.id, member_repo
            )

    return False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    # Startup
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Starting Syfthub API v{__version__}")
    logger.info("Initializing database...")
    create_tables()
    logger.info("Database initialized successfully.")
    yield
    # Shutdown
    logger.info("Shutting down Syfthub API")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "message": "Welcome to Syfthub API",
        "version": __version__,
        "docs": "/docs",
    }


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": __version__}


# Special routes for GitHub-like URLs (must be last to avoid conflicts)
@app.get("/{owner_slug}", response_model=list[DatasitePublicResponse])
async def list_owner_public_datasites(
    owner_slug: str,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[DatasitePublicResponse]:
    """List an owner's (user or organization) public datasites."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug, user_repo, org_repo)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"'{owner_slug}' not found"
        )

    # Get owner's datasites
    owner_datasites = get_owner_datasites(owner, owner_type, datasite_repo)

    # Filter to only show datasites the current user can access
    accessible_datasites = []
    for datasite in owner_datasites:
        if not datasite.is_active:
            continue

        # Check access permissions
        if can_access_datasite_with_org(
            datasite, current_user, owner_type, member_repo
        ):
            # For public listing, show different levels based on access
            if datasite.visibility == DatasiteVisibility.PUBLIC:
                accessible_datasites.append(datasite)
            elif current_user and (
                (owner_type == "user" and current_user.id == datasite.user_id)
                or (
                    owner_type == "organization"
                    and datasite.organization_id is not None
                    and is_organization_member(
                        datasite.organization_id, current_user.id, member_repo
                    )
                )
            ):
                # Allow owner/members to see their own datasites in public listing
                accessible_datasites.append(datasite)

    # Sort by most recent first
    accessible_datasites.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    accessible_datasites = accessible_datasites[skip : skip + limit]

    # Build response with owner_username
    response_list = []
    for ds in accessible_datasites:
        ds_dict = ds.model_dump()
        # Get the appropriate username/slug based on owner type
        if owner_type == "user":
            from syfthub.schemas.user import User

            ds_dict["owner_username"] = (
                owner.username if isinstance(owner, User) else ""
            )
        else:
            from syfthub.schemas.organization import Organization

            ds_dict["owner_username"] = (
                owner.slug if isinstance(owner, Organization) else ""
            )
        response_list.append(DatasitePublicResponse.model_validate(ds_dict))

    return response_list


@app.get("/{owner_slug}/{datasite_slug}", response_model=None)
async def get_owner_datasite(
    request: Request,
    owner_slug: str,
    datasite_slug: str,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    datasite_repo: Annotated[DatasiteRepository, Depends(get_datasite_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> Union[HTMLResponse, DatasiteResponse, DatasitePublicResponse]:
    """Get a specific datasite by owner and slug."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug, user_repo, org_repo)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or datasite not found"
        )

    # Get datasite by owner and slug
    datasite = get_datasite_by_owner_and_slug(
        owner, owner_type, datasite_slug.lower(), datasite_repo
    )
    if not datasite or not datasite.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or datasite not found"
        )

    # Check access permissions
    if not can_access_datasite_with_org(
        datasite, current_user, owner_type, member_repo
    ):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this datasite",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            # Return 404 for private datasites to hide existence (like GitHub)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Owner or datasite not found",
            )

    # Return full details if user is owner/admin/org member, public details otherwise
    can_see_full_details = False
    if current_user:
        if current_user.role == "admin" or (
            owner_type == "user" and current_user.id == datasite.user_id
        ):
            can_see_full_details = True
        elif owner_type == "organization" and datasite.organization_id:
            can_see_full_details = is_organization_member(
                datasite.organization_id, current_user.id, member_repo
            )

    # Check if this is a browser request (wants HTML) or API request (wants JSON)
    if is_browser_request(request):
        # Render HTML template for browsers
        if owner_type == "user":
            from syfthub.schemas.user import User

            owner_name = owner.username if isinstance(owner, User) else ""
        else:
            from syfthub.schemas.organization import Organization

            owner_name = owner.name if isinstance(owner, Organization) else ""

        # Convert README markdown to HTML
        readme_html = ""
        if datasite.readme and datasite.readme.strip():
            readme_html = markdown.markdown(
                datasite.readme, extensions=["codehilite", "fenced_code"]
            )

        return templates.TemplateResponse(
            "datasite.html",
            {
                "request": request,
                "datasite": datasite,
                "owner_name": owner_name,
                "owner_slug": owner_slug,
                "readme_html": readme_html,
                "can_see_full_details": can_see_full_details,
            },
        )
    else:
        # Return JSON for API clients
        if can_see_full_details:
            return DatasiteResponse.model_validate(datasite)
        else:
            # Build public response with owner_username
            datasite_dict = datasite.model_dump()
            # Get the appropriate username/slug based on owner type
            if owner_type == "user":
                from syfthub.schemas.user import User

                datasite_dict["owner_username"] = (
                    owner.username if isinstance(owner, User) else ""
                )
            else:
                from syfthub.schemas.organization import Organization

                datasite_dict["owner_username"] = (
                    owner.slug if isinstance(owner, Organization) else ""
                )
            return DatasitePublicResponse.model_validate(datasite_dict)


def main() -> None:
    """Entry point for running the server via script."""
    import uvicorn

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
