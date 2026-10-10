"""Pytest configuration and global fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from services.api.main import app

# Ensure testing environment
os.environ["PROMETHEUS_ENV"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
