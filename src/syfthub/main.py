"""Main FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from syfthub import __version__
from syfthub.api.endpoints.datasites import (
    can_access_datasite,
    fake_datasites_db,
    get_datasite_by_slug,
    user_datasites_lookup,
)
from syfthub.api.router import api_router
from syfthub.auth.dependencies import get_optional_current_user, get_user_by_username
from syfthub.core.config import settings
from syfthub.database.connection import create_tables
from syfthub.schemas.datasite import (
    DatasitePublicResponse,
    DatasiteResponse,
    DatasiteVisibility,
)

if TYPE_CHECKING:
    from syfthub.schemas.user import User


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
@app.get("/{username}", response_model=list[DatasitePublicResponse])
async def list_user_public_datasites(
    username: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: User | None = Depends(get_optional_current_user),
) -> list[DatasitePublicResponse]:
    """List a user's public datasites by username."""
    # Get user by username
    user = get_user_by_username(username.lower())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{username}' not found"
        )

    # Get user's datasites
    user_datasite_ids = user_datasites_lookup.get(user.id, set())
    user_datasites = [
        fake_datasites_db[ds_id]
        for ds_id in user_datasite_ids
        if ds_id in fake_datasites_db
    ]

    # Filter to only show datasites the current user can access
    accessible_datasites = []
    for datasite in user_datasites:
        if not datasite.is_active:
            continue

        # For listing, only show public datasites to others
        # Owner and admin can see their own internal/private in the API endpoint
        if datasite.visibility == DatasiteVisibility.PUBLIC:
            accessible_datasites.append(datasite)
        elif (
            current_user
            and can_access_datasite(datasite, current_user)
            and current_user.id == datasite.user_id
        ):
            # Allow owner/admin to see their own datasites in this public listing
            accessible_datasites.append(datasite)

    # Sort by most recent first
    accessible_datasites.sort(key=lambda ds: ds.updated_at, reverse=True)

    # Apply pagination
    accessible_datasites = accessible_datasites[skip : skip + limit]

    return [DatasitePublicResponse.model_validate(ds) for ds in accessible_datasites]


@app.get("/{username}/{datasite_slug}")
async def get_user_datasite(
    username: str,
    datasite_slug: str,
    current_user: User | None = Depends(get_optional_current_user),
) -> DatasiteResponse | DatasitePublicResponse:
    """Get a specific datasite by username and slug."""
    # Get user by username
    user = get_user_by_username(username.lower())
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User or datasite not found"
        )

    # Get datasite by slug
    datasite = get_datasite_by_slug(user.id, datasite_slug.lower())
    if not datasite or not datasite.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User or datasite not found"
        )

    # Check access permissions
    if not can_access_datasite(datasite, current_user):
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
                detail="User or datasite not found",
            )

    # Return full details if user is owner/admin, public details otherwise
    if current_user and (
        current_user.id == datasite.user_id or current_user.role == "admin"
    ):
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
