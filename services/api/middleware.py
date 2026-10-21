"""PROMETHEUS API Middleware & Global Exception Handlers.

Provides:
- Request correlation ID injection, OpenTelemetry span tracking, and propagation.
- Request timeout enforcement with cooperative cancellation.
- In-memory rate limiting with sliding window counters.
- Request body payload size limits.
- Safe structured error responses that never leak stack traces, paths, or secrets.
"""

import asyncio
import logging
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry.trace import Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from prometheus_ai.execution.guards import (
    PathTraversalError,
    ProtectedPathError,
    ResourceLimitExceededError,
    SecurityException,
)
from services.api.security import sanitize_message_for_client
from services.api.state_machine import InvalidStateTransitionError
from services.api.telemetry import (
    get_tracer,
    sanitize_span_attributes,
    set_current_correlation_id,
)

logger = logging.getLogger("prometheus.api")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every incoming HTTP request receives a tracked correlation ID and OpenTelemetry span."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or f"corr-{uuid4().hex[:12]}"
        )
        request.state.correlation_id = corr_id
        set_current_correlation_id(corr_id)

        tracer = get_tracer("prometheus.api")
        span_attrs = sanitize_span_attributes(
            {
                "http.method": request.method,
                "http.url": str(request.url),
                "http.target": request.url.path,
                "correlation_id": corr_id,
                "client.address": request.client.host if request.client else "unknown",
            }
        )

        with tracer.start_as_current_span(
            f"http {request.method} {request.url.path}", attributes=span_attrs
        ) as span:
            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                else:
                    span.set_status(Status(StatusCode.OK))
                response.headers["X-Correlation-ID"] = corr_id
                return response
            except Exception as exc:
                span.set_attribute("http.status_code", 500)
                span.set_attribute("error", True)
                span.set_attribute("error.type", exc.__class__.__name__)
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Enforce maximum execution duration per HTTP request."""

    def __init__(self, app: ASGIApp, timeout_seconds: float = 60.0) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        # Allow health checks and readiness probes to bypass long timeouts
        if request.url.path in ("/api/v1/health", "/api/v1/ready", "/health", "/ready"):
            return await call_next(request)

        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
        except TimeoutError:
            logger.warning(
                "Request timed out after %.1fs [correlation_id=%s, path=%s]",
                self.timeout_seconds,
                corr_id,
                request.url.path,
            )
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "error": "RequestTimeoutError",
                    "message": f"Request processing timed out after {self.timeout_seconds}s.",
                    "correlation_id": corr_id,
                },
                headers={"X-Correlation-ID": corr_id},
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding window rate limiter per client IP address."""

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 300,
        max_requests_per_minute: int | None = None,
    ) -> None:
        super().__init__(app)
        self.limit = (
            max_requests_per_minute if max_requests_per_minute is not None else requests_per_minute
        )
        self.window_seconds = 60.0
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Exempt health probes from rate limits
        if request.url.path in ("/api/v1/health", "/api/v1/ready", "/health", "/ready"):
            return await call_next(request)

        corr_id = getattr(request.state, "correlation_id", "unknown")
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()

        async with self._lock:
            # Purge entries older than window
            timestamps = [t for t in self._history[client_ip] if now - t < self.window_seconds]
            if len(timestamps) >= self.limit:
                retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
                logger.warning(
                    "Rate limit exceeded for IP %s [count=%d, correlation_id=%s]",
                    client_ip,
                    len(timestamps),
                    corr_id,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "RateLimitExceeded",
                        "message": f"Rate limit of {self.limit} req/min exceeded. Please retry after {retry_after} seconds.",
                        "correlation_id": corr_id,
                    },
                    headers={
                        "Retry-After": str(max(retry_after, 1)),
                        "X-Correlation-ID": corr_id,
                    },
                )

            timestamps.append(now)
            self._history[client_ip] = timestamps

        return await call_next(request)


class MaxPayloadSizeMiddleware(BaseHTTPMiddleware):
    """Reject requests with payloads exceeding safe boundaries to prevent memory exhaustion."""

    def __init__(self, app: ASGIApp, max_bytes: int = 10_000_000) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_bytes:
                    logger.warning(
                        "Payload too large: %d bytes (limit: %d) [correlation_id=%s]",
                        length,
                        self.max_bytes,
                        corr_id,
                    )
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "PayloadTooLargeError",
                            "message": f"Request body exceeds maximum permitted size of {self.max_bytes} bytes.",
                            "correlation_id": corr_id,
                        },
                        headers={"X-Correlation-ID": corr_id},
                    )
            except ValueError:
                pass

        return await call_next(request)


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform, safe exception handlers for the application."""

    @app.exception_handler(InvalidStateTransitionError)
    async def invalid_state_transition_handler(
        request: Request, exc: InvalidStateTransitionError
    ) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.warning(
            "Invalid state transition attempted [correlation_id=%s]: %s",
            corr_id,
            exc,
        )
        data = exc.to_dict()
        data["correlation_id"] = corr_id
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=data,
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(PathTraversalError)
    async def path_traversal_handler(request: Request, exc: PathTraversalError) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.warning("Path traversal attempt blocked [correlation_id=%s]: %s", corr_id, exc)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "PathTraversalError",
                "message": "Path traversal or directory escape detected and rejected.",
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(ProtectedPathError)
    async def protected_path_handler(request: Request, exc: ProtectedPathError) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.warning("Protected path access blocked [correlation_id=%s]: %s", corr_id, exc)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "ProtectedPathError",
                "message": "Access to protected system or credential file is denied.",
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(ResourceLimitExceededError)
    async def resource_limit_handler(
        request: Request, exc: ResourceLimitExceededError
    ) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.warning("Resource limit exceeded [correlation_id=%s]: %s", corr_id, exc)
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "error": "ResourceLimitExceededError",
                "message": sanitize_message_for_client(str(exc)),
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(SecurityException)
    async def security_exception_handler(request: Request, exc: SecurityException) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.warning("Security policy violation [correlation_id=%s]: %s", corr_id, exc)
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": exc.__class__.__name__,
                "message": sanitize_message_for_client(str(exc)),
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.info("Request validation failed [correlation_id=%s]: %s", corr_id, exc.errors())
        clean_errors = []
        for err in exc.errors():
            clean_errors.append(
                {
                    "loc": [str(loc) for loc in err.get("loc", [])],
                    "msg": sanitize_message_for_client(err.get("msg", "")),
                    "type": err.get("type", "value_error"),
                }
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "ValidationError",
                "message": "Input validation failed. Please check the request payload.",
                "details": clean_errors,
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.exception("Unhandled server exception [correlation_id=%s]: %s", corr_id, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An internal server error occurred. Please contact the administrator.",
                "correlation_id": corr_id,
            },
            headers={"X-Correlation-ID": corr_id},
        )
