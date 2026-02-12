"""API router configuration."""

from fastapi import APIRouter

from aggregator.api.endpoints import chat, health

# Main API router with version prefix
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat.router)

# Health router at root level
health_router = health.router
