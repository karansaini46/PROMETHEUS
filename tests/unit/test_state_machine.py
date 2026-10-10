"""Unit tests for PROMETHEUS state transitions."""

import pytest

from services.api.models import RunStatusEnum, TaskStatusEnum
from services.api.state_machine import (
    InvalidStateTransitionError,
    validate_run_transition,
    validate_task_transition,
)


@pytest.mark.unit
def test_valid_run_transitions() -> None:
    """Verify that legitimate run transitions succeed without error."""
    # PENDING -> RUNNING
    validate_run_transition(RunStatusEnum.PENDING, RunStatusEnum.RUNNING)
    # PENDING -> CANCELLED
    validate_run_transition(RunStatusEnum.PENDING, RunStatusEnum.CANCELLED)

    # RUNNING -> PAUSED
    validate_run_transition(RunStatusEnum.RUNNING, RunStatusEnum.PAUSED)
    # RUNNING -> VERIFYING
    validate_run_transition(RunStatusEnum.RUNNING, RunStatusEnum.VERIFYING)
    # RUNNING -> RESOLVED
    validate_run_transition(RunStatusEnum.RUNNING, RunStatusEnum.RESOLVED)
    # RUNNING -> FAILED
    validate_run_transition(RunStatusEnum.RUNNING, RunStatusEnum.FAILED)
    # RUNNING -> CANCELLED
    validate_run_transition(RunStatusEnum.RUNNING, RunStatusEnum.CANCELLED)

    # PAUSED -> RUNNING
    validate_run_transition(RunStatusEnum.PAUSED, RunStatusEnum.RUNNING)
    # VERIFYING -> RESOLVED
    validate_run_transition(RunStatusEnum.VERIFYING, RunStatusEnum.RESOLVED)


@pytest.mark.unit
def test_invalid_run_transitions_fail() -> None:
    """Verify that illegal run transitions raise InvalidStateTransitionError."""
    # Terminal states cannot transition to anything
    with pytest.raises(InvalidStateTransitionError, match="terminal state"):
        validate_run_transition(RunStatusEnum.RESOLVED, RunStatusEnum.RUNNING)

    with pytest.raises(InvalidStateTransitionError, match="terminal state"):
        validate_run_transition(RunStatusEnum.FAILED, RunStatusEnum.RUNNING)

    with pytest.raises(InvalidStateTransitionError, match="terminal state"):
        validate_run_transition(RunStatusEnum.CANCELLED, RunStatusEnum.RUNNING)

    with pytest.raises(InvalidStateTransitionError, match="terminal state"):
        validate_run_transition(RunStatusEnum.CANCELLED, RunStatusEnum.CANCELLED)

    # Cannot skip from PENDING straight to RESOLVED
    with pytest.raises(InvalidStateTransitionError):
        validate_run_transition(RunStatusEnum.PENDING, RunStatusEnum.RESOLVED)

    # Cannot skip from PENDING to VERIFYING
    with pytest.raises(InvalidStateTransitionError):
        validate_run_transition(RunStatusEnum.PENDING, RunStatusEnum.VERIFYING)


@pytest.mark.unit
def test_task_state_transitions() -> None:
    """Verify task lifecycle transitions and error cases."""
    # OPEN -> IN_PROGRESS
    validate_task_transition(TaskStatusEnum.OPEN, TaskStatusEnum.IN_PROGRESS)
    # IN_PROGRESS -> RESOLVED
    validate_task_transition(TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.RESOLVED)
    # RESOLVED -> CLOSED
    validate_task_transition(TaskStatusEnum.RESOLVED, TaskStatusEnum.CLOSED)

    # Illegal transition: OPEN directly to RESOLVED without IN_PROGRESS
    with pytest.raises(InvalidStateTransitionError):
        validate_task_transition(TaskStatusEnum.OPEN, TaskStatusEnum.RESOLVED)
