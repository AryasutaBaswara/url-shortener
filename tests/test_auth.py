from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt

import app.core.auth as auth_module
from app.core.database import get_db
from app.main import app
from app.models.entities import URL
from app.services.url_service import URLService


KEYCLOAK_BASE_URL = auth_module.settings.KEYCLOAK_URL.rstrip("/")
TOKEN_URL = f"{KEYCLOAK_BASE_URL}/realms/{auth_module.settings.KEYCLOAK_REALM}/protocol/openid-connect/token"


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    auth_module._JWKS_CACHE["keys"] = None
    auth_module._JWKS_CACHE["expires_at"] = 0.0
    yield
    auth_module._JWKS_CACHE["keys"] = None
    auth_module._JWKS_CACHE["expires_at"] = 0.0


@pytest.fixture
def mock_db_session():
    session = AsyncMock(name="auth_mock_db_session")
    session.execute = AsyncMock(return_value=None)
    session.commit = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    return session


@pytest.fixture
def client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    async def mock_init_db():
        return None

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.init_db", mock_init_db):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_url_entity():
    url = MagicMock(spec=URL)
    url.original_url = "https://example.com"
    url.short_code = "abc123"
    url.created_at = datetime(2025, 1, 1)
    return url


def _build_expired_token() -> tuple[str, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    now = datetime.now(UTC)
    payload = {
        "sub": "expired-user",
        "email": "expired@example.com",
        "iss": auth_module._issuer(),
        "iat": int((now - timedelta(minutes=10)).timestamp()),
        "exp": int((now - timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "expired-kid"})
    return token, public_pem


class TestKeycloakAuth:
    def test_missing_token(self, client):
        response = client.post(
            "/api/v1/shorten",
            json={"original_url": "https://example.com"},
        )

        assert response.status_code == 401

    def test_invalid_token(self, client):
        response = client.post(
            "/api/v1/shorten",
            headers={"Authorization": "Bearer invalid.token.value"},
            json={"original_url": "https://example.com"},
        )

        assert response.status_code == 401

    def test_expired_token(self, client):
        token, public_pem = _build_expired_token()

        with patch.object(auth_module, "_fetch_jwks", AsyncMock(return_value=[{"kid": "expired-kid"}])), patch.object(
            auth_module,
            "_find_signing_key",
            return_value=public_pem,
        ):
            response = client.post(
                "/api/v1/shorten",
                headers={"Authorization": f"Bearer {token}"},
                json={"original_url": "https://example.com"},
            )

        assert response.status_code == 401

    def test_valid_token(self, client, mock_url_entity):
        token_response = httpx.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "password",
                "client_id": "url-shortener-client",
                "client_secret": "dev-secret",
                "username": "testuser",
                "password": "testpassword",
            },
            timeout=10.0,
        )

        if token_response.status_code != 200:
            pytest.skip(f"Unable to fetch Keycloak token: {token_response.status_code} {token_response.text}")

        access_token = token_response.json()["access_token"]

        with patch.object(auth_module.settings, "KEYCLOAK_URL", KEYCLOAK_BASE_URL), patch.object(
            URLService,
            "shorten_url",
            AsyncMock(return_value=mock_url_entity),
        ) as mock_shorten:
            auth_module._JWKS_CACHE["keys"] = None
            auth_module._JWKS_CACHE["expires_at"] = 0.0
            response = client.post(
                "/api/v1/shorten",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"original_url": "https://example.com"},
            )

        assert response.status_code in {200, 400}
        assert response.status_code not in {401, 403}
        if response.status_code == 200:
            mock_shorten.assert_awaited_once_with("https://example.com/", None)