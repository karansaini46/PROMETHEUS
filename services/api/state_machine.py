"""PROMETHEUS Explicit State Machine & Transition Rules.

Enforces deterministic state transitions for execution runs and tasks.
Invalid transitions immediately fail with explicit errors.
"""

from typing import Any

from services.api.models import RunStatusEnum, TaskStatusEnum
from services.api.telemetry import trace_span


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""

    def __init__(
        self,
        current_status: str,
        target_status: str,
        entity_name: str = "ExecutionRun",
        allowed_transitions: set[str] | None = None,
    ) -> None:
        self.current_status = current_status
        self.target_status = target_status
        self.entity_name = entity_name
        self.allowed_transitions = sorted(allowed_transitions or [])
        allowed_str = (
            ", ".join(f"'{t}'" for t in self.allowed_transitions)
            if self.allowed_transitions
            else "none (terminal state)"
        )
        super().__init__(
            f"Invalid {entity_name} state transition from '{current_status}' to '{target_status}'. "
            f"Allowed transitions from '{current_status}': [{allowed_str}]."
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize error details for API responses."""
        return {
            "error": "InvalidStateTransition",
            "message": str(self),
            "entity": self.entity_name,
            "current_status": self.current_status,
            "target_status": self.target_status,
            "allowed_transitions": self.allowed_transitions,
        }


# ==============================================================================
# Execution Run State Machine
# ==============================================================================

RUN_TRANSITIONS: dict[RunStatusEnum, set[RunStatusEnum]] = {
    RunStatusEnum.PENDING: {RunStatusEnum.RUNNING, RunStatusEnum.CANCELLED},
    RunStatusEnum.RUNNING: {
        RunStatusEnum.PAUSED,
        RunStatusEnum.VERIFYING,
        RunStatusEnum.RESOLVED,
        RunStatusEnum.FAILED,
        RunStatusEnum.CANCELLED,
    },
    RunStatusEnum.PAUSED: {RunStatusEnum.RUNNING, RunStatusEnum.CANCELLED},
    RunStatusEnum.VERIFYING: {
        RunStatusEnum.RESOLVED,
        RunStatusEnum.FAILED,
        RunStatusEnum.CANCELLED,
    },
    # Terminal states
    RunStatusEnum.RESOLVED: set(),
    RunStatusEnum.FAILED: set(),
    RunStatusEnum.CANCELLED: set(),
}


def validate_run_transition(
    current_status: RunStatusEnum | str, target_status: RunStatusEnum | str
) -> None:
    """Validate that transition from current_status to target_status is permitted.

    Raises:
        InvalidStateTransitionError: If the transition is illegal.
    """
    with trace_span(
        "state_machine.run_transition",
        attributes={
            "transition.from": str(current_status),
            "transition.to": str(target_status),
            "entity": "ExecutionRun",
        },
    ):
        try:
            curr = (
                current_status
                if isinstance(current_status, RunStatusEnum)
                else RunStatusEnum(current_status)
            )
        except ValueError as err:
            raise ValueError(f"Unknown current Run status: '{current_status}'") from err

        try:
            target = (
                target_status
                if isinstance(target_status, RunStatusEnum)
                else RunStatusEnum(target_status)
            )
        except ValueError as err:
            raise ValueError(f"Unknown target Run status: '{target_status}'") from err

        # Terminal states cannot transition to any state, including themselves
        terminal_states = {RunStatusEnum.RESOLVED, RunStatusEnum.FAILED, RunStatusEnum.CANCELLED}
        if curr in terminal_states:
            raise InvalidStateTransitionError(
                current_status=curr.value,
                target_status=target.value,
                entity_name="ExecutionRun",
                allowed_transitions=set(),
            )

        # Non-terminal idempotent same-state check
        if curr == target:
            return

        allowed = RUN_TRANSITIONS.get(curr, set())
        if target not in allowed:
            raise InvalidStateTransitionError(
                current_status=curr.value,
                target_status=target.value,
                entity_name="ExecutionRun",
                allowed_transitions={t.value for t in allowed},
            )


# ==============================================================================
# Task State Machine
# ==============================================================================

TASK_TRANSITIONS: dict[TaskStatusEnum, set[TaskStatusEnum]] = {
    TaskStatusEnum.OPEN: {TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.CANCELLED},
    TaskStatusEnum.IN_PROGRESS: {
        TaskStatusEnum.RESOLVED,
        TaskStatusEnum.CLOSED,
        TaskStatusEnum.CANCELLED,
        TaskStatusEnum.OPEN,
    },
    TaskStatusEnum.RESOLVED: {TaskStatusEnum.CLOSED, TaskStatusEnum.IN_PROGRESS},
    TaskStatusEnum.CLOSED: {TaskStatusEnum.OPEN},
    TaskStatusEnum.CANCELLED: {TaskStatusEnum.OPEN},
}


def validate_task_transition(
    current_status: TaskStatusEnum | str, target_status: TaskStatusEnum | str
) -> None:
    """Validate task lifecycle state transitions."""
    with trace_span(
        "state_machine.task_transition",
        attributes={
            "transition.from": str(current_status),
            "transition.to": str(target_status),
            "entity": "Task",
        },
    ):
        try:
            curr = (
                current_status
                if isinstance(current_status, TaskStatusEnum)
                else TaskStatusEnum(current_status)
            )
        except ValueError as err:
            raise ValueError(f"Unknown current Task status: '{current_status}'") from err

        try:
            target = (
                target_status
                if isinstance(target_status, TaskStatusEnum)
                else TaskStatusEnum(target_status)
            )
        except ValueError as err:
            raise ValueError(f"Unknown target Task status: '{target_status}'") from err

        if curr == target:
            return

        allowed = TASK_TRANSITIONS.get(curr, set())
        if target not in allowed:
            raise InvalidStateTransitionError(
                current_status=curr.value,
                target_status=target.value,
                entity_name="Task",
                allowed_transitions={t.value for t in allowed},
            )
