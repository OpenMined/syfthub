"""Main API router."""

from fastapi import APIRouter

from syfthub.api.endpoints import (
    accounting,
    endpoints,
    errors,
    mq,
    organizations,
    token,
    users,
)
from syfthub.auth import router as auth_router

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth_router.router, tags=["authentication"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(endpoints.router, prefix="/endpoints", tags=["endpoints"])
api_router.include_router(
    organizations.router, prefix="/organizations", tags=["organizations"]
)

# Accounting proxy endpoints (proxies to external accounting service)
api_router.include_router(accounting.router, prefix="/accounting", tags=["accounting"])

# Identity Provider (IdP) endpoints
api_router.include_router(token.router, tags=["identity-provider"])

# Error reporting endpoint for frontend
api_router.include_router(errors.router, tags=["observability"])

# Message queue endpoints (Redis-backed user message queues)
api_router.include_router(mq.router, prefix="/mq", tags=["message-queue"])
