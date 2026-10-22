"""PROMETHEUS FastAPI Application Server."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.config import get_settings
from services.api.db import get_db_session
from services.api.logging_config import setup_logging
from services.api.middleware import (
    CorrelationIdMiddleware,
    MaxPayloadSizeMiddleware,
    RateLimitMiddleware,
    RequestTimeoutMiddleware,
    register_exception_handlers,
)
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
from services.api.worker import WorkerManager, recover_interrupted_tasks

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger = setup_logging(level=settings.LOG_LEVEL)
    logger.info("Starting PROMETHEUS API server (env=%s)...", settings.PROMETHEUS_ENV)

    # Initialize OpenTelemetry
    setup_telemetry(
        service_name=settings.OTEL_SERVICE_NAME,
        enabled=settings.OTEL_EXPORTER_ENABLED,
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
    )

    # Initialize worker supervisor and heartbeat
    worker = WorkerManager.get_instance()
    await worker.start()

    # Recover any runs interrupted during a prior crash or restart
    try:
        async for session in get_db_session():
            await recover_interrupted_tasks(session)
            break
    except Exception as err:
        logger.warning(
            "Could not perform startup task recovery (database may be uninitialized): %s", err
        )

    yield

    # Graceful shutdown: drain in-flight executions, cancel workers, cleanup resources
    logger.info("PROMETHEUS API server shutting down gracefully...")
    await worker.stop(timeout_seconds=5.0)
    logger.info("PROMETHEUS API server shut down completed.")


def create_app() -> FastAPI:
    """Initialize and configure the FastAPI application with security and reliability middleware."""
    app = FastAPI(
        title="PROMETHEUS API",
        version="0.1.0",
        description="Autonomous AI Software Engineering and Debugging Platform",
        lifespan=lifespan,
    )

    # 1. Payload size limit middleware (first line of defense against memory exhaustion)
    app.add_middleware(
        MaxPayloadSizeMiddleware,
        max_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )

    # 2. Rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    )

    # 3. Request timeout middleware (enforces bounded execution)
    app.add_middleware(
        RequestTimeoutMiddleware,
        timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS,
    )

    # 4. Correlation ID and tracing middleware
    app.add_middleware(CorrelationIdMiddleware)

    # 5. CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 6. Register safe exception handlers (no tracebacks or env leaks)
    register_exception_handlers(app)

    # 7. Mount Health and Readiness probes at root and API v1
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")

    # 8. Mount API v1 domain routes
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(runs_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(code_intel_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")

    return app


app = create_app()
