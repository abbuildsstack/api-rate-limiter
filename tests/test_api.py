def test_health_is_available(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rate_limit_allows_quota_then_returns_429(client):
    first = client.get("/api/data", headers={"X-API-Key": "client-a"})
    second = client.get("/api/data", headers={"X-API-Key": "client-a"})
    third = client.get("/api/data", headers={"X-API-Key": "client-a"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["retry-after"]
    assert third.headers["x-ratelimit-remaining"] == "0"


def test_different_keys_have_separate_quotas(client):
    for _ in range(2):
        assert (
            client.get("/api/data", headers={"X-API-Key": "client-b"}).status_code
            == 200
        )
    assert client.get("/api/data", headers={"X-API-Key": "client-c"}).status_code == 200


def test_admin_requires_bearer_token(client):
    assert client.get("/admin/rules").status_code == 401
    response = client.get(
        "/admin/rules", headers={"Authorization": "Bearer test-admin-token"}
    )
    assert response.status_code == 200


def test_admin_rule_validation_and_update(client):
    headers = {"Authorization": "Bearer test-admin-token"}
    invalid = client.put(
        "/admin/rules/client-x",
        headers=headers,
        json={"strategy": "fixed_window", "limit": 0, "window_seconds": 60},
    )
    assert invalid.status_code == 422
    valid = client.put(
        "/admin/rules/client-x",
        headers=headers,
        json={
            "strategy": "token_bucket",
            "limit": 5,
            "window_seconds": 60,
            "bucket_capacity": 3,
            "refill_rate": 1.5,
        },
    )
    assert valid.status_code == 200
    assert valid.json()["rule"]["strategy"] == "token_bucket"
