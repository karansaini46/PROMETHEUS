"""PROMETHEUS Structured Logging Baseline.

Provides JSON-formatted or human-readable structured log records
with trace correlation, context propagation, and secrets sanitization.
"""

import json
import logging
import re
import sys
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Scrub known API keys and tokens from log messages."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter adhering to OpenTelemetry/Cloud standard schemas."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
            "module": record.module,
            "line": record.lineno,
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry)


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
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)
    return logging.getLogger("prometheus")
