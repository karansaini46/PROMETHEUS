"""State Checkpointing and Snapshot Persistence."""

import json
import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from prometheus_ai.agents.state import (
    FinalReport,
    ImplementerOutput,
    InvestigatorOutput,
    PlannerOutput,
    StepEvent,
    TaskSpec,
    TestAnalystOutput,
    ToolCallRecord,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


class BaseCheckpointer(ABC):
    """Abstract checkpointer for durable workflow execution state."""

    @abstractmethod
    def save(self, state: WorkflowState) -> None:
        """Save a state snapshot."""
        raise NotImplementedError

    @abstractmethod
    def load(self, run_id: str) -> WorkflowState | None:
        """Load a state snapshot by run_id."""
        raise NotImplementedError

    @abstractmethod
    def list_runs(self) -> list[str]:
        """List all tracked run IDs."""
        raise NotImplementedError


class MemoryCheckpointer(BaseCheckpointer):
    """Thread-safe in-memory checkpointer."""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, state: WorkflowState) -> None:
        with self._lock:
            self._states[state.run_id] = state.to_dict()

    def load(self, run_id: str) -> WorkflowState | None:
        with self._lock:
            data = self._states.get(run_id)
            if not data:
                return None
            return deserialize_workflow_state(data)

    def list_runs(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())


class FileCheckpointer(BaseCheckpointer):
    """File-backed JSON checkpointer for local crash recovery and resumption.

    # ponytail: Local atomic JSON files provide complete durability, crash recovery,
    # and resumability without database overhead. Upgrade path: PostgreSQL checkpoints table.
    """

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        if storage_dir:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = Path("/tmp/prometheus_checkpoints")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _file_path(self, run_id: str) -> Path:
        return self.storage_dir / f"{run_id}.json"

    def save(self, state: WorkflowState) -> None:
        with self._lock:
            path = self._file_path(state.run_id)
            tmp_path = path.with_suffix(".tmp")
            data = state.to_dict()
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_path.replace(path)

    def load(self, run_id: str) -> WorkflowState | None:
        with self._lock:
            path = self._file_path(run_id)
            if not path.exists():
                return None
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                return deserialize_workflow_state(data)
            except Exception as err:
                logger.error("Failed to load checkpoint %s: %s", path, err)
                return None

    def list_runs(self) -> list[str]:
        with self._lock:
            return [p.stem for p in self.storage_dir.glob("*.json")]


def deserialize_workflow_state(data: dict[str, Any]) -> WorkflowState:
    """Reconstruct a typed WorkflowState object from a serialized dictionary."""
    task_data = data.get("task", {})
    task = TaskSpec(
        task_id=task_data.get("task_id", ""),
        issue_description=task_data.get("issue_description", ""),
        repo_path=task_data.get("repo_path", ""),
        test_runner=task_data.get("test_runner", "pytest"),
        test_target=task_data.get("test_target"),
        extra_args=task_data.get("extra_args", []),
        max_retries=task_data.get("max_retries", 3),
    )

    state = WorkflowState(
        run_id=data["run_id"],
        task=task,
        status=WorkflowStatus(data.get("status", WorkflowStatus.PENDING.value)),
        current_step=WorkflowStep(data.get("current_step", WorkflowStep.VALIDATE_TASK.value)),
        worktree_path=data.get("worktree_path"),
        iteration=data.get("iteration", 0),
        planner_output=PlannerOutput(**data.get("planner_output", {})),
        investigator_output=InvestigatorOutput(**data.get("investigator_output", {})),
        implementer_output=ImplementerOutput(**data.get("implementer_output", {})),
        test_analyst_output=TestAnalystOutput(**data.get("test_analyst_output", {})),
        applied_patches=data.get("applied_patches", []),
        executed_commands=data.get("executed_commands", []),
        pause_requested=data.get("pause_requested", False),
        cancel_requested=data.get("cancel_requested", False),
        error=data.get("error"),
        metadata=data.get("metadata", {}),
    )

    # Reconstruct final report if present
    fr_data = data.get("final_report")
    if fr_data:
        state.final_report = FinalReport(**fr_data)

    # Reconstruct history events
    for ev_data in data.get("history", []):
        state.history.append(
            StepEvent(
                step=WorkflowStep(ev_data.get("step", WorkflowStep.VALIDATE_TASK.value)),
                timestamp=ev_data.get("timestamp", 0.0),
                details=ev_data.get("details", {}),
                error=ev_data.get("error"),
            )
        )

    # Reconstruct tool calls
    for tc_data in data.get("tool_calls", []):
        state.tool_calls.append(
            ToolCallRecord(
                tool_name=tc_data.get("tool_name", ""),
                inputs=tc_data.get("inputs", {}),
                output=tc_data.get("output"),
                success=tc_data.get("success", True),
                error=tc_data.get("error"),
                timestamp=tc_data.get("timestamp", 0.0),
            )
        )

    return state
