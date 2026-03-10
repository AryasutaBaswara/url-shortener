from uuid import uuid4

import pytest


pytestmark = pytest.mark.asyncio(loop_scope="session")

@pytest.mark.integration
async def test_shorten_and_redirect_flow(client, created_short_codes):
    original_url = f"https://example.com/integration/{uuid4()}"

    shorten_response = await client.post(
        "/api/v1/shorten",
        json={"original_url": original_url},
    )

    assert shorten_response.status_code == 200
    short_code = shorten_response.json()["short_code"]
    created_short_codes.add(short_code)

    redirect_response = await client.get(f"/{short_code}")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == original_url

@pytest.mark.integration
async def test_click_count_increments(client, created_short_codes):
    original_url = f"https://example.com/integration/{uuid4()}"

    shorten_response = await client.post(
        "/api/v1/shorten",
        json={"original_url": original_url},
    )

    assert shorten_response.status_code == 200
    short_code = shorten_response.json()["short_code"]
    created_short_codes.add(short_code)

    first_redirect = await client.get(f"/{short_code}")
    second_redirect = await client.get(f"/{short_code}")
    stats_response = await client.get(f"/api/v1/stats/{short_code}")

    assert first_redirect.status_code == 307
    assert second_redirect.status_code == 307
    assert stats_response.status_code == 200
    assert stats_response.json()["click_count"] == 2

@pytest.mark.integration
async def test_duplicate_custom_code(client, created_short_codes):
    custom_code = f"dup{uuid4().hex[:8]}"
    first_response = await client.post(
        "/api/v1/shorten",
        json={"original_url": f"https://example.com/integration/{uuid4()}", "custom_code": custom_code},
    )
    created_short_codes.add(custom_code)

    second_response = await client.post(
        "/api/v1/shorten",
        json={"original_url": f"https://example.com/integration/{uuid4()}", "custom_code": custom_code},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "Short code already exists"

@pytest.mark.integration
async def test_short_code_not_found(client):
    response = await client.get("/nonexistent_code")

    assert response.status_code == 404
    assert response.json()["detail"] == "Short URL not found"