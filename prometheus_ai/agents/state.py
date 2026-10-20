"""Autonomous Debugging Agent State Schemas and Event Data Models."""

import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class WorkflowStatus(StrEnum):
    """Execution statuses for the autonomous debugging workflow."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(StrEnum):
    """The 13 discrete phases of the autonomous debugging lifecycle."""

    VALIDATE_TASK = "validate_task"
    INSPECT_REPO = "inspect_repo"
    SEARCH_CODE = "search_code"
    HYPOTHESIZE = "hypothesize"
    PLAN_INVESTIGATION = "plan_investigation"
    EXECUTE_INSPECTION = "execute_inspection"
    ANALYZE_EVIDENCE = "analyze_evidence"
    PROPOSE_PATCH = "propose_patch"
    APPLY_PATCH = "apply_patch"
    RUN_TESTS = "run_tests"
    ANALYZE_TESTS = "analyze_tests"
    REVIEW_DIFF = "review_diff"
    GENERATE_REPORT = "generate_report"
    TERMINAL = "terminal"


@dataclass
class TaskSpec:
    """Specification of an incoming debugging task."""

    task_id: str
    issue_description: str
    repo_path: str
    test_runner: str = "pytest"
    test_target: str | None = None
    extra_args: list[str] = field(default_factory=list)
    max_retries: int = 3


@dataclass
class StepEvent:
    """Audit log entry capturing a discrete workflow transition."""

    step: WorkflowStep
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ToolCallRecord:
    """Record of a tool invocation, safety decision, and result."""

    tool_name: str
    inputs: dict[str, Any]
    output: Any
    success: bool
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class PlannerOutput:
    """Structured output from the Planner role."""

    hypotheses: list[str] = field(default_factory=list)
    investigation_plan: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


@dataclass
class InvestigatorOutput:
    """Structured output from the Investigator role."""

    evidence_collected: dict[str, Any] = field(default_factory=dict)
    root_cause_analysis: str = ""
    candidate_files: list[str] = field(default_factory=list)


@dataclass
class ImplementerOutput:
    """Structured output from the Implementer role."""

    patch_diff: str = ""
    explanation: str = ""
    files_modified: list[str] = field(default_factory=list)


@dataclass
class TestAnalystOutput:
    """Structured output from the Test Analyst role."""

    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    tests_not_run: list[str] = field(default_factory=list)
    should_retry: bool = False
    failure_diagnostics: str | None = None
    exit_code: int = 0
    duration_seconds: float = 0.0


@dataclass
class FinalReport:
    """Comprehensive evidence-backed final debugging report.

    Guarantees strict separation between model proposals and concrete verification.
    Consequential external actions (e.g. opening pull requests, merging, deploying)
    always require explicit human approval.
    """

    task_id: str
    proposed_changes: list[str] = field(default_factory=list)
    changes_actually_applied: list[str] = field(default_factory=list)
    commands_actually_executed: list[str] = field(default_factory=list)
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    tests_not_run: list[str] = field(default_factory=list)
    findings_remain_uncertain: list[str] = field(default_factory=list)
    is_resolved: bool = False
    requires_human_approval: bool = True
    summary: str = ""


@dataclass
class WorkflowState:
    """Complete durable state of an active or completed debugging workflow."""

    run_id: str
    task: TaskSpec
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: WorkflowStep = WorkflowStep.VALIDATE_TASK
    worktree_path: str | None = None
    iteration: int = 0

    # Role outputs
    planner_output: PlannerOutput = field(default_factory=PlannerOutput)
    investigator_output: InvestigatorOutput = field(default_factory=InvestigatorOutput)
    implementer_output: ImplementerOutput = field(default_factory=ImplementerOutput)
    test_analyst_output: TestAnalystOutput = field(default_factory=TestAnalystOutput)
    final_report: FinalReport | None = None

    # Audit trails and safety records
    history: list[StepEvent] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    applied_patches: list[str] = field(default_factory=list)
    executed_commands: list[str] = field(default_factory=list)

    # Control flags
    pause_requested: bool = False
    cancel_requested: bool = False
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_event(
        self,
        step: WorkflowStep,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.history.append(
            StepEvent(
                step=step,
                details=details or {},
                error=error,
            )
        )

    def record_tool_call(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        output: Any,
        success: bool,
        error: str | None = None,
    ) -> None:
        self.tool_calls.append(
            ToolCallRecord(
                tool_name=tool_name,
                inputs=inputs,
                output=output,
                success=success,
                error=error,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert state into a JSON-serializable dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        data["current_step"] = self.current_step.value
        for event in data.get("history", []):
            if isinstance(event.get("step"), WorkflowStep):
                event["step"] = event["step"].value
        return data


# Preserved for backward compatibility
@dataclass
class AgentState:
    """Legacy state schema for backward compatibility."""

    run_id: str
    issue_description: str
    worktree_path: str
    hypotheses: list[str] = field(default_factory=list)
    candidate_files: list[str] = field(default_factory=list)
    reproduce_script: str | None = None
    patch_diff: str | None = None
    sandbox_logs: list[str] = field(default_factory=list)
    iteration_count: int = 0
    resolved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
