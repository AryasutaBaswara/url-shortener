import random
import string
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import URL
from app.repositories.url_repository import URLRepository
from datetime import datetime

# Placeholder for Redis client (implement actual connection in integration phase)
class RedisCache:
    def __init__(self):
        self._cache = {}
    async def get(self, key):
        return self._cache.get(key)
    async def set(self, key, value, ex=None):
        self._cache[key] = value
    async def delete(self, key):
        if key in self._cache:
            del self._cache[key]

redis_cache = RedisCache()

class URLService:
    def __init__(self, db: AsyncSession):
        self.repo = URLRepository(db)

    async def shorten_url(self, original_url: str, custom_code: Optional[str] = None, expires_at: Optional[datetime] = None) -> URL:
        short_code = custom_code or self._generate_short_code()
        # Check for collision
        existing = await self.repo.get_by_short_code(short_code)
        if existing:
            raise ValueError("Short code already exists")
        url = URL(
            original_url=original_url,
            short_code=short_code,
            expires_at=expires_at
        )
        url = await self.repo.create_url(url)
        await redis_cache.set(short_code, original_url)
        return url

    async def redirect_url(self, short_code: str) -> Optional[str]:
        # Try Redis first
        cached = await redis_cache.get(short_code)
        if cached:
            await self.repo.increment_click_count(short_code)
            return cached
        # Fallback to DB
        url = await self.repo.get_by_short_code(short_code)
        if url:
            await redis_cache.set(short_code, url.original_url)
            await self.repo.increment_click_count(short_code)
            return url.original_url
        return None

    async def get_url_stats(self, short_code: str) -> Optional[URL]:
        return await self.repo.get_by_short_code(short_code)

    def _generate_short_code(self, length: int = 6) -> str:
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
