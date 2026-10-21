"""FastAPI application factory and lifecycle management."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from .config import get_settings
from .limiter.limiter import RateLimiter, Rule
from .limiter.storage import InMemoryStorage, RedisStorage
from .middleware import RateLimitMiddleware
from .routers import admin, api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
FRONTEND_DIR = next((candidate for candidate in (Path(__file__).resolve().parents[2] / "frontend", Path(__file__).resolve().parents[1] / "frontend") if candidate.exists()), Path(__file__).resolve().parents[2] / "frontend")


def create_app(*, test_storage=None, settings_override=None) -> FastAPI:
    settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis_client = None
        if test_storage is not None:
            storage = test_storage
            app.state.redis_enabled = False
        else:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2,
                                          socket_timeout=2, health_check_interval=30)
            try:
                await redis_client.ping()
                storage = RedisStorage(redis_client, settings.key_prefix)
                app.state.redis_enabled = True
            except Exception:
                logger.exception("Redis is unavailable during startup")
                await redis_client.aclose()
                if settings.fail_mode == "closed":
                    raise RuntimeError("Redis is required when FAIL_MODE=closed")
                storage = InMemoryStorage()
                app.state.redis_enabled = False
        default_rule = Rule(strategy=settings.limiter_strategy, limit=settings.rate_limit,
                            window_seconds=settings.window_seconds, bucket_capacity=settings.token_bucket_capacity,
                            refill_rate=settings.token_bucket_refill_rate)
        app.state.limiter = RateLimiter(storage, default_rule)
        yield
        await storage.close()

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "PUT", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-API-Key"])
    # Middleware resolves the limiter from app.state at request time, after lifespan startup.
    class AppRateLimitMiddleware(RateLimitMiddleware):
        def __init__(self, inner_app):
            super().__init__(inner_app, limiter=_LazyLimiter(app), fail_mode=settings.fail_mode,
                             trust_proxy_headers=settings.trusted_proxy_headers)
    app.add_middleware(AppRateLimitMiddleware)
    app.include_router(api.router)
    app.include_router(admin.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
        @app.get("/", include_in_schema=False)
        async def dashboard() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")
    return app


class _LazyLimiter:
    """Middleware-safe proxy because FastAPI lifespan initializes storage after app creation."""
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    async def check(self, client_id: str):
        limiter = getattr(self.app.state, "limiter", None)
        if limiter is None:
            raise RuntimeError("Rate limiter has not initialized")
        return await limiter.check(client_id)


app = create_app()
