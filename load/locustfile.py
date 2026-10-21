"""Load test: run `locust -f load/locustfile.py --host http://localhost:8000`."""
import uuid

from locust import HttpUser, between, task


class RateLimitUser(HttpUser):
    wait_time = between(0.0, 0.15)

    def on_start(self):
        self.api_key = "load-user-" + uuid.uuid4().hex

    @task
    def request_protected_resource(self):
        # Each virtual user has a stable key, so its own quota is observable.
        with self.client.get("/api/data", headers={"X-API-Key": self.api_key},
                             name="GET /api/data", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.success()  # Expected outcome when the quota is exhausted.
            else:
                response.failure(f"Unexpected HTTP status {response.status_code}")