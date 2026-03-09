from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl

class ShortenRequest(BaseModel):
    original_url: HttpUrl
    custom_code: Optional[str] = None

class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: HttpUrl
    created_at: datetime

class URLStats(BaseModel):
    short_code: str
    original_url: HttpUrl
    click_count: int
    created_at: datetime
