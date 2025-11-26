"""Main API router."""

from fastapi import APIRouter

from syfthub.api.endpoints import datasites, organizations, users
from syfthub.auth import router as auth_router

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth_router.router, tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(datasites.router, prefix="/datasites", tags=["datasites"])
api_router.include_router(
    organizations.router, prefix="/organizations", tags=["organizations"]
)
