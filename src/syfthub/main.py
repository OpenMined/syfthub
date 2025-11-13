"""Main FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import markdown  # type: ignore
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates

from syfthub import __version__
from syfthub.api.endpoints.datasites import (
    can_access_datasite,
    fake_datasites_db,
    get_datasite_by_slug,
    user_datasites_lookup,
)
from syfthub.api.endpoints.organizations import (
    get_organization_by_slug,
    is_organization_member,
)
from syfthub.api.router import api_router
from syfthub.auth.dependencies import get_optional_current_user, get_user_by_username
from syfthub.core.config import settings
from syfthub.database.connection import create_tables
from syfthub.schemas.datasite import (
    Datasite,
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteVisibility,
)

if TYPE_CHECKING:
    from fastapi.responses import HTMLResponse

    from syfthub.schemas.organization import Organization
    from syfthub.schemas.user import User


# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def resolve_owner(owner_slug: str) -> tuple[User | Organization | None, str]:
    """Resolve owner slug to either user or organization.

    Returns:
        Tuple of (owner_object, owner_type) where owner_type is 'user' or 'organization'
    """
    # Try to find user first
    user = get_user_by_username(owner_slug.lower())
    if user:
        return user, "user"

    # Try to find organization
    organization = get_organization_by_slug(owner_slug.lower())
    if organization and organization.is_active:
        return organization, "organization"

    return None, ""


def get_owner_datasites(owner: User | Organization, owner_type: str) -> list[Datasite]:
    """Get datasites for an owner (user or organization)."""
    if owner_type == "user":
        # Get user's datasites
        user_datasite_ids = user_datasites_lookup.get(owner.id, set())
        return [
            fake_datasites_db[ds_id]
            for ds_id in user_datasite_ids
            if ds_id in fake_datasites_db
            and fake_datasites_db[ds_id].user_id == owner.id
        ]
    elif owner_type == "organization":
        # Get organization's datasites
        return [
            datasite
            for datasite in fake_datasites_db.values()
            if datasite.organization_id == owner.id
        ]
    return []


def get_datasite_by_owner_and_slug(
    owner: User | Organization, owner_type: str, slug: str
) -> Datasite | None:
    """Get datasite by owner and slug."""
    if owner_type == "user":
        return get_datasite_by_slug(owner.id, slug)
    elif owner_type == "organization":
        # Look for datasite with organization_id and slug
        for datasite in fake_datasites_db.values():
            if datasite.organization_id == owner.id and datasite.slug == slug:
                return datasite
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
    datasite: Datasite, current_user: User | None, owner_type: str
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
        # Owner/members can access internal datasites
        if datasite.visibility == DatasiteVisibility.INTERNAL:
            return is_organization_member(datasite.organization_id, current_user.id)

        # Private datasites only for organization members
        if datasite.visibility == DatasiteVisibility.PRIVATE:
            return is_organization_member(datasite.organization_id, current_user.id)

    return False


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifecycle."""
    # Startup
    print(f"Starting Syfthub API v{__version__}")
    print("Initializing database...")
    create_tables()
    print("Database initialized successfully.")
    yield
    # Shutdown
    print("Shutting down Syfthub API")


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
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[DatasitePublicResponse]:
    """List an owner's (user or organization) public datasites."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"'{owner_slug}' not found"
        )

    # Get owner's datasites
    owner_datasites = get_owner_datasites(owner, owner_type)

    # Filter to only show datasites the current user can access
    accessible_datasites = []
    for datasite in owner_datasites:
        if not datasite.is_active:
            continue

        # Check access permissions
        if can_access_datasite_with_org(datasite, current_user, owner_type):
            # For public listing, show different levels based on access
            if datasite.visibility == DatasiteVisibility.PUBLIC:
                accessible_datasites.append(datasite)
            elif current_user and (
                (owner_type == "user" and current_user.id == datasite.user_id)
                or (
                    owner_type == "organization"
                    and datasite.organization_id is not None
                    and is_organization_member(
                        datasite.organization_id, current_user.id
                    )
                )
            ):
                # Allow owner/members to see their own datasites in public listing
                accessible_datasites.append(datasite)

    # Sort by most recent first
    accessible_datasites.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    accessible_datasites = accessible_datasites[skip : skip + limit]

    return [DatasitePublicResponse.model_validate(ds) for ds in accessible_datasites]


@app.get("/{owner_slug}/{datasite_slug}")
async def get_owner_datasite(
    request: Request,
    owner_slug: str,
    datasite_slug: str,
    current_user: User | None = Depends(get_optional_current_user),
) -> HTMLResponse | DatasiteResponse | DatasitePublicResponse:
    """Get a specific datasite by owner and slug."""
    # Resolve owner (user or organization)
    owner, owner_type = resolve_owner(owner_slug)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or datasite not found"
        )

    # Get datasite by owner and slug
    datasite = get_datasite_by_owner_and_slug(owner, owner_type, datasite_slug.lower())
    if not datasite or not datasite.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Owner or datasite not found"
        )

    # Check access permissions
    if not can_access_datasite_with_org(datasite, current_user, owner_type):
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
                datasite.organization_id, current_user.id
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
            return DatasitePublicResponse.model_validate(datasite)


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
