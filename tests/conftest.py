import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.limiter.storage import InMemoryStorage


@pytest.fixture
def settings():
    return Settings(
        environment="test",
        admin_token="test-admin-token",
        rate_limit=2,
        window_seconds=60,
        limiter_strategy="fixed_window",
        fail_mode="closed",
    )


@pytest.fixture
def client(settings):
    app = create_app(test_storage=InMemoryStorage(), settings_override=settings)
    with TestClient(app) as test_client:
        yield test_client
