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
    get_endpoint_repository,
    get_organization_member_repository,
    get_organization_repository,
    get_user_repository,
)
from syfthub.repositories.endpoint import EndpointRepository
from syfthub.repositories.organization import (
    OrganizationMemberRepository,
    OrganizationRepository,
)
from syfthub.repositories.user import UserRepository
from syfthub.schemas.endpoint import (
    Endpoint,
    EndpointPublicResponse,
    EndpointResponse,
    EndpointVisibility,
)
from syfthub.schemas.organization import Organization
from syfthub.schemas.user import User

# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# Local helper functions to avoid circular imports
def can_access_endpoint(endpoint: Endpoint, current_user: Optional[User]) -> bool:
    """Check if user can access a endpoint based on visibility."""
    if endpoint.visibility == EndpointVisibility.PUBLIC:
        return True

    if current_user is None:
        return False

    # Owner can always access
    if current_user.id == endpoint.user_id:
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


def get_owner_endpoints(
    owner: Union[User, Organization], owner_type: str, endpoint_repo: EndpointRepository
) -> list[Endpoint]:
    """Get endpoints for an owner (user or organization)."""
    if owner_type == "user":
        # Get user's endpoints
        return endpoint_repo.get_user_endpoints(owner.id)
    elif owner_type == "organization":
        # Get organization's endpoints
        return endpoint_repo.get_organization_endpoints(owner.id)
    return []


def get_endpoint_by_owner_and_slug(
    owner: Union[User, Organization],
    owner_type: str,
    slug: str,
    endpoint_repo: EndpointRepository,
) -> Optional[Endpoint]:
    """Get endpoint by owner and slug."""
    if owner_type == "user":
        return endpoint_repo.get_by_user_and_slug(owner.id, slug)
    elif owner_type == "organization":
        return endpoint_repo.get_by_organization_and_slug(owner.id, slug)
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


def can_access_endpoint_with_org(
    endpoint: Endpoint,
    current_user: Optional[User],
    owner_type: str,
    member_repo: Optional[OrganizationMemberRepository] = None,
) -> bool:
    """Check if user can access endpoint, considering organization membership."""
    # Public endpoints are always accessible
    if endpoint.visibility == EndpointVisibility.PUBLIC:
        return True

    # Unauthenticated users can only see public endpoints
    if current_user is None:
        return False

    # Admin can access everything
    if current_user.role == "admin":
        return True

    # For user-owned endpoints, use existing logic
    if owner_type == "user" and endpoint.user_id:
        return can_access_endpoint(endpoint, current_user)

    # For organization-owned endpoints
    if owner_type == "organization" and endpoint.organization_id:
        # If no member_repo provided, cannot check organization membership
        if member_repo is None:
            return False

        # Owner/members can access internal endpoints
        if endpoint.visibility == EndpointVisibility.INTERNAL:
            return is_organization_member(
                endpoint.organization_id, current_user.id, member_repo
            )

        # Private endpoints only for organization members
        if endpoint.visibility == EndpointVisibility.PRIVATE:
            return is_organization_member(
                endpoint.organization_id, current_user.id, member_repo
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
@app.get("/{owner_slug}", response_model=list[EndpointPublicResponse])
async def list_owner_public_endpoints(
    owner_slug: str,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    endpoint_repo: Annotated[EndpointRepository, Depends(get_endpoint_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
) -> list[EndpointPublicResponse]:
    """List an owner's (user or organization) public endpoints."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug, user_repo, org_repo)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"'{owner_slug}' not found"
        )

    # Get owner's endpoints
    owner_endpoints = get_owner_endpoints(owner, owner_type, endpoint_repo)

    # Filter to only show endpoints the current user can access
    accessible_endpoints = []
    for endpoint in owner_endpoints:
        if not endpoint.is_active:
            continue

        # Check access permissions
        if can_access_endpoint_with_org(
            endpoint, current_user, owner_type, member_repo
        ):
            # For public listing, show different levels based on access
            if endpoint.visibility == EndpointVisibility.PUBLIC:
                accessible_endpoints.append(endpoint)
            elif current_user and (
                (owner_type == "user" and current_user.id == endpoint.user_id)
                or (
                    owner_type == "organization"
                    and endpoint.organization_id is not None
                    and is_organization_member(
                        endpoint.organization_id, current_user.id, member_repo
                    )
                )
            ):
                # Allow owner/members to see their own endpoints in public listing
                accessible_endpoints.append(endpoint)

    # Sort by most recent first
    accessible_endpoints.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    accessible_endpoints = accessible_endpoints[skip : skip + limit]

    # Build response with owner_username
    response_list = []
    for ds in accessible_endpoints:
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
        response_list.append(EndpointPublicResponse.model_validate(ds_dict))

    return response_list


@app.get("/{owner_slug}/{endpoint_slug}", response_model=None)
async def get_owner_endpoint(
    request: Request,
    owner_slug: str,
    endpoint_slug: str,
    current_user: Annotated[Optional[User], Depends(get_optional_current_user)],
    endpoint_repo: Annotated[EndpointRepository, Depends(get_endpoint_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    org_repo: Annotated[OrganizationRepository, Depends(get_organization_repository)],
    member_repo: Annotated[
        OrganizationMemberRepository, Depends(get_organization_member_repository)
    ],
) -> Union[HTMLResponse, EndpointResponse, EndpointPublicResponse]:
    """Get a specific endpoint by owner and slug."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug, user_repo, org_repo)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or endpoint not found"
        )

    # Get endpoint by owner and slug
    endpoint = get_endpoint_by_owner_and_slug(
        owner, owner_type, endpoint_slug.lower(), endpoint_repo
    )
    if not endpoint or not endpoint.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or endpoint not found"
        )

    # Check access permissions
    if not can_access_endpoint_with_org(
        endpoint, current_user, owner_type, member_repo
    ):
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to access this endpoint",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            # Return 404 for private endpoints to hide existence (like GitHub)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Owner or endpoint not found",
            )

    # Return full details if user is owner/admin/org member, public details otherwise
    can_see_full_details = False
    if current_user:
        if current_user.role == "admin" or (
            owner_type == "user" and current_user.id == endpoint.user_id
        ):
            can_see_full_details = True
        elif owner_type == "organization" and endpoint.organization_id:
            can_see_full_details = is_organization_member(
                endpoint.organization_id, current_user.id, member_repo
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
        if endpoint.readme and endpoint.readme.strip():
            readme_html = markdown.markdown(
                endpoint.readme, extensions=["codehilite", "fenced_code"]
            )

        return templates.TemplateResponse(
            "endpoint.html",
            {
                "request": request,
                "endpoint": endpoint,
                "owner_name": owner_name,
                "owner_slug": owner_slug,
                "readme_html": readme_html,
                "can_see_full_details": can_see_full_details,
            },
        )
    else:
        # Return JSON for API clients
        if can_see_full_details:
            return EndpointResponse.model_validate(endpoint)
        else:
            # Build public response with owner_username
            endpoint_dict = endpoint.model_dump()
            # Get the appropriate username/slug based on owner type
            if owner_type == "user":
                from syfthub.schemas.user import User

                endpoint_dict["owner_username"] = (
                    owner.username if isinstance(owner, User) else ""
                )
            else:
                from syfthub.schemas.organization import Organization

                endpoint_dict["owner_username"] = (
                    owner.slug if isinstance(owner, Organization) else ""
                )
            return EndpointPublicResponse.model_validate(endpoint_dict)


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
