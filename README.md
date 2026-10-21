# API Rate Limiter

A compact FastAPI service demonstrating configurable rate limiting with fixed-window, sliding-window-log, and token-bucket strategies. Redis Lua scripts make each decision atomic across application workers. A small browser dashboard makes it easy to demonstrate successful requests and `429 Too Many Requests` responses.

## Features

- `X-API-Key` client identification with SHA-256-derived internal IDs; otherwise the client IP is used.
- Configurable default strategy, quota, window, token bucket capacity/refill, and storage failure policy.
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After` response headers.
- Bearer-token-protected admin endpoints for inspecting and setting in-memory per-client rules.
- Redis for shared state; an in-memory adapter is used by unit tests and can be used for single-process demos.
- Dashboard, pytest suite, Locust load test, Docker Compose, and GitHub Actions CI.

## Quick start with Docker

1. Install Docker Engine and the Docker Compose plugin.
2. Copy `.env.example` to `.env`.
3. Replace `ADMIN_TOKEN` with a long random secret. For example, generate one locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. Start the app: `docker compose up --build`.
5. Open <http://localhost:8000>. Swagger docs are at <http://localhost:8000/docs>.

Do not commit `.env` or use the example token in a public deployment. Compose refuses to start without `ADMIN_TOKEN`.

## Run locally without Docker

Requires Python 3.12+ and a reachable Redis instance.

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
export REDIS_URL=redis://localhost:6379/0
export ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FAIL_MODE=closed
cd backend
uvicorn app.main:app --reload
```

## API examples

```bash
# Health check (does not consume quota)
curl -i http://localhost:8000/health

# Send protected requests; each API key has its own quota
curl -i -H 'X-API-Key: demo-client' http://localhost:8000/api/data

# Inspect public demo configuration
curl -s http://localhost:8000/api/stats

# Admin endpoints require the configured bearer token
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/admin/rules
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"strategy":"sliding_window_log","limit":5,"window_seconds":60}' \
  http://localhost:8000/admin/rules/client-123
```

`client_id` in the admin API refers to the opaque ID used by the limiter (for API keys, `key_` plus the SHA-256 digest; for IPs, `ip_` plus the digest). The admin rules map is intentionally in-memory in this MVP and resets on restart. For production, persist and validate rules in Redis or a database and define a safe admin workflow.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL; keep credentials in secret storage |
| `LIMITER_STRATEGY` | `fixed_window` | `fixed_window`, `sliding_window_log`, or `token_bucket` |
| `RATE_LIMIT` | `10` | Requests per fixed/sliding window |
| `WINDOW_SECONDS` | `60` | Window length, 1–86400 seconds |
| `TOKEN_BUCKET_CAPACITY` | `10` | Maximum burst size for token bucket |
| `TOKEN_BUCKET_REFILL_RATE` | `1.0` | Tokens refilled per second |
| `FAIL_MODE` | `closed` | `closed` returns 503 on storage failure; `open` lets requests pass |
| `ADMIN_TOKEN` | empty | Required bearer token for admin endpoints; admin is disabled if absent |
| `TRUSTED_PROXY_HEADERS` | `false` | Only enable behind a proxy that strips client-supplied forwarding headers and sets its own |
| `ALLOWED_ORIGINS` | localhost origin | Comma-separated CORS origins |
| `PORT` | `8000` | Host port in Compose |

## Tests and quality checks

```bash
cd backend
python -m pytest -q
python -m ruff check app tests
```

The tests cover health, allowed requests, quota exhaustion, client isolation, admin authentication, rule validation, sliding-window behavior, and token-bucket burst limits. Redis Lua scripts should additionally be integration-tested against a real Redis service in CI before production use.

## Load test

With the app running, install requirements and run:

```bash
locust -f load/locustfile.py --host http://localhost:8000
```

Open Locust's local UI and increase users/spawn rate. Expect successful responses followed by 429s for each stable client identity. Each virtual user generates a unique API key on startup, so quota exhaustion can be observed independently per user.

## Request flow

1. Middleware skips health/docs/admin and CORS preflight requests.
2. A client identity is derived from the API key, or the request IP when no key is supplied. Raw API keys are not used as Redis key names.
3. The configured rule selects an algorithm.
4. Redis runs one atomic Lua script to update state and return the decision.
5. Allowed requests proceed; rejected requests receive HTTP 429 and a `Retry-After` header.
6. If Redis fails, `FAIL_MODE=closed` returns 503 (safer for protected services); `open` favors availability but bypasses protection during the outage.

## Security and trade-offs

- Use HTTPS in production. Do not put admin tokens in browser code or client-side applications.
- Admin routes are bearer-token protected and compare tokens using constant-time comparison. Add token rotation, audit logs, and stronger admin identity before production.
- Do not trust `X-Forwarded-For` unless your trusted reverse proxy overwrites it. IP-based limiting is imperfect behind NAT and on IPv6 privacy addresses; API keys are preferred.
- CORS is not authentication. Set `ALLOWED_ORIGINS` to known origins.
- The dashboard is a demonstration UI, not an API-key management console. Do not use real secrets as its demo key.
- In-memory rule overrides are per-process and not persisted; use a shared policy store for multi-instance deployment.
- Fixed windows can allow a boundary burst. Sliding-window logs are more precise but use more Redis memory. Token buckets support bursts and smooth refill.
- Choose `FAIL_MODE=closed` when bypassing quotas is unacceptable. Redis availability becomes part of request availability.
- Configure Redis authentication, TLS, memory limits, monitoring, and network isolation for production. Compose is a demo deployment, not a hardened production platform.

## Demo script (2–3 minutes)

1. Open the dashboard and point out the active strategy and configured quota.
2. Send requests using key `demo-a` until a 429 appears; show `Retry-After` and remaining quota.
3. Change the key to `demo-b` and show that its quota is independent.
4. Open `/docs` and show the public and admin endpoints. Demonstrate an unauthenticated admin request failing with 401, then use a bearer token from the terminal.
5. Explain the algorithm trade-offs, Redis atomicity, and fail-open versus fail-closed behavior.

## Suggested next steps

Persist admin rules, add Redis integration tests and CI service containers, instrument latency/rejections, add API-key provisioning/rotation, add per-route rules and weighted costs, configure TLS and trusted proxy allowlists, and publish deployment-specific runbooks.
