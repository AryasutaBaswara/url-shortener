from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.entities import URL
from app.services.url_service import URLService


@pytest.fixture
def mock_url_entity():
    url = MagicMock(spec=URL)
    url.id = 1
    url.original_url = "https://example.com"
    url.short_code = "abc123"
    url.click_count = 0
    url.created_at = datetime(2025, 1, 1)
    url.expires_at = None
    return url


@pytest.fixture
def mock_db_session():
    session = AsyncMock(name="mock_db_session")
    session.execute = AsyncMock(return_value=None)
    session.commit = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    session.close = AsyncMock(return_value=None)
    return session


@pytest.fixture
def client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return {"sub": "test-user", "email": "test@example.com"}

    async def mock_init_db():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("app.main.init_db", mock_init_db):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


class TestHealthCheck:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestShortenUrl:
    def test_shorten_url(self, client, mock_url_entity):
        with patch.object(URLService, "shorten_url", AsyncMock(return_value=mock_url_entity)) as mock_shorten:
            response = client.post(
                "/api/v1/shorten",
                json={"original_url": "https://example.com"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data["short_code"] == "abc123"
        assert data["short_url"] == "/abc123"
        assert data["original_url"] == "https://example.com/"
        mock_shorten.assert_awaited_once_with("https://example.com/", None)

    def test_shorten_url_invalid(self, client):
        response = client.post(
            "/api/v1/shorten",
            json={"url": "not-a-valid-url"}
        )
        assert response.status_code == 422


class TestRedirectUrl:
    def test_redirect_url(self, client):
        with patch.object(URLService, "redirect_url", AsyncMock(return_value="https://example.com")) as mock_redirect:
            response = client.get("/abc123", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "https://example.com"
        mock_redirect.assert_awaited_once_with("abc123")

    def test_redirect_url_not_found(self, client):
        with patch.object(URLService, "redirect_url", AsyncMock(return_value=None)) as mock_redirect:
            response = client.get("/nonexistent", follow_redirects=False)

        assert response.status_code == 404
        assert response.json() == {"detail": "Short URL not found"}
        mock_redirect.assert_awaited_once_with("nonexistent")


class TestUrlStats:
    def test_url_stats(self, client, mock_url_entity):
        mock_url_entity.click_count = 5
        with patch.object(URLService, "get_url_stats", AsyncMock(return_value=mock_url_entity)) as mock_stats:
            response = client.get("/api/v1/stats/abc123")

        assert response.status_code == 200
        assert response.json()["short_code"] == "abc123"
        assert response.json()["click_count"] == 5
        mock_stats.assert_awaited_once_with("abc123")

    def test_url_stats_not_found(self, client):
        with patch.object(URLService, "get_url_stats", AsyncMock(return_value=None)) as mock_stats:
            response = client.get("/api/v1/stats/nonexistent")

        assert response.status_code == 404
        assert response.json() == {"detail": "Short URL not found"}
        mock_stats.assert_awaited_once_with("nonexistent")