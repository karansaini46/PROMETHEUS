"""PROMETHEUS API Middleware & Global Exception Handlers.

Provides:
- Request correlation ID injection and propagation.
- Safe structured error responses that never leak stack traces or env variables.
"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from services.api.security import sanitize_message_for_client
from services.api.state_machine import InvalidStateTransitionError

logger = logging.getLogger("prometheus.api")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every incoming HTTP request receives a tracked correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        corr_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or f"corr-{uuid4().hex[:12]}"
        )
        request.state.correlation_id = corr_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        return response


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
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=data)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.info("Request validation failed [correlation_id=%s]: %s", corr_id, exc.errors())
        # Clean validation errors
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
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        corr_id = getattr(request.state, "correlation_id", "unknown")
        logger.exception("Unhandled server exception [correlation_id=%s]: %s", corr_id, exc)

        # Never leak stack traces, internal paths, or environment variables
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An internal server error occurred. Please contact the administrator.",
                "correlation_id": corr_id,
            },
        )
