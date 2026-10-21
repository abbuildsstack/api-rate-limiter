"""Storage adapters for atomic rate-limit decisions."""
import asyncio
import hashlib
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis

from .algorithms import FIXED_WINDOW_SCRIPT, SLIDING_LOG_SCRIPT, TOKEN_BUCKET_SCRIPT


@dataclass(frozen=True)
class Decision:
    """Result of evaluating a client's request."""
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    reset_at: int
    strategy: str


class Storage(Protocol):
    async def check(self, *, key: str, strategy: str, limit: int, window_seconds: int,
                   bucket_capacity: int, refill_rate: float) -> Decision: ...
    async def close(self) -> None: ...


class RedisStorage:
    """Redis implementation; Lua scripts make each decision atomic across workers."""
    def __init__(self, client: Redis, prefix: str) -> None:
        self.client = client
        self.prefix = prefix

    async def check(self, *, key: str, strategy: str, limit: int, window_seconds: int,
                    bucket_capacity: int, refill_rate: float) -> Decision:
        now = time.time()
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        redis_key = f"{self.prefix}:{strategy}:{digest}"
        if strategy == "fixed_window":
            window_start = int(now) // window_seconds * window_seconds
            redis_key = f"{redis_key}:{window_start}"
            result = await self.client.eval(FIXED_WINDOW_SCRIPT, 1, redis_key, window_seconds, limit, window_start + window_seconds)
        elif strategy == "sliding_window_log":
            result = await self.client.eval(SLIDING_LOG_SCRIPT, 1, redis_key, int(now * 1000), window_seconds * 1000,
                                            limit, uuid.uuid4().hex)
        elif strategy == "token_bucket":
            result = await self.client.eval(TOKEN_BUCKET_SCRIPT, 1, redis_key, int(now * 1000), bucket_capacity,
                                            refill_rate / 1000, 1)
        else:
            raise ValueError("Unsupported rate-limit strategy")
        allowed, remaining, retry_after, reset_at = (int(value) for value in result)
        effective_limit = bucket_capacity if strategy == "token_bucket" else limit
        return Decision(bool(allowed), effective_limit, max(0, remaining), max(0, retry_after), reset_at, strategy)

    async def close(self) -> None:
        await self.client.aclose()


class InMemoryStorage:
    """Single-process development/test adapter. Not suitable for multi-worker production."""
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._buckets: dict[str, tuple[float, float]] = {}

    async def check(self, *, key: str, strategy: str, limit: int, window_seconds: int,
                    bucket_capacity: int, refill_rate: float) -> Decision:
        now = time.time()
        async with self._lock:
            if strategy == "fixed_window":
                start = int(now) // window_seconds * window_seconds
                slot = f"{key}:{start}"
                hits = self._windows[slot]
                hits.append(now)
                count = len(hits)
                remaining = max(0, limit - count)
                reset = start + window_seconds
                return Decision(count <= limit, limit, remaining, max(0, int(reset - now)), reset, strategy)
            if strategy == "sliding_window_log":
                hits = [stamp for stamp in self._windows[key] if stamp > now - window_seconds]
                allowed = len(hits) < limit
                if allowed:
                    hits.append(now)
                self._windows[key] = hits
                retry = max(1, int(hits[0] + window_seconds - now)) if not allowed and hits else 0
                reset = int(now) + retry if retry else int(now) + window_seconds
                return Decision(allowed, limit, max(0, limit-len(hits)), retry, reset, strategy)
            if strategy == "token_bucket":
                tokens, updated = self._buckets.get(key, (float(bucket_capacity), now))
                tokens = min(float(bucket_capacity), tokens + max(0.0, now-updated)*refill_rate)
                allowed = tokens >= 1.0
                if allowed:
                    tokens -= 1.0
                retry = max(1, int((1.0-tokens)/refill_rate + 0.999)) if not allowed else 0
                self._buckets[key] = (tokens, now)
                reset = int(now) + retry
                return Decision(allowed, bucket_capacity, int(tokens), retry, reset, strategy)
            raise ValueError("Unsupported rate-limit strategy")

    async def close(self) -> None:
        return None