"""HTTP middleware for client identification and rate-limit enforcement."""
import hashlib
import ipaddress
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


def identify_client(request: Request, *, trust_proxy_headers: bool = False) -> str:
    """Return a stable opaque client identifier; never use raw API keys as storage keys."""
    api_key = request.headers.get("x-api-key", "").strip()
    if api_key:
        # Hashing prevents accidental exposure of credentials in Redis keys and logs.
        return "key_" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    host = request.client.host if request.client else "unknown"
    if trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        try:
            host = str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        host = "unknown"
    return "ip_" + hashlib.sha256(host.encode("utf-8")).hexdigest()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limiter, fail_mode: str = "closed", trust_proxy_headers: bool = False,
                 exempt_paths: set[str] | None = None) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.fail_mode = fail_mode
        self.trust_proxy_headers = trust_proxy_headers
        self.exempt_paths = exempt_paths or {"/health", "/openapi.json", "/docs", "/redoc"}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or request.url.path in self.exempt_paths or request.url.path.startswith("/admin"):
            return await call_next(request)
        client_id = identify_client(request, trust_proxy_headers=self.trust_proxy_headers)
        try:
            decision = await self.limiter.check(client_id)
        except Exception:
            logger.exception("Rate-limit storage check failed")
            if self.fail_mode == "closed":
                return JSONResponse({"detail": "Rate limiter temporarily unavailable"}, status_code=503,
                                    headers={"Cache-Control": "no-store"})
            return await call_next(request)
        headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
            "X-RateLimit-Reset": str(decision.reset_at),
            "Cache-Control": "no-store",
        }
        if not decision.allowed:
            headers["Retry-After"] = str(max(1, decision.retry_after))
            return JSONResponse({"detail": "Rate limit exceeded", "retry_after": max(1, decision.retry_after)},
                                status_code=429, headers=headers)
        response = await call_next(request)
        response.headers.update(headers)
        return response
