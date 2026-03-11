from fastapi import FastAPI
from app.api.v1.routes import router
from contextlib import asynccontextmanager
from app.core.database import init_db

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield

app = FastAPI(
    lifespan=lifespan,
    title="URL-Shortener API",
    version="1.0.0",)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

app.include_router(router)

