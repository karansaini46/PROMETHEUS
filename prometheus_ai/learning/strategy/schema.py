"""Data models and schemas for the Experimental Learning Subsystem.

IMPORTANT ARCHITECTURAL DISTINCTION:
This subsystem does NOT modify the underlying language model's weights,
parameters, or prompt instructions, nor does it claim that the system
automatically modifies its own intelligence.

Its scope is strictly empirical: optimizing tool-selection and investigation
strategies for the autonomous debugging agent using recorded execution outcomes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TaskCategory(StrEnum):
    """Categorization of software engineering debugging tasks."""

    SYNTAX_BUG = "syntax_bug"
    REPRODUCTION = "reproduction"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    REGRESSION = "regression"
    FLAKY_TEST = "flaky_test"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    PERFORMANCE = "performance"
    SECURITY_VALIDATION = "security_validation"
    GENERAL = "general"


class ActionOutcome(StrEnum):
    """Execution outcome status of an individual tool call."""

    SUCCESS = "success"
    FAILURE = "failure"
    NO_OP = "no_op"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class ToolSelectionContext:
    """State context provided to a policy to select the next action.

    Guarantees:
    - `available_tools` represents the strict subset of tools authorized and permitted
      by sandbox and security policies for this step.
    - Sensitive strings and secrets are scrubbed before reaching the policy.
    """

    task_id: str
    task_category: TaskCategory
    issue_description: str
    step_index: int
    candidate_files: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)
    recent_history: list[dict[str, Any]] = field(default_factory=list)
    error_context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["task_category"] = self.task_category.value
        return data


@dataclass
class ToolSelectionDecision:
    """Structured decision returned by a tool-selection policy."""

    selected_tool: str
    rationale: str
    confidence: float = 1.0
    suggested_args: dict[str, Any] = field(default_factory=dict)
    is_fallback: bool = False
    policy_id: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionTrace:
    """Structured execution trace recording an individual tool invocation and outcome.

    Invariants:
    - Does NOT contain secrets, authorization keys, or unbounded sensitive source content.
    - Captures task category, initial state, authorized tools, chosen action, observations,
      outcome, cost, latency, and overall task evaluation result.
    """

    trace_id: str
    task_id: str
    task_category: TaskCategory
    step_index: int
    initial_state: dict[str, Any]
    available_tools: list[str]
    chosen_action: str
    action_inputs: dict[str, Any]
    relevant_observations: dict[str, Any]
    outcome: ActionOutcome
    cost_usd: float
    latency_ms: float
    final_evaluation_result: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["task_category"] = self.task_category.value
        data["outcome"] = self.outcome.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionTrace:
        return cls(
            trace_id=data.get("trace_id", f"tr-{uuid.uuid4().hex[:8]}"),
            task_id=data["task_id"],
            task_category=TaskCategory(data.get("task_category", TaskCategory.GENERAL.value)),
            step_index=int(data.get("step_index", 0)),
            initial_state=data.get("initial_state", {}),
            available_tools=list(data.get("available_tools", [])),
            chosen_action=data.get("chosen_action", ""),
            action_inputs=data.get("action_inputs", {}),
            relevant_observations=data.get("relevant_observations", {}),
            outcome=ActionOutcome(data.get("outcome", ActionOutcome.SUCCESS.value)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            latency_ms=float(data.get("latency_ms", 0.0)),
            final_evaluation_result=data.get("final_evaluation_result"),
            metadata=data.get("metadata", {}),
            timestamp=float(data.get("timestamp", time.time())),
        )
