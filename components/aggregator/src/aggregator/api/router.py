"""API router configuration."""

from fastapi import APIRouter

from aggregator.api.endpoints import agent, chat, health, payment, query
from aggregator.services import attachment_relay

# Main API router with version prefix
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat.router)
api_router.include_router(payment.router)
api_router.include_router(query.router)
api_router.include_router(agent.router)
api_router.include_router(attachment_relay.router)

# Health router at root level
health_router = health.router
