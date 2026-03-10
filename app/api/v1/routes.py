from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schemas import ShortenRequest, ShortenResponse, URLStats
from app.services.url_service import URLService
from app.core.auth import get_current_user
from app.models.entities import URL
from app.core.database import get_db

router = APIRouter()

@router.post("/api/v1/shorten", response_model=ShortenResponse, dependencies=[Depends(get_current_user)])
async def shorten_url(request: ShortenRequest, db: AsyncSession = Depends(get_db)):
    service = URLService(db)
    try:
        url: URL = await service.shorten_url(str(request.original_url), request.custom_code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    short_url = "/" + url.short_code  # Replace with full domain in production
    return ShortenResponse(
        short_code=url.short_code,
        short_url=short_url,
        original_url=url.original_url,
        created_at=url.created_at
    )

@router.get("/api/v1/stats/{short_code}", response_model=URLStats, dependencies=[Depends(get_current_user)])
async def url_stats(short_code: str, db: AsyncSession = Depends(get_db)):
    service = URLService(db)
    url = await service.get_url_stats(short_code)
    if not url:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return URLStats(
        short_code=url.short_code,
        original_url=url.original_url,
        click_count=url.click_count,
        created_at=url.created_at
    )

@router.get("/{short_code}")
async def redirect(short_code: str, db: AsyncSession = Depends(get_db)):
    service = URLService(db)
    original_url = await service.redirect_url(short_code)
    if not original_url:
        raise HTTPException(status_code=404, detail="Short URL not found")
    return RedirectResponse(original_url)