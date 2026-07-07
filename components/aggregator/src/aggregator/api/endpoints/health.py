"""Health check endpoints."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "syfthub-aggregator"}


@router.get("/ready")
async def ready() -> dict[str, Any]:
    """
    Readiness check - aggregator is always ready.

    The aggregator no longer depends on SyftHub for endpoint resolution
    since URLs are now passed directly in the request.
    """
    return {
        "status": "ready",
        "checks": {},
    }
