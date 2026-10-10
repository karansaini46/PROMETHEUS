"""Unit tests for authentication boundaries and authorization enforcement."""

import pytest
from httpx import AsyncClient

from services.api.config import get_settings

settings = get_settings()


@pytest.mark.unit
async def test_local_default_allows_requests(async_client: AsyncClient) -> None:
    """In local development without auth headers, requests succeed."""
    res = await async_client.get("/api/v1/health")
    assert res.status_code == 200


@pytest.mark.unit
async def test_valid_api_key_header(async_client: AsyncClient) -> None:
    """Request with valid X-API-Key header is accepted."""
    headers = {"X-API-Key": settings.API_SECRET_KEY}
    res = await async_client.get("/api/v1/models", headers=headers)
    assert res.status_code == 200


@pytest.mark.unit
async def test_valid_bearer_token(async_client: AsyncClient) -> None:
    """Request with valid Authorization Bearer header is accepted."""
    headers = {"Authorization": f"Bearer {settings.API_SECRET_KEY}"}
    res = await async_client.get("/api/v1/models", headers=headers)
    assert res.status_code == 200


@pytest.mark.unit
async def test_invalid_api_key_rejected(async_client: AsyncClient) -> None:
    """Request with an invalid API key is strictly rejected with 401 Unauthorized."""
    headers = {"X-API-Key": "invalid-token-12345"}
    res = await async_client.get("/api/v1/models", headers=headers)
    assert res.status_code == 401
    assert "Invalid API authentication" in res.json()["detail"]


@pytest.mark.unit
async def test_invalid_bearer_token_rejected(async_client: AsyncClient) -> None:
    """Request with an invalid Bearer token is rejected with 401 Unauthorized."""
    headers = {"Authorization": "Bearer invalid-bearer-key"}
    res = await async_client.get("/api/v1/models", headers=headers)
    assert res.status_code == 401
    assert "Invalid API authentication" in res.json()["detail"]
