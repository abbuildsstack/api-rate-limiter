"""Public demonstration endpoints."""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/data")
async def get_data(request: Request) -> dict[str, object]:
    """A sample protected resource used to demonstrate rate limiting."""
    return {"message": "Request allowed", "data": {"items": ["alpha", "beta", "gamma"]}}


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, object]:
    """Expose non-sensitive runtime configuration for the demo dashboard."""
    settings = request.app.state.settings
    return {"strategy": settings.limiter_strategy, "rate_limit": settings.rate_limit,
            "window_seconds": settings.window_seconds, "fail_mode": settings.fail_mode,
            "storage": "redis" if request.app.state.redis_enabled else "in-memory"}
