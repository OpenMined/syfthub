"""Main FastAPI application."""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Optional, Union

import httpx
import markdown
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from syfthub import __version__
from syfthub.api.router import api_router
from syfthub.auth.db_dependencies import get_optional_current_user
from syfthub.auth.keys import key_manager
from syfthub.core.config import settings
from syfthub.core.url_builder import (
    build_connection_url,
    get_first_enabled_connection,
    transform_connection_urls,
)
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
    EndpointType,
    EndpointVisibility,
)
from syfthub.schemas.organization import Organization
from syfthub.schemas.user import User

# Setup Jinja2 templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Timeout configuration for endpoint proxying (in seconds)
PROXY_TIMEOUT_DATA_SOURCE = 30.0
PROXY_TIMEOUT_MODEL = 120.0


def build_invocation_url(
    owner: Union[User, Organization],
    connections: list[dict[str, Any]],
    endpoint_slug: str,
    endpoint_path: str,
) -> str:
    """Build the invocation URL from owner domain and connection config.

    Args:
        owner: The endpoint owner (User or Organization)
        connections: List of connection configurations from the endpoint
        endpoint_slug: The endpoint's slug for building the query path
        endpoint_path: Path identifier for error messages (e.g., "owner/endpoint")

    Returns:
        The full query URL for invoking the endpoint

    Raises:
        HTTPException: If no domain or connections are configured
    """
    # Check owner has a domain configured
    domain = getattr(owner, "domain", None)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Owner of endpoint '{endpoint_path}' has no domain configured",
        )

    if not connections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Endpoint '{endpoint_path}' has no connections configured",
        )

    # Get the first enabled connection
    connection = get_first_enabled_connection(connections)
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No enabled connection found for endpoint '{endpoint_path}'",
        )

    # Get connection type and path from config
    connection_type = connection.get("type", "rest_api")
    config = connection.get("config", {})
    path_suffix = config.get("url", "") or config.get("path", "")

    # Build the base URL from domain and path
    base_url = build_connection_url(domain, connection_type, path_suffix)
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not build URL for endpoint '{endpoint_path}'",
        )

    # Append the SyftAI-Space query pattern
    return f"{base_url.rstrip('/')}/api/v1/endpoints/{endpoint_slug}/query"


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

    # Initialize database
    logger.info("Initializing database...")
    create_tables()
    logger.info("Database initialized successfully.")

    # Initialize RSA Key Manager for Identity Provider
    logger.info("Initializing RSA Key Manager for Identity Provider...")
    try:
        key_manager.initialize()
        if key_manager.is_configured:
            logger.info(
                f"RSA keys loaded successfully. Key ID: {key_manager.current_key_id}"
            )
        else:
            logger.warning(
                "RSA keys not configured. Satellite token endpoints will be unavailable."
            )
    except Exception as e:
        logger.error(f"Failed to initialize RSA Key Manager: {e}")
        logger.warning("Satellite token endpoints will be unavailable.")

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
    # Disable automatic trailing slash redirects to avoid redirect issues
    # when running behind a reverse proxy (nginx) on a different port
    redirect_slashes=False,
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


# ===========================================
# IDENTITY PROVIDER (IdP) ENDPOINTS
# ===========================================


@app.get("/.well-known/jwks.json")
async def get_jwks() -> JSONResponse:
    """Get JSON Web Key Set (JWKS) for token verification.

    This endpoint exposes the Hub's public RSA keys in standard JWKS format.
    Satellite services (like SyftAI Space) fetch and cache these keys to
    verify tokens locally without calling the Hub for every request.

    No authentication required (FR-01).

    Returns:
        JSONResponse: JWKS containing public keys with Cache-Control headers

    Raises:
        HTTPException: 503 if keys are not configured
    """
    if not key_manager.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity Provider not configured. RSA keys are unavailable.",
        )

    jwks = key_manager.get_jwks()

    # Return with cache headers for satellite services
    return JSONResponse(
        content=jwks,
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Content-Type": "application/json",
        },
    )


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

    # Build response with owner_username and transformed URLs
    # Get owner's domain for URL transformation
    owner_domain = getattr(owner, "domain", None)

    response_list = []
    for ds in accessible_endpoints:
        ds_dict = ds.model_dump()

        # Transform connection URLs using owner's domain
        if ds_dict.get("connect"):
            ds_dict["connect"] = transform_connection_urls(
                owner_domain,
                ds_dict["connect"],
            )

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
        # Return JSON for API clients with transformed URLs
        # Get owner's domain for URL transformation
        owner_domain = getattr(owner, "domain", None)
        endpoint_dict = endpoint.model_dump()

        # Transform connection URLs using owner's domain
        if endpoint_dict.get("connect"):
            endpoint_dict["connect"] = transform_connection_urls(
                owner_domain,
                endpoint_dict["connect"],
            )

        if can_see_full_details:
            return EndpointResponse.model_validate(endpoint_dict)
        else:
            # Build public response with owner_username
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


@app.post("/{owner_slug}/{endpoint_slug}", response_model=None)
async def invoke_owner_endpoint(
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
) -> JSONResponse:
    """Invoke a specific endpoint by owner and slug.

    This endpoint handles POST requests to /{owner_slug}/{endpoint_slug} for
    invoking/executing the endpoint's functionality.
    """
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

    # Build invocation URL from owner's domain and connection config
    endpoint_path = f"{owner_slug}/{endpoint_slug}"

    # Convert Connection objects to dicts for the helper function
    connections_data = [
        conn.model_dump() if hasattr(conn, "model_dump") else dict(conn)
        for conn in endpoint.connect
    ]

    # Build the full query URL using owner's domain
    query_url = build_invocation_url(
        owner, connections_data, endpoint_slug, endpoint_path
    )

    # Get the request body
    try:
        request_body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON request body",
        ) from None

    # Set timeout based on endpoint type
    timeout = (
        PROXY_TIMEOUT_DATA_SOURCE
        if endpoint.type == EndpointType.DATA_SOURCE
        else PROXY_TIMEOUT_MODEL
    )

    # Prepare headers for the proxied request
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Forward X-Tenant-Name header if present (for multi-tenancy)
    tenant_header = request.headers.get("X-Tenant-Name")
    if tenant_header:
        headers["X-Tenant-Name"] = tenant_header

    # Make the proxied request to the target endpoint
    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                query_url,
                json=request_body,
                headers=headers,
            )

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Handle different response status codes
        if response.status_code == 200:
            # Success - return the response from the target endpoint
            try:
                response_data = response.json()
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=response_data,
                    headers={"X-Proxy-Latency-Ms": str(latency_ms)},
                )
            except Exception:
                # Response is not JSON, return as-is
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={"raw_response": response.text},
                    headers={"X-Proxy-Latency-Ms": str(latency_ms)},
                )

        elif response.status_code == 403:
            # Access denied by target endpoint
            try:
                error_detail = response.json().get("detail", "Access denied")
            except Exception:
                error_detail = response.text[:200] or "Access denied"

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Target endpoint denied access: {error_detail}",
            )

        else:
            # Other error from target endpoint
            try:
                error_data = response.json()
                error_detail = error_data.get("detail", str(error_data))
            except Exception:
                error_detail = response.text[:200] or f"HTTP {response.status_code}"

            raise HTTPException(
                status_code=response.status_code,
                detail=f"Target endpoint error: {error_detail}",
            )

    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Request to target endpoint timed out after {timeout}s",
        ) from None

    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to target endpoint: {e}",
        ) from None

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during proxy request: {e}",
        ) from None


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
