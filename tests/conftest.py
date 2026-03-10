import asyncio
import importlib
import os

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.entities import Base, URL


TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@supabase-db:5432/urlshortener"
TEST_REDIS_URL = "redis://redis:6379/0"
TEST_KEYCLOAK_URL = "http://keycloak:8081"
TEST_KEYCLOAK_REALM = "url-shortener-realm"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


@pytest.fixture(scope="module")
def integration_modules(request):
    if request.module.__name__ != "tests.test_integration":
        pytest.skip("Integration fixtures are only available to test_integration.py")

    previous_database_url = os.environ.get("DATABASE_URL")
    previous_redis_url = os.environ.get("REDIS_URL")
    previous_keycloak_url = os.environ.get("KEYCLOAK_URL")
    previous_keycloak_realm = os.environ.get("KEYCLOAK_REALM")

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["REDIS_URL"] = TEST_REDIS_URL
    os.environ["KEYCLOAK_URL"] = TEST_KEYCLOAK_URL
    os.environ["KEYCLOAK_REALM"] = TEST_KEYCLOAK_REALM

    import app.core.config as config_module
    import app.api.v1.routes as routes_module
    import app.main as main_module
    import app.services.url_service as url_service_module

    config_module = importlib.reload(config_module)
    routes_module = importlib.reload(routes_module)
    url_service_module = importlib.reload(url_service_module)
    main_module = importlib.reload(main_module)

    try:
        yield {
            "routes_module": routes_module,
            "main_module": main_module,
            "url_service_module": url_service_module,
        }
    finally:
        main_module.app.dependency_overrides.clear()

        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

        if previous_redis_url is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = previous_redis_url

        if previous_keycloak_url is None:
            os.environ.pop("KEYCLOAK_URL", None)
        else:
            os.environ["KEYCLOAK_URL"] = previous_keycloak_url

        if previous_keycloak_realm is None:
            os.environ.pop("KEYCLOAK_REALM", None)
        else:
            os.environ["KEYCLOAK_REALM"] = previous_keycloak_realm


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def test_engine(integration_modules):
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable at {TEST_DATABASE_URL}: {exc}")

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def redis_client(integration_modules):
    client = redis_asyncio.from_url(TEST_REDIS_URL, decode_responses=True)

    try:
        await client.ping()
    except Exception as exc:
        await client.aclose()
        pytest.skip(f"Redis unavailable at {TEST_REDIS_URL}: {exc}")

    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def created_short_codes():
    return set()


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def keycloak_token(integration_modules):
    token_url = f"{TEST_KEYCLOAK_URL}/realms/{TEST_KEYCLOAK_REALM}/protocol/openid-connect/token"

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(
                token_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "password",
                    "client_id": "url-shortener-client",
                    "client_secret": "dev-secret",
                    "username": "testuser",
                    "password": "testpassword",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"Keycloak token endpoint unavailable at {token_url}: {exc}")

    return response.json()["access_token"]


@pytest_asyncio.fixture(loop_scope="session")
async def client(integration_modules, test_session_factory, redis_client, keycloak_token, created_short_codes):
    routes_module = integration_modules["routes_module"]
    main_module = integration_modules["main_module"]
    url_service_module = integration_modules["url_service_module"]

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    original_cache = url_service_module.redis_cache
    url_service_module.redis_cache = redis_client
    main_module.app.dependency_overrides[routes_module.get_db] = override_get_db
    transport = httpx.ASGITransport(app=main_module.app)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {keycloak_token}"},
            follow_redirects=False,
        ) as async_client:
            yield async_client
    finally:
        main_module.app.dependency_overrides.pop(routes_module.get_db, None)
        url_service_module.redis_cache = original_cache

        if created_short_codes:
            await redis_client.delete(*created_short_codes)
            async with test_session_factory() as session:
                await session.execute(delete(URL).where(URL.short_code.in_(list(created_short_codes))))
                await session.commit()