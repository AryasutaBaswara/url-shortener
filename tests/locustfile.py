import random
from uuid import uuid4

import requests
from locust import HttpUser, between, task


KEYCLOAK_TOKEN_URL = "http://localhost:8082/realms/url-shortener-realm/protocol/openid-connect/token"


class URLShortenerUser(HttpUser):
    host = "http://localhost:8001"
    wait_time = between(1, 3)

    def on_start(self):
        self.short_codes: list[str] = []
        self.auth_headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

    def _get_access_token(self) -> str:
        response = requests.post(
            KEYCLOAK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "password",
                "client_id": "url-shortener-client",
                "client_secret": "dev-secret",
                "username": "testuser",
                "password": "testpassword",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    @task(3)
    def shorten_url(self):
        original_url = f"https://example.com/load-test/{uuid4()}"
        response = self.client.post(
            "/api/v1/shorten",
            json={"original_url": original_url},
            headers=self.auth_headers,
            name="POST /api/v1/shorten",
        )

        if response.status_code == 200:
            short_code = response.json().get("short_code")
            if short_code:
                self.short_codes.append(short_code)

    @task(5)
    def redirect_url(self):
        if not self.short_codes:
            self.shorten_url()
            if not self.short_codes:
                return

        short_code = random.choice(self.short_codes)
        self.client.get(
            f"/{short_code}",
            headers=self.auth_headers,
            name="GET /{short_code}",
            allow_redirects=False,
        )

    @task(2)
    def get_stats(self):
        if not self.short_codes:
            self.shorten_url()
            if not self.short_codes:
                return

        short_code = random.choice(self.short_codes)
        self.client.get(
            f"/api/v1/stats/{short_code}",
            headers=self.auth_headers,
            name="GET /api/v1/stats/{short_code}",
        )