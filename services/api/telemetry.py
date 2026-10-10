"""PROMETHEUS OpenTelemetry Tracing Initialization."""

import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger("prometheus.telemetry")


def setup_telemetry(service_name: str, enabled: bool = False) -> trace.Tracer:
    """Initialize OpenTelemetry tracer provider."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if enabled:
        # In local dev or production when enabled, add span processor
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
        logger.info("OpenTelemetry enabled for service: %s", service_name)
    else:
        logger.debug("OpenTelemetry remote exporter is disabled.")

    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
