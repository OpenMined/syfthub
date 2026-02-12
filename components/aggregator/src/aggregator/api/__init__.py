"""API package - FastAPI routes and dependencies."""

from aggregator.api.router import api_router, health_router

__all__ = ["api_router", "health_router"]
