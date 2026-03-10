import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=True)
_JWKS_CACHE: dict[str, Any] = {"keys": None, "expires_at": 0.0}
_JWKS_CACHE_TTL_SECONDS = 300


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _jwks_url() -> str:
    base_url = settings.KEYCLOAK_URL.rstrip("/")
    return f"{base_url}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"


def _issuer() -> str:
    base_url = settings.KEYCLOAK_URL.rstrip("/")
    return f"{base_url}/realms/{settings.KEYCLOAK_REALM}"


def _find_signing_key(keys: list[dict[str, Any]], key_id: str | None) -> dict[str, Any] | None:
    if not key_id:
        return None

    return next((key for key in keys if key.get("kid") == key_id), None)


async def _fetch_jwks(force_refresh: bool = False) -> list[dict[str, Any]]:
    now = time.monotonic()
    cached_keys = _JWKS_CACHE.get("keys")
    cache_expires_at = _JWKS_CACHE.get("expires_at", 0.0)

    if not force_refresh and cached_keys and now < cache_expires_at:
        return cached_keys

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(_jwks_url())
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _unauthorized(f"Unable to fetch Keycloak certs: {exc}") from exc

    jwks = response.json().get("keys", [])
    if not jwks:
        raise _unauthorized("Keycloak certs response did not include signing keys")

    _JWKS_CACHE["keys"] = jwks
    _JWKS_CACHE["expires_at"] = now + _JWKS_CACHE_TTL_SECONDS
    return jwks


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    token = credentials.credentials

    try:
        token_header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _unauthorized("Invalid token") from exc

    signing_keys = await _fetch_jwks()
    signing_key = _find_signing_key(signing_keys, token_header.get("kid"))

    if signing_key is None:
        signing_keys = await _fetch_jwks(force_refresh=True)
        signing_key = _find_signing_key(signing_keys, token_header.get("kid"))

    if signing_key is None:
        raise _unauthorized("Invalid token")

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[token_header.get("alg", "RS256")],
            issuer=_issuer(),
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise _unauthorized("Invalid token") from exc

    return payload