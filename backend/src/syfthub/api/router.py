"""Main API router."""

from fastapi import APIRouter

from syfthub.api.endpoints import (
    accounting,
    endpoints,
    errors,
    nats,
    organizations,
    peer,
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

# NATS peer token endpoints
api_router.include_router(peer.router, tags=["nats-peer"])

# NATS credentials endpoint
api_router.include_router(nats.router, tags=["nats"])

# Error reporting endpoint for frontend
api_router.include_router(errors.router, tags=["observability"])
