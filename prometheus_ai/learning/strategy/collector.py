"""Execution Trace Collection and Sanitization Subsystem.

Responsible for recording structured execution traces from debugging workflows,
strictly scrubbing secrets and redacting unnecessary sensitive source code.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
)
from prometheus_ai.models.sanitizer import sanitize_dict

logger = logging.getLogger(__name__)

# Maximum character threshold for source snippets or observation strings
MAX_SNIPPET_LENGTH = 1000


class TraceSanitizer:
    """Sanitizes trace payloads to ensure secrets and excessive source content are eliminated."""

    def __init__(
        self,
        custom_secrets: list[str] | None = None,
        max_snippet_len: int = MAX_SNIPPET_LENGTH,
    ) -> None:
        self.custom_secrets = custom_secrets or []
        self.max_snippet_len = max_snippet_len

    def _truncate_strings(self, data: Any) -> Any:
        """Recursively truncate long string payloads to avoid leaking source files."""
        if isinstance(data, str):
            if len(data) > self.max_snippet_len:
                return data[: self.max_snippet_len] + f"... [TRUNCATED_{len(data)}_CHARS]"
            return data
        if isinstance(data, dict):
            return {k: self._truncate_strings(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._truncate_strings(item) for item in data]
        return data

    def sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Scrub known secret patterns and truncate oversized text buffers."""
        sanitized = sanitize_dict(data, custom_secrets=self.custom_secrets)
        return self._truncate_strings(sanitized)


class TraceCollector:
    """Collects, validates, filters, and manages structured execution traces."""

    def __init__(
        self,
        sanitizer: TraceSanitizer | None = None,
        storage_path: Path | None = None,
    ) -> None:
        self.sanitizer = sanitizer or TraceSanitizer()
        self.storage_path = storage_path
        self._traces: list[ExecutionTrace] = []

    @property
    def total_traces(self) -> int:
        return len(self._traces)

    def record_trace(
        self,
        task_id: str,
        task_category: TaskCategory | str,
        step_index: int,
        initial_state: dict[str, Any],
        available_tools: list[str],
        chosen_action: str,
        action_inputs: dict[str, Any],
        relevant_observations: dict[str, Any],
        outcome: ActionOutcome | str,
        cost_usd: float,
        latency_ms: float,
        final_evaluation_result: bool | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> ExecutionTrace:
        """Sanitize and record an execution trace."""
        if isinstance(task_category, str):
            task_category = TaskCategory(task_category)
        if isinstance(outcome, str):
            outcome = ActionOutcome(outcome)

        sanitized_initial = self.sanitizer.sanitize(initial_state)
        sanitized_inputs = self.sanitizer.sanitize(action_inputs)
        sanitized_observations = self.sanitizer.sanitize(relevant_observations)
        sanitized_metadata = self.sanitizer.sanitize(metadata or {})

        trace = ExecutionTrace(
            trace_id=trace_id or f"tr-{uuid.uuid4().hex[:10]}",
            task_id=task_id,
            task_category=task_category,
            step_index=step_index,
            initial_state=sanitized_initial,
            available_tools=list(available_tools),
            chosen_action=chosen_action,
            action_inputs=sanitized_inputs,
            relevant_observations=sanitized_observations,
            outcome=outcome,
            cost_usd=max(0.0, float(cost_usd)),
            latency_ms=max(0.0, float(latency_ms)),
            final_evaluation_result=final_evaluation_result,
            metadata=sanitized_metadata,
        )

        self._traces.append(trace)

        if self.storage_path:
            self._append_to_file(trace)

        return trace

    def _append_to_file(self, trace: ExecutionTrace) -> None:
        """Persist single trace to disk in JSONL format."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace.to_dict()) + "\n")
        except Exception as exc:
            logger.warning(f"Failed to append trace {trace.trace_id} to file: {exc}")

    def get_traces(
        self,
        task_category: TaskCategory | None = None,
        tool_name: str | None = None,
        successful_only: bool = False,
        resolved_only: bool = False,
    ) -> list[ExecutionTrace]:
        """Query collected traces matching filter criteria."""
        results = self._traces
        if task_category is not None:
            results = [t for t in results if t.task_category == task_category]
        if tool_name is not None:
            results = [t for t in results if t.chosen_action == tool_name]
        if successful_only:
            results = [t for t in results if t.outcome == ActionOutcome.SUCCESS]
        if resolved_only:
            results = [t for t in results if t.final_evaluation_result is True]
        return results

    def compute_tool_statistics(
        self, task_category: TaskCategory | None = None
    ) -> dict[str, dict[str, float]]:
        """Compute empirical success rate, average cost, and latency per tool."""
        traces = self.get_traces(task_category=task_category)
        stats: dict[str, dict[str, float]] = {}

        for t in traces:
            tool = t.chosen_action
            if tool not in stats:
                stats[tool] = {
                    "total_calls": 0.0,
                    "successful_calls": 0.0,
                    "total_cost_usd": 0.0,
                    "total_latency_ms": 0.0,
                    "resolved_task_count": 0.0,
                }
            stats[tool]["total_calls"] += 1.0
            if t.outcome == ActionOutcome.SUCCESS:
                stats[tool]["successful_calls"] += 1.0
            stats[tool]["total_cost_usd"] += t.cost_usd
            stats[tool]["total_latency_ms"] += t.latency_ms
            if t.final_evaluation_result is True:
                stats[tool]["resolved_task_count"] += 1.0

        results: dict[str, dict[str, float]] = {}
        for tool, s in stats.items():
            calls = s["total_calls"]
            results[tool] = {
                "total_calls": calls,
                "success_rate": s["successful_calls"] / calls if calls > 0 else 0.0,
                "avg_cost_usd": s["total_cost_usd"] / calls if calls > 0 else 0.0,
                "avg_latency_ms": s["total_latency_ms"] / calls if calls > 0 else 0.0,
                "task_resolution_rate": s["resolved_task_count"] / calls if calls > 0 else 0.0,
            }

        return results

    def export_jsonl(self, output_path: Path) -> int:
        """Export all traces to a JSONL file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for trace in self._traces:
                f.write(json.dumps(trace.to_dict()) + "\n")
        return len(self._traces)

    def load_jsonl(self, input_path: Path) -> int:
        """Load traces from a JSONL file into memory."""
        loaded = 0
        with open(input_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    trace = ExecutionTrace.from_dict(data)
                    self._traces.append(trace)
                    loaded += 1
        return loaded

    def clear(self) -> None:
        """Clear in-memory trace collection."""
        self._traces.clear()
