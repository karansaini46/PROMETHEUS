"""PROMETHEUS OpenTelemetry Tracing Initialization & Span Helpers.

Provides vendor-neutral distributed tracing, context propagation, correlation IDs,
and privacy-preserving telemetry across all subsystems (API, agents, models, tools,
code intel, sandbox, and training).
"""

import contextvars
import functools
import inspect
import logging
import re
import time
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Status, StatusCode

_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[a-zA-Z0-9_]{30,}", re.IGNORECASE),
    re.compile(r"glpat-[a-zA-Z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE),
    re.compile(r"(?:postgresql|postgres|mysql|redis)://([^:]+):([^@]+)@", re.IGNORECASE),
]


def sanitize_secrets(text: str) -> str:
    """Scrub secrets from strings."""
    for pattern in _SECRET_PATTERNS:
        if "://" in pattern.pattern:
            text = pattern.sub(r"\1:[REDACTED_PASSWORD]@", text)
        else:
            text = pattern.sub("[REDACTED_SECRET]", text)
    return text


logger = logging.getLogger("prometheus.telemetry")

# Global context variable for cross-boundary correlation ID propagation
correlation_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="untracked"
)

P = ParamSpec("P")
R = TypeVar("R")


def get_current_correlation_id() -> str:
    """Return the active correlation ID in the current execution context."""
    return correlation_id_ctx.get()


def set_current_correlation_id(corr_id: str) -> None:
    """Set the active correlation ID for the current execution context."""
    correlation_id_ctx.set(corr_id)


def sanitize_span_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    """Scrub sensitive keys, passwords, and raw confidential prompts from span attributes."""
    cleaned: dict[str, Any] = {}
    sensitive_keys = {
        "api_key",
        "secret",
        "password",
        "token",
        "authorization",
        "credentials",
        "private_key",
    }

    for k, v in attrs.items():
        k_lower = k.lower()
        if any(s in k_lower for s in sensitive_keys):
            cleaned[k] = "[REDACTED]"
            continue

        if isinstance(v, str):
            # Apply regex scrubber
            cleaned[k] = sanitize_secrets(v)
            # Cap attribute string size to 1024 characters to avoid huge payloads
            if len(cleaned[k]) > 1024:
                cleaned[k] = cleaned[k][:1021] + "..."
        elif isinstance(v, (int, float, bool)):
            cleaned[k] = v
        elif v is None:
            cleaned[k] = ""
        else:
            cleaned[k] = str(v)[:256]

    return cleaned


def setup_telemetry(
    service_name: str = "prometheus-api",
    enabled: bool = False,
    endpoint: str | None = None,
) -> trace.Tracer:
    """Initialize OpenTelemetry tracer provider with resources and exporters."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if enabled:
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
                provider.add_span_processor(processor)
                logger.info(
                    "OpenTelemetry OTLP exporter enabled for service: %s (%s)",
                    service_name,
                    endpoint,
                )
            except Exception as err:
                logger.warning(
                    "Failed to initialize OTLP exporter, falling back to ConsoleSpanExporter: %s",
                    err,
                )
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            processor = BatchSpanProcessor(ConsoleSpanExporter())
            provider.add_span_processor(processor)
            logger.info("OpenTelemetry Console exporter enabled for service: %s", service_name)
    else:
        logger.debug("OpenTelemetry remote exporter is disabled.")

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


def get_tracer(name: str = "prometheus") -> trace.Tracer:
    """Retrieve an OpenTelemetry tracer for instrumentation."""
    return trace.get_tracer(name)


def record_error_category(
    span: trace.Span,
    exc: Exception,
    category: str | None = None,
) -> None:
    """Record exception and error category on span with sanitized message."""
    cat = category or exc.__class__.__name__
    span.set_attribute("error", True)
    span.set_attribute("error.category", cat)
    span.set_attribute("error.type", exc.__class__.__name__)
    span.set_attribute("error.message", sanitize_secrets(str(exc))[:512])
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, description=cat))


def record_model_usage(
    span: trace.Span,
    provider: str | None = None,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float | None = None,
) -> None:
    """Record model token usage and cost accounting attributes on span."""
    if provider:
        span.set_attribute("gen_ai.system", provider)
    if model:
        span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("model.usage.prompt_tokens", prompt_tokens)
    span.set_attribute("model.usage.completion_tokens", completion_tokens)
    span.set_attribute("model.usage.total_tokens", total_tokens)
    if cost_usd is not None:
        span.set_attribute("model.cost_estimate_usd", round(cost_usd, 6))


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    category: str | None = None,
    tracer_name: str = "prometheus",
) -> Generator[trace.Span, None, None]:
    """Synchronous context manager creating a traced span with auto-correlation."""
    tracer = get_tracer(tracer_name)
    corr_id = get_current_correlation_id()
    attrs = {"correlation_id": corr_id}
    if attributes:
        attrs.update(attributes)
    safe_attrs = sanitize_span_attributes(attrs)

    start_time = time.perf_counter()
    with tracer.start_as_current_span(name, attributes=safe_attrs) as span:
        try:
            yield span
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            span.set_attribute("execution.duration_ms", round(duration_ms, 2))
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            span.set_attribute("execution.duration_ms", round(duration_ms, 2))
            record_error_category(span, exc, category=category)
            raise


@asynccontextmanager
async def trace_span_async(
    name: str,
    attributes: dict[str, Any] | None = None,
    category: str | None = None,
    tracer_name: str = "prometheus",
) -> AsyncGenerator[trace.Span, None]:
    """Asynchronous context manager creating a traced span with auto-correlation."""
    tracer = get_tracer(tracer_name)
    corr_id = get_current_correlation_id()
    attrs = {"correlation_id": corr_id}
    if attributes:
        attrs.update(attributes)
    safe_attrs = sanitize_span_attributes(attrs)

    start_time = time.perf_counter()
    with tracer.start_as_current_span(name, attributes=safe_attrs) as span:
        try:
            yield span
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            span.set_attribute("execution.duration_ms", round(duration_ms, 2))
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            span.set_attribute("execution.duration_ms", round(duration_ms, 2))
            record_error_category(span, exc, category=category)
            raise


def traced(
    span_name: str | None = None,
    attributes: dict[str, Any] | None = None,
    category: str | None = None,
    tracer_name: str = "prometheus",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to trace functions (both sync and async) with OpenTelemetry spans."""

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        name = span_name or fn.__name__

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                async with trace_span_async(
                    name=name,
                    attributes=attributes,
                    category=category,
                    tracer_name=tracer_name,
                ):
                    return await fn(*args, **kwargs)

            return async_wrapper  # type: ignore

        @functools.wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            with trace_span(
                name=name,
                attributes=attributes,
                category=category,
                tracer_name=tracer_name,
            ):
                return fn(*args, **kwargs)

        return sync_wrapper

    return decorator
