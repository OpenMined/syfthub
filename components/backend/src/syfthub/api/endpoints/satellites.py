"""Satellite registration endpoints.

A satellite is addressed by its ``public_id`` UUID. The integer primary key
never appears here.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.database.dependencies import get_db_session
from syfthub.schemas.satellite import (
    SatelliteCreate,
    SatelliteResponse,
    SatelliteUpdate,
)
from syfthub.schemas.user import User
from syfthub.services.satellite_service import SatelliteService

router = APIRouter()


def get_satellite_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> SatelliteService:
    """Dependency to get satellite service."""
    return SatelliteService(session)


@router.get("", response_model=list[SatelliteResponse])
def list_satellites(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SatelliteService, Depends(get_satellite_service)],
) -> list[SatelliteResponse]:
    """List the satellites owned by the current account, oldest first."""
    return service.list_satellites(current_user.id)


@router.post("", response_model=SatelliteResponse, status_code=status.HTTP_201_CREATED)
def create_satellite(
    satellite_data: SatelliteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SatelliteService, Depends(get_satellite_service)],
) -> SatelliteResponse:
    """Register a satellite.

    Spaces normally register themselves at setup. Stations must be registered
    explicitly: they serve no endpoints, so they never report health and would
    otherwise never acquire a row.
    """
    return service.create_satellite(current_user.id, satellite_data)


@router.get("/{satellite_id}", response_model=SatelliteResponse)
def get_satellite(
    satellite_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SatelliteService, Depends(get_satellite_service)],
) -> SatelliteResponse:
    """Get one satellite owned by the current account."""
    return service.get_satellite(current_user.id, satellite_id)


@router.put("/{satellite_id}", response_model=SatelliteResponse)
def update_satellite(
    satellite_id: uuid.UUID,
    satellite_data: SatelliteUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SatelliteService, Depends(get_satellite_service)],
) -> SatelliteResponse:
    """Update a satellite's slug and/or origin. Omitted fields are unchanged."""
    return service.update_satellite(current_user.id, satellite_id, satellite_data)


@router.delete("/{satellite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_satellite(
    satellite_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[SatelliteService, Depends(get_satellite_service)],
) -> None:
    """Delete a satellite.

    Its endpoints are **orphaned**, not deleted: they keep their addresses and
    are deactivated, so a redeployed space can re-adopt them.
    """
    service.delete_satellite(current_user.id, satellite_id)
