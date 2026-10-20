"""PROMETHEUS FastAPI Application Server."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.config import get_settings
from services.api.logging_config import setup_logging
from services.api.middleware import CorrelationIdMiddleware, register_exception_handlers
from services.api.routes import (
    code_intel_router,
    experiments_router,
    health_router,
    memory_router,
    models_router,
    runs_router,
    tasks_router,
)
from services.api.telemetry import setup_telemetry

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger = setup_logging(level=settings.LOG_LEVEL)
    logger.info("Starting PROMETHEUS API server (env=%s)...", settings.PROMETHEUS_ENV)

    setup_telemetry(
        service_name=settings.OTEL_SERVICE_NAME,
        enabled=settings.OTEL_EXPORTER_ENABLED,
    )
    yield
    logger.info("PROMETHEUS API server shut down.")


def create_app() -> FastAPI:
    """Initialize and configure the FastAPI application."""
    app = FastAPI(
        title="PROMETHEUS API",
        version="0.1.0",
        description="Autonomous AI Software Engineering and Debugging Platform",
        lifespan=lifespan,
    )

    # Correlation ID middleware
    app.add_middleware(CorrelationIdMiddleware)

    # CORS configuration for the Next.js control plane
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register safe exception handlers (no tracebacks or env leaks)
    register_exception_handlers(app)

    # Mount v1 routes
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(code_intel_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")

    return app


app = create_app()
