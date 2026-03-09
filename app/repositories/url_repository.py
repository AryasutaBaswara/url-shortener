from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.models.entities import URL

class URLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_url(self, url: URL):
        self.session.add(url)
        await self.session.commit()
        await self.session.refresh(url)
        return url

    async def get_by_short_code(self, short_code: str):
        result = await self.session.execute(select(URL).where(URL.short_code == short_code))
        return result.scalar_one_or_none()

    async def increment_click_count(self, short_code: str):
        result = await self.session.execute(select(URL).where(URL.short_code == short_code))
        url = result.scalar_one_or_none()
        if url:
            url.click_count += 1
            await self.session.commit()
            await self.session.refresh(url)
        return url

    async def delete_url(self, short_code: str):
        await self.session.execute(delete(URL).where(URL.short_code == short_code))
        await self.session.commit()
