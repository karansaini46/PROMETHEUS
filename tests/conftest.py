"""Pytest configuration and global fixtures."""

import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure testing environment points to isolated test database
os.environ["PROMETHEUS_ENV"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"
if "DATABASE_URL" not in os.environ or "prometheus_db" in os.environ["DATABASE_URL"]:
    os.environ["DATABASE_URL"] = (
        "postgresql+asyncpg://prometheus:prometheus@localhost:5432/prometheus_test"
    )

from services.api.config import get_settings
from services.api.db import get_db_session
from services.api.main import app

settings = get_settings()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Isolated database session for unit and integration testing."""
    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    test_sessionmaker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with test_sessionmaker() as session:
        yield session
    await test_engine.dispose()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing the FastAPI application with isolated per-test DB."""
    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    test_sessionmaker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def _test_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db_session] = _test_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
    await test_engine.dispose()
