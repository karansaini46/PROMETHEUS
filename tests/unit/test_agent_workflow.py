"""Comprehensive deterministic tests for the PROMETHEUS autonomous debugging workflow."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from prometheus_ai.agents.checkpointer import (
    FileCheckpointer,
    MemoryCheckpointer,
)
from prometheus_ai.agents.state import (
    TaskSpec,
    WorkflowStatus,
    WorkflowStep,
)
from prometheus_ai.agents.workflow import DebuggingWorkflow
from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.execution.process_runner import ProcessSandboxRunner


def _create_buggy_repository(path: Path) -> None:
    """Helper to initialize a test git repository with a deliberately buggy function."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "GIT_AUTHOR_NAME": "Buggy Author",
        "GIT_AUTHOR_EMAIL": "buggy@example.com",
        "GIT_COMMITTER_NAME": "Buggy Committer",
        "GIT_COMMITTER_EMAIL": "buggy@example.com",
    }
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, env=env
    )

    # Buggy calculator: subtracts instead of adds
    code = (
        "def calculate_total(a: int, b: int) -> int:\n"
        "    # Deliberate defect: minus instead of plus\n"
        "    return a - b\n"
    )
    (path / "calculator.py").write_text(code)

    # Unit test that initially fails
    test_code = (
        "from calculator import calculate_total\n\n"
        "def test_calculate_total():\n"
        "    assert calculate_total(10, 5) == 15\n"
    )
    (path / "test_calculator.py").write_text(test_code)

    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Initial buggy commit"],
        cwd=path,
        check=True,
        capture_output=True,
        env=env,
    )


@pytest.mark.unit
async def test_complete_debugging_workflow_lifecycle() -> None:
    """Run a complete end-to-end debugging task against a deliberately buggy repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "buggy_repo"
        repo_dir.mkdir()
        _create_buggy_repository(repo_dir)

        git_mgr = GitManager(worktree_base_dir=base_dir / "worktrees")
        runner = ProcessSandboxRunner()
        checkpointer = MemoryCheckpointer()

        workflow = DebuggingWorkflow(
            git_manager=git_mgr,
            sandbox_runner=runner,
            checkpointer=checkpointer,
        )

        task = TaskSpec(
            task_id="TASK-BUG-001",
            issue_description="calculate_total returns 5 instead of 15 for inputs 10 and 5 in calculator.py",
            repo_path=str(repo_dir),
            test_runner="pytest",
            test_target="test_calculator.py",
        )

        state = workflow.create_run(task, run_id="run-bug-001")
        assert state.status == WorkflowStatus.PENDING
        assert state.current_step == WorkflowStep.VALIDATE_TASK

        # Fix patch that resolves the issue
        fix_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,3 @@
 def calculate_total(a: int, b: int) -> int:
-    # Deliberate defect: minus instead of plus
-    return a - b
+    # Deliberate defect: minus instead of plus
+    return a + b
"""

        # Execute workflow to completion
        final_state = await workflow.run_until_complete(state, custom_patch=fix_patch)

        # 1. State machine completion check
        assert final_state.status == WorkflowStatus.COMPLETED
        assert final_state.current_step == WorkflowStep.TERMINAL

        # 2. Verification of Role Outputs
        assert len(final_state.planner_output.hypotheses) > 0
        assert len(final_state.planner_output.investigation_plan) > 0
        assert "calculator.py" in final_state.investigator_output.candidate_files
        assert len(final_state.applied_patches) == 1

        # 3. Test analyst results
        assert final_state.test_analyst_output.exit_code == 0
        assert len(final_state.test_analyst_output.tests_passed) > 0
        assert len(final_state.test_analyst_output.tests_failed) == 0

        # 4. Final evidence-backed report
        report = final_state.final_report
        assert report is not None
        assert report.task_id == "TASK-BUG-001"
        assert report.is_resolved is True
        assert "calculator.py" in report.changes_actually_applied
        assert "calculator.py" in report.proposed_changes
        assert len(report.commands_actually_executed) >= 1
        assert report.requires_human_approval is True  # Non-negotiable human approval
        assert "RESOLVED" in report.summary

        # 5. Inspection of Execution Trace
        steps_traversed = [event.step for event in final_state.history]
        expected_sequence = [
            WorkflowStep.VALIDATE_TASK,
            WorkflowStep.INSPECT_REPO,
            WorkflowStep.SEARCH_CODE,
            WorkflowStep.HYPOTHESIZE,
            WorkflowStep.PLAN_INVESTIGATION,
            WorkflowStep.EXECUTE_INSPECTION,
            WorkflowStep.ANALYZE_EVIDENCE,
            WorkflowStep.PROPOSE_PATCH,
            WorkflowStep.APPLY_PATCH,
            WorkflowStep.RUN_TESTS,
            WorkflowStep.ANALYZE_TESTS,
            WorkflowStep.REVIEW_DIFF,
            WorkflowStep.GENERATE_REPORT,
        ]
        for step in expected_sequence:
            assert step in steps_traversed


@pytest.mark.unit
async def test_workflow_bounded_retry_and_exhaustion() -> None:
    """Ensure failed tests trigger bounded retry, and stop when budget is exhausted."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "buggy_repo"
        repo_dir.mkdir()
        _create_buggy_repository(repo_dir)

        git_mgr = GitManager(worktree_base_dir=base_dir / "worktrees")
        runner = ProcessSandboxRunner()

        workflow = DebuggingWorkflow(
            git_manager=git_mgr,
            sandbox_runner=runner,
        )

        # Task configured with max_retries = 2
        task = TaskSpec(
            task_id="TASK-RETRY-002",
            issue_description="calculate_total bug with retry limits",
            repo_path=str(repo_dir),
            test_runner="pytest",
            test_target="test_calculator.py",
            max_retries=2,
        )

        state = workflow.create_run(task, run_id="run-retry-002")

        # Ineffective patch (still fails test)
        ineffective_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,3 @@
 def calculate_total(a: int, b: int) -> int:
-    # Deliberate defect: minus instead of plus
-    return a - b
+    # Deliberate defect: minus instead of plus
+    return a - b + 0
"""
        final_state = await workflow.run_until_complete(state, custom_patch=ineffective_patch)

        assert final_state.status == WorkflowStatus.COMPLETED
        # Verified that retry count reached max_retries
        assert final_state.iteration == 2

        # Verification rule: bug is marked UNRESOLVED because tests failed
        assert final_state.final_report is not None
        assert final_state.final_report.is_resolved is False
        assert len(final_state.final_report.tests_failed) > 0


@pytest.mark.unit
async def test_workflow_cancellation() -> None:
    """Ensure requesting cancellation halts the workflow immediately."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "buggy_repo"
        repo_dir.mkdir()
        _create_buggy_repository(repo_dir)

        git_mgr = GitManager(worktree_base_dir=base_dir / "worktrees")
        runner = ProcessSandboxRunner()

        workflow = DebuggingWorkflow(
            git_manager=git_mgr,
            sandbox_runner=runner,
        )

        task = TaskSpec(
            task_id="TASK-CANCEL-003",
            issue_description="Test cancellation",
            repo_path=str(repo_dir),
        )

        state = workflow.create_run(task, run_id="run-cancel-003")

        # Advance one step
        state = await workflow.step(state)
        assert state.current_step == WorkflowStep.INSPECT_REPO

        # Request cancellation
        state.cancel_requested = True
        state = await workflow.step(state)

        assert state.status == WorkflowStatus.CANCELLED
        assert state.current_step == WorkflowStep.TERMINAL


@pytest.mark.unit
async def test_workflow_pause_and_resumption() -> None:
    """Ensure workflow can pause and resume from the persisted state."""
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        repo_dir = base_dir / "buggy_repo"
        repo_dir.mkdir()
        _create_buggy_repository(repo_dir)

        git_mgr = GitManager(worktree_base_dir=base_dir / "worktrees")
        runner = ProcessSandboxRunner()
        checkpointer = FileCheckpointer(storage_dir=base_dir / "checkpoints")

        workflow = DebuggingWorkflow(
            git_manager=git_mgr,
            sandbox_runner=runner,
            checkpointer=checkpointer,
        )

        task = TaskSpec(
            task_id="TASK-PAUSE-004",
            issue_description="calculate_total pause and resume test",
            repo_path=str(repo_dir),
            test_runner="pytest",
            test_target="test_calculator.py",
        )

        state = workflow.create_run(task, run_id="run-pause-004")

        # Advance a few steps
        state = await workflow.step(state)  # INSPECT_REPO
        state = await workflow.step(state)  # SEARCH_CODE

        # Pause workflow
        state.pause_requested = True
        state = await workflow.step(state)
        assert state.status == WorkflowStatus.PAUSED
        paused_step = state.current_step

        # Simulate reload from disk checkpointer
        restored_state = checkpointer.load("run-pause-004")
        assert restored_state is not None
        assert restored_state.status == WorkflowStatus.PAUSED
        assert restored_state.current_step == paused_step

        # Resume execution
        restored_state.pause_requested = False
        fix_patch = """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,3 +1,3 @@
 def calculate_total(a: int, b: int) -> int:
-    # Deliberate defect: minus instead of plus
-    return a - b
+    # Deliberate defect: minus instead of plus
+    return a + b
"""
        final_state = await workflow.run_until_complete(restored_state, custom_patch=fix_patch)
        assert final_state.status == WorkflowStatus.COMPLETED
        assert final_state.final_report is not None
        assert final_state.final_report.is_resolved is True


@pytest.mark.unit
async def test_workflow_task_validation_failure() -> None:
    """Ensure invalid task specifications transition cleanly to terminal failure."""
    git_mgr = GitManager()
    runner = ProcessSandboxRunner()
    workflow = DebuggingWorkflow(git_manager=git_mgr, sandbox_runner=runner)

    task = TaskSpec(
        task_id="TASK-FAIL-005",
        issue_description="Bad repo path",
        repo_path="/non/existent/path/on/system",
    )

    state = workflow.create_run(task)
    await workflow.step(state)

    assert state.status == WorkflowStatus.FAILED
    assert state.current_step == WorkflowStep.TERMINAL
    assert "does not exist" in str(state.error)
