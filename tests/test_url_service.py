import pytest
import string
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from app.services.url_service import URLService, RedisCache
from app.models.entities import URL


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = AsyncMock(spec=RedisCache)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def url_service(mock_db):
    service = URLService(mock_db)
    service.repo = AsyncMock()
    return service


class TestGenerateShortCode:
    def test_generate_short_code_length(self, url_service):
        code = url_service._generate_short_code()
        assert len(code) == 6

    def test_generate_short_code_alphanumeric(self, url_service):
        code = url_service._generate_short_code()
        valid_chars = set(string.ascii_letters + string.digits)
        assert all(c in valid_chars for c in code)

    def test_generate_short_code_custom_length(self, url_service):
        code = url_service._generate_short_code(length=10)
        assert len(code) == 10

    def test_generate_short_code_uniqueness(self, url_service):
        codes = {url_service._generate_short_code() for _ in range(100)}
        assert len(codes) > 1


class TestShortenUrl:
    @pytest.mark.asyncio
    async def test_shorten_url_success(self, url_service, mock_redis):
        url_service.repo.get_by_short_code = AsyncMock(return_value=None)
        url_service.repo.create_url = AsyncMock(side_effect=lambda u: u)

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.shorten_url("https://example.com")

        assert result.original_url == "https://example.com"
        assert len(result.short_code) == 6
        url_service.repo.create_url.assert_awaited_once()
        mock_redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shorten_url_custom_code(self, url_service, mock_redis):
        url_service.repo.get_by_short_code = AsyncMock(return_value=None)
        url_service.repo.create_url = AsyncMock(side_effect=lambda u: u)

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.shorten_url("https://example.com", custom_code="mycode")

        assert result.short_code == "mycode"
        url_service.repo.create_url.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shorten_url_collision(self, url_service, mock_redis):
        existing_url = MagicMock(spec=URL)
        url_service.repo.get_by_short_code = AsyncMock(return_value=existing_url)

        with patch("app.services.url_service.redis_cache", mock_redis):
            with pytest.raises(ValueError, match="Short code already exists"):
                await url_service.shorten_url("https://example.com", custom_code="taken1")

        url_service.repo.create_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shorten_url_with_expires_at(self, url_service, mock_redis):
        url_service.repo.get_by_short_code = AsyncMock(return_value=None)
        url_service.repo.create_url = AsyncMock(side_effect=lambda u: u)
        expires = datetime(2025, 12, 31)

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.shorten_url("https://example.com", expires_at=expires)

        assert result.expires_at == expires


class TestRedirectUrl:
    @pytest.mark.asyncio
    async def test_redirect_url_from_cache(self, url_service, mock_redis):
        mock_redis.get = AsyncMock(return_value="https://example.com")
        url_service.repo.increment_click_count = AsyncMock()

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.redirect_url("abc123")

        assert result == "https://example.com"
        mock_redis.get.assert_awaited_once_with("abc123")
        url_service.repo.increment_click_count.assert_awaited_once_with("abc123")
        url_service.repo.get_by_short_code.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_redirect_url_from_db(self, url_service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        db_url = MagicMock(spec=URL)
        db_url.original_url = "https://example.com"
        url_service.repo.get_by_short_code = AsyncMock(return_value=db_url)
        url_service.repo.increment_click_count = AsyncMock()

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.redirect_url("abc123")

        assert result == "https://example.com"
        url_service.repo.get_by_short_code.assert_awaited_once_with("abc123")
        mock_redis.set.assert_awaited_once_with("abc123", "https://example.com")
        url_service.repo.increment_click_count.assert_awaited_once_with("abc123")

    @pytest.mark.asyncio
    async def test_redirect_url_not_found(self, url_service, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)
        url_service.repo.get_by_short_code = AsyncMock(return_value=None)

        with patch("app.services.url_service.redis_cache", mock_redis):
            result = await url_service.redirect_url("nonexistent")

        assert result is None


class TestGetUrlStats:
    @pytest.mark.asyncio
    async def test_get_url_stats_found(self, url_service):
        db_url = MagicMock(spec=URL)
        db_url.short_code = "abc123"
        db_url.click_count = 42
        url_service.repo.get_by_short_code = AsyncMock(return_value=db_url)

        result = await url_service.get_url_stats("abc123")

        assert result == db_url
        url_service.repo.get_by_short_code.assert_awaited_once_with("abc123")

    @pytest.mark.asyncio
    async def test_get_url_stats_not_found(self, url_service):
        url_service.repo.get_by_short_code = AsyncMock(return_value=None)

        result = await url_service.get_url_stats("nonexistent")

        assert result is None