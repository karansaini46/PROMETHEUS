"""PROMETHEUS Database Connection and Session Management."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from services.api.config import get_settings

logger = logging.getLogger("prometheus.db")

settings = get_settings()

engine_kwargs: dict[str, Any] = {
    "echo": (settings.PROMETHEUS_ENV == "development" and settings.LOG_LEVEL == "DEBUG"),
}

if settings.PROMETHEUS_ENV == "test":
    # In test environments, use NullPool so each test's event loop creates its own clean connections
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_health() -> bool:
    """Check if the database connection is alive without raising unhandled exceptions."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True
    except Exception as exc:
        logger.debug("Database healthcheck probe failed: %s", exc)
        return False
