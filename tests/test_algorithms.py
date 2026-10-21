import pytest
from app.limiter.storage import InMemoryStorage


@pytest.mark.asyncio
async def test_sliding_window_rejects_over_limit():
    store = InMemoryStorage()
    kwargs = dict(
        key="client",
        strategy="sliding_window_log",
        limit=2,
        window_seconds=60,
        bucket_capacity=2,
        refill_rate=1.0,
    )
    assert (await store.check(**kwargs)).allowed
    assert (await store.check(**kwargs)).allowed
    assert not (await store.check(**kwargs)).allowed


@pytest.mark.asyncio
async def test_token_bucket_allows_burst_up_to_capacity():
    store = InMemoryStorage()
    kwargs = dict(
        key="client",
        strategy="token_bucket",
        limit=10,
        window_seconds=60,
        bucket_capacity=2,
        refill_rate=0.001,
    )
    assert (await store.check(**kwargs)).allowed
    assert (await store.check(**kwargs)).allowed
    assert not (await store.check(**kwargs)).allowed
