"""API router configuration."""

from fastapi import APIRouter

from aggregator.api.endpoints import chat, health, query

# Main API router with version prefix
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat.router)
api_router.include_router(query.router)

# Health router at root level
health_router = health.router
