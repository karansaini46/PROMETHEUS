"""Evaluation and Benchmark Subsystem Package."""

from dataclasses import dataclass


@dataclass
class BenchmarkResult:
    """Benchmark evaluation outcome for a task instance."""

    task_id: str
    resolved: bool
    iterations: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_seconds: float
