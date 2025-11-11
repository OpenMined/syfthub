"""Main API router."""

from fastapi import APIRouter

from syfthub.api.endpoints import items, users

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(items.router, prefix="/items", tags=["items"])
