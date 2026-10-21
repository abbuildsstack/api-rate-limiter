"""Rate-limit policy resolution and decision service."""
from dataclasses import dataclass
from typing import Any

from .storage import Decision, Storage


@dataclass(frozen=True)
class Rule:
    """A validated per-client rate-limit rule."""
    strategy: str
    limit: int
    window_seconds: int
    bucket_capacity: int
    refill_rate: float


class RateLimiter:
    def __init__(self, storage: Storage, default_rule: Rule) -> None:
        self.storage = storage
        self.default_rule = default_rule
        self._rules: dict[str, Rule] = {}

    def get_rule(self, client_id: str) -> Rule:
        return self._rules.get(client_id, self.default_rule)

    def set_rule(self, client_id: str, rule: Rule) -> None:
        self._rules[client_id] = rule

    def list_rules(self) -> dict[str, dict[str, Any]]:
        return {client: {"strategy": rule.strategy, "limit": rule.limit,
                         "window_seconds": rule.window_seconds, "bucket_capacity": rule.bucket_capacity,
                         "refill_rate": rule.refill_rate} for client, rule in self._rules.items()}

    async def check(self, client_id: str) -> Decision:
        rule = self.get_rule(client_id)
        return await self.storage.check(key=client_id, strategy=rule.strategy, limit=rule.limit,
                                        window_seconds=rule.window_seconds, bucket_capacity=rule.bucket_capacity,
                                        refill_rate=rule.refill_rate)
