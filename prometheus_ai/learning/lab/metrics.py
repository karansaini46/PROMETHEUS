"""Telemetry, metrics collection, and structured logging for the PROMETHEUS ML Lab.

Captures training loss, validation loss, perplexity, throughput, duration,
peak memory, and inference benchmarking statistics.
"""

from __future__ import annotations

import json
import math
import resource
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import torch


def get_peak_memory_mb() -> float:
    """Measure peak resident set memory usage in Megabytes."""
    if torch.cuda.is_available():
        cuda_mem = torch.cuda.max_memory_allocated() / (1024 * 1024)
        if cuda_mem > 0:
            return round(cuda_mem, 2)

    # On Linux, ru_maxrss is in Kilobytes
    usage_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(usage_kb / 1024.0, 2)


def calculate_perplexity(loss: float) -> float:
    """Safely calculate perplexity = exp(loss), capping to avoid float overflow."""
    try:
        # Cap loss at 100 to prevent math range overflow
        capped_loss = min(max(loss, 0.0), 100.0)
        return float(math.exp(capped_loss))
    except OverflowError:
        return float("inf")


@dataclass
class StepMetrics:
    """Detailed telemetry captured at each training log step."""

    step: int
    epoch: int
    train_loss: float
    train_perplexity: float
    learning_rate: float
    throughput_tokens_per_sec: float
    throughput_samples_per_sec: float
    elapsed_seconds: float
    peak_memory_mb: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationMetrics:
    """Metrics computed on validation or test evaluation partitions."""

    step: int
    epoch: int
    val_loss: float
    val_perplexity: float
    token_accuracy: float
    eval_duration_seconds: float
    split_name: str = "validation"
    sample_generations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InferenceBenchmarkMetrics:
    """Benchmarking statistics for model inference latency and throughput."""

    model_type: str
    device: str
    batch_size: int
    prompt_tokens: int
    generated_tokens: int
    total_tokens: int
    iterations: int
    latency_ms_mean: float
    latency_ms_p50: float
    latency_ms_p90: float
    latency_ms_p99: float
    throughput_tokens_per_sec: float
    model_size_mb: float
    peak_memory_mb: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrainingLogger:
    """Structured logging sink for laboratory experiments."""

    def __init__(self, log_file: Path | str | None = None) -> None:
        self.log_file = Path(log_file) if log_file else None
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            # Create or truncate existing log file
            self.log_file.write_text("", encoding="utf-8")

        self.step_history: list[StepMetrics] = []
        self.validation_history: list[ValidationMetrics] = []

    def log_step(self, metrics: StepMetrics) -> None:
        """Record step metrics in memory and append to jsonl file."""
        self.step_history.append(metrics)
        if self.log_file:
            payload = {"type": "step", **metrics.to_dict()}
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")

    def log_validation(self, metrics: ValidationMetrics) -> None:
        """Record validation metrics in memory and append to jsonl file."""
        self.validation_history.append(metrics)
        if self.log_file:
            payload = {"type": "validation", **metrics.to_dict()}
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")

    def get_summary(self) -> dict[str, Any]:
        """Aggregate summary of the training run."""
        if not self.step_history:
            return {
                "total_steps": 0,
                "final_train_loss": None,
                "best_val_loss": None,
                "best_val_perplexity": None,
            }

        final_step = self.step_history[-1]
        best_val = min(self.validation_history, key=lambda m: m.val_loss, default=None)

        return {
            "total_steps": final_step.step,
            "final_train_loss": round(final_step.train_loss, 4),
            "final_train_perplexity": round(final_step.train_perplexity, 4),
            "best_val_loss": round(best_val.val_loss, 4) if best_val else None,
            "best_val_perplexity": round(best_val.val_perplexity, 4) if best_val else None,
            "best_val_step": best_val.step if best_val else None,
            "total_training_duration_seconds": round(final_step.elapsed_seconds, 2),
            "peak_memory_mb": max(
                (m.peak_memory_mb for m in self.step_history if m.peak_memory_mb is not None),
                default=None,
            ),
        }
