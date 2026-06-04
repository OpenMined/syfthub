"""Admin user-overview dashboard endpoints.

All routes are admin-only, gated by ``require_admin`` (HS256 hub token belonging
to a user whose role == "admin"). Mounted under ``/api/v1/admin``.
"""

from datetime import datetime, timezone
from enum import IntEnum
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, Response

from syfthub.auth.db_dependencies import require_admin
from syfthub.database.dependencies import get_admin_stats_service
from syfthub.schemas.admin import AdminUserPage, UserOverviewStats
from syfthub.services.admin_stats_service import AdminStatsService

router = APIRouter()

# Shared query-param value sets for the user-listing + export endpoints, kept in
# one place so the two routes can't drift apart.
SortByParam = Literal["username", "email", "role", "created_at", "last_login_at"]
SortDirParam = Literal["asc", "desc"]
RoleParam = Literal["admin", "user", "guest"]


class TrendWindow(IntEnum):
    """Allowed signup-trend windows (number of daily buckets)."""

    WEEK = 7
    MONTH = 30
    QUARTER = 90


@router.get("/overview", response_model=UserOverviewStats)
async def get_user_overview(
    _: Annotated[bool, Depends(require_admin)],
    service: Annotated[AdminStatsService, Depends(get_admin_stats_service)],
    trend_days: Annotated[TrendWindow, Query()] = TrendWindow.MONTH,
) -> UserOverviewStats:
    """Return aggregated user-overview statistics for the admin dashboard."""
    return service.get_overview(trend_days=int(trend_days))


@router.get("/users", response_model=AdminUserPage)
async def list_admin_users(
    _: Annotated[bool, Depends(require_admin)],
    service: Annotated[AdminStatsService, Depends(get_admin_stats_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[SortByParam, Query()] = "created_at",
    sort_dir: Annotated[SortDirParam, Query()] = "desc",
    search: Annotated[Optional[str], Query()] = None,
    role: Annotated[Optional[RoleParam], Query()] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
    is_email_verified: Annotated[Optional[bool], Query()] = None,
) -> AdminUserPage:
    """Return a paginated, sortable, filterable page of users."""
    return service.list_users(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        role=role,
        is_active=is_active,
        is_email_verified=is_email_verified,
    )


@router.get("/users/export")
async def export_admin_users(
    _: Annotated[bool, Depends(require_admin)],
    service: Annotated[AdminStatsService, Depends(get_admin_stats_service)],
    sort_by: Annotated[SortByParam, Query()] = "created_at",
    sort_dir: Annotated[SortDirParam, Query()] = "desc",
    search: Annotated[Optional[str], Query()] = None,
    role: Annotated[Optional[RoleParam], Query()] = None,
    is_active: Annotated[Optional[bool], Query()] = None,
    is_email_verified: Annotated[Optional[bool], Query()] = None,
) -> Response:
    """Export the filtered user base as a downloadable CSV file (admin-only).

    Honors the same filters/sort as ``GET /users`` but returns every matching
    row (no pagination). Only account-overview fields are included.
    """
    csv_text = service.export_users_csv(
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        role=role,
        is_active=is_active,
        is_email_verified=is_email_verified,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="syfthub-users-{stamp}.csv"'
        },
    )
