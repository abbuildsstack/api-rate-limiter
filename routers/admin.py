"""Token-protected administrative endpoints."""
import hmac
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = request.app.state.settings.admin_token.get_secret_value()
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is disabled: ADMIN_TOKEN is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token",
                            headers={"WWW-Authenticate": "Bearer"})


class RuleInput(BaseModel):
    strategy: Literal["fixed_window", "sliding_window_log", "token_bucket"]
    limit: int = Field(default=10, ge=1, le=1_000_000)
    window_seconds: int = Field(default=60, ge=1, le=86_400)
    bucket_capacity: int = Field(default=10, ge=1, le=1_000_000)
    refill_rate: float = Field(default=1.0, gt=0, le=100_000)


@router.get("/rules", dependencies=[Depends(require_admin)])
async def list_rules(request: Request) -> dict[str, object]:
    return {"default": request.app.state.limiter.default_rule.__dict__,
            "clients": request.app.state.limiter.list_rules()}


@router.put("/rules/{client_id}", dependencies=[Depends(require_admin)])
async def update_rule(client_id: str, body: RuleInput, request: Request) -> dict[str, object]:
    if not client_id or len(client_id) > 128 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in client_id):
        raise HTTPException(status_code=422, detail="client_id must contain only letters, numbers, underscore, or hyphen")
    from ..limiter.limiter import Rule
    rule = Rule(**body.model_dump())
    request.app.state.limiter.set_rule(client_id, rule)
    return {"client_id": client_id, "rule": body.model_dump()}


@router.get("/clients", dependencies=[Depends(require_admin)])
async def list_clients(request: Request) -> dict[str, object]:
    return {"configured_clients": sorted(request.app.state.limiter.list_rules().keys()),
            "count": len(request.app.state.limiter.list_rules())}
