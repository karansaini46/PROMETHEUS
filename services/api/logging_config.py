"""PROMETHEUS Structured Logging Baseline.

Provides JSON-formatted or human-readable structured log records
with trace correlation, context propagation, and secrets sanitization.
"""

import json
import logging
import re
import sys
from typing import Any

from opentelemetry import trace

from services.api.telemetry import get_current_correlation_id

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"github_pat_[a-zA-Z0-9_]{30,}", re.IGNORECASE),
    re.compile(r"glpat-[a-zA-Z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"(?:postgresql|postgres|mysql|redis)://([^:]+):([^@]+)@", re.IGNORECASE),
    re.compile(
        r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC )?PRIVATE KEY-----"
    ),
]


def redact_secrets(text: str) -> str:
    """Scrub known API keys, database credentials, and tokens from log messages."""
    for pattern in SECRET_PATTERNS:
        # For database URLs, keep the protocol and username but redact the password
        if "://" in pattern.pattern:
            text = pattern.sub(r"\1:[REDACTED_PASSWORD]@", text)
        else:
            text = pattern.sub("[REDACTED_SECRET]", text)
    return text


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter adhering to OpenTelemetry/Cloud standard schemas."""

    def format(self, record: logging.LogRecord) -> str:
        corr_id = getattr(record, "correlation_id", None) or get_current_correlation_id()

        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            "module": record.module,
            "line": record.lineno,
            "correlation_id": corr_id,
        }

        # Inject OpenTelemetry trace context if an active span exists
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_ctx = span.get_span_context()
            log_entry["trace_id"] = f"{span_ctx.trace_id:032x}"
            log_entry["span_id"] = f"{span_ctx.span_id:016x}"

        if record.exc_info:
            log_entry["exception"] = redact_secrets(self.formatException(record.exc_info))

        # Include custom extra fields if provided
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                if isinstance(value, str):
                    log_entry[key] = redact_secrets(value)
                else:
                    log_entry[key] = value

        return json.dumps(log_entry)


class StandardFormatter(logging.Formatter):
    """Human-readable formatter with correlation ID and secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        corr_id = getattr(record, "correlation_id", None) or get_current_correlation_id()
        msg = super().format(record)
        redacted = redact_secrets(msg)
        if corr_id and corr_id != "untracked":
            return f"[{corr_id}] {redacted}"
        return redacted


def setup_logging(level: str = "INFO", json_format: bool = False) -> logging.Logger:
    """Initialize root and application loggers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers on re-init
    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            StandardFormatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)
    return logging.getLogger("prometheus")
