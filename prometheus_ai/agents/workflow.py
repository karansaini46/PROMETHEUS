"""Stateful Graph-Based Autonomous Debugging Workflow Engine."""

import logging
import uuid
from pathlib import Path
from typing import Any

from prometheus_ai.agents.checkpointer import (
    BaseCheckpointer,
    MemoryCheckpointer,
)
from prometheus_ai.agents.roles import (
    ImplementerRole,
    InvestigatorRole,
    PlannerRole,
    ReviewerRole,
    TestAnalystRole,
)
from prometheus_ai.agents.state import (
    TaskSpec,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)
from prometheus_ai.execution.allowlist import ALLOWED_TEST_RUNNERS
from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.execution.sandbox import BaseSandboxRunner
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.tools.execution import RunAllowlistedTestsTool

logger = logging.getLogger(__name__)


class DebuggingWorkflow:
    """Stateful orchestrator executing the 13-step autonomous debugging lifecycle.

    Guarantees:
    - Durable state persistence and crash-resumption after every step.
    - Explicit state transitions with pause, cancellation, and retry boundaries.
    - Idempotency guards on patch application and command execution.
    - Non-automated external actions (always sets requires_human_approval=True).
    """

    def __init__(
        self,
        git_manager: GitManager,
        sandbox_runner: BaseSandboxRunner,
        model_provider: BaseModelProvider | None = None,
        checkpointer: BaseCheckpointer | None = None,
        memory_manager: Any | None = None,
    ) -> None:
        self.git_manager = git_manager
        self.sandbox_runner = sandbox_runner
        self.model_provider = model_provider
        self.checkpointer = checkpointer or MemoryCheckpointer()
        self.memory_manager = memory_manager

        # Initialize specialized roles
        self.planner = PlannerRole(model_provider=model_provider)
        self.investigator = InvestigatorRole(git_manager=git_manager)
        self.implementer = ImplementerRole(model_provider=model_provider)
        self.test_tool = RunAllowlistedTestsTool(runner=sandbox_runner)
        self.test_analyst = TestAnalystRole(test_tool=self.test_tool)
        self.reviewer = ReviewerRole(git_manager=git_manager)

    def create_run(self, task: TaskSpec, run_id: str | None = None) -> WorkflowState:
        """Initialize a new workflow instance and save initial checkpoint."""
        active_run_id = run_id or f"run-{uuid.uuid4().hex[:10]}"
        state = WorkflowState(
            run_id=active_run_id,
            task=task,
            status=WorkflowStatus.PENDING,
            current_step=WorkflowStep.VALIDATE_TASK,
        )
        self.checkpointer.save(state)
        return state

    async def step(
        self,
        state: WorkflowState,
        custom_patch: str | None = None,
    ) -> WorkflowState:
        """Execute exactly one step in the state machine and persist checkpoint."""
        if state.cancel_requested:
            state.status = WorkflowStatus.CANCELLED
            state.current_step = WorkflowStep.TERMINAL
            state.record_event(WorkflowStep.TERMINAL, {"reason": "Cancelled by user request"})
            self.checkpointer.save(state)
            return state

        if state.pause_requested:
            state.status = WorkflowStatus.PAUSED
            state.record_event(state.current_step, {"reason": "Workflow paused"})
            self.checkpointer.save(state)
            return state

        state.status = WorkflowStatus.RUNNING

        try:
            match state.current_step:
                case WorkflowStep.VALIDATE_TASK:
                    await self._step_validate_task(state)
                case WorkflowStep.INSPECT_REPO:
                    await self._step_inspect_repo(state)
                case WorkflowStep.SEARCH_CODE:
                    await self._step_search_code(state)
                case WorkflowStep.HYPOTHESIZE:
                    await self._step_hypothesize(state)
                case WorkflowStep.PLAN_INVESTIGATION:
                    await self._step_plan_investigation(state)
                case WorkflowStep.EXECUTE_INSPECTION:
                    await self._step_execute_inspection(state)
                case WorkflowStep.ANALYZE_EVIDENCE:
                    await self._step_analyze_evidence(state)
                case WorkflowStep.PROPOSE_PATCH:
                    await self._step_propose_patch(state, custom_patch=custom_patch)
                case WorkflowStep.APPLY_PATCH:
                    await self._step_apply_patch(state)
                case WorkflowStep.RUN_TESTS:
                    await self._step_run_tests(state)
                case WorkflowStep.ANALYZE_TESTS:
                    await self._step_analyze_tests(state)
                case WorkflowStep.REVIEW_DIFF:
                    await self._step_review_diff(state)
                case WorkflowStep.GENERATE_REPORT:
                    await self._step_generate_report(state)
                case WorkflowStep.TERMINAL:
                    state.status = WorkflowStatus.COMPLETED

        except Exception as err:
            logger.exception("Workflow step failed: %s", err)
            state.status = WorkflowStatus.FAILED
            state.error = str(err)
            state.current_step = WorkflowStep.TERMINAL
            state.record_event(state.current_step, {"error": str(err)}, error=str(err))

        self.checkpointer.save(state)
        return state

    async def run_until_complete(
        self,
        state: WorkflowState,
        custom_patch: str | None = None,
        max_steps: int = 40,
    ) -> WorkflowState:
        """Run the workflow sequentially until reaching a terminal state or pause."""
        steps_taken = 0
        while (
            (
                state.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING)
                or (state.status == WorkflowStatus.PAUSED and not state.pause_requested)
            )
            and state.current_step != WorkflowStep.TERMINAL
            and steps_taken < max_steps
        ):
            await self.step(state, custom_patch=custom_patch)
            steps_taken += 1

        if steps_taken >= max_steps and state.current_step != WorkflowStep.TERMINAL:
            state.status = WorkflowStatus.FAILED
            state.error = f"Workflow exceeded maximum step threshold ({max_steps})"
            self.checkpointer.save(state)

        return state

    # --- Step Implementations ---

    async def _step_validate_task(self, state: WorkflowState) -> None:
        """Step 1: Validate incoming task."""
        repo = Path(state.task.repo_path)
        if not repo.exists() or not repo.is_dir():
            raise FileNotFoundError(f"Target repository path does not exist: {repo}")

        base_runner = state.task.test_runner.split()[0]
        if base_runner not in ALLOWED_TEST_RUNNERS:
            raise ValueError(
                f"Test runner '{base_runner}' is not permitted in allowlist: {sorted(ALLOWED_TEST_RUNNERS)}"
            )

        state.record_event(WorkflowStep.VALIDATE_TASK, {"validated": True})
        state.current_step = WorkflowStep.INSPECT_REPO

    async def _step_inspect_repo(self, state: WorkflowState) -> None:
        """Step 2: Inspect registered repository."""
        meta = self.git_manager.register_repository(state.task.repo_path)
        files = self.git_manager.list_permitted_files(state.task.repo_path)
        state.metadata["repo_files"] = files
        state.metadata["default_branch"] = meta.default_branch

        if self.memory_manager:
            try:
                project_id = state.metadata.get("project_id") or getattr(
                    state.task, "project_id", None
                )
                memories = await self.memory_manager.retrieve(
                    query=state.task.issue_description,
                    project_id=project_id,
                    limit=5,
                )
                state.metadata["retrieved_memories"] = [m.model_dump() for m in memories]
            except Exception as mem_err:
                logger.warning("Memory retrieval skipped: %s", mem_err)

        state.record_event(
            WorkflowStep.INSPECT_REPO,
            {
                "files_count": len(files),
                "branch": meta.default_branch,
                "retrieved_memories_count": len(state.metadata.get("retrieved_memories", [])),
            },
        )
        state.current_step = WorkflowStep.SEARCH_CODE

    async def _step_search_code(self, state: WorkflowState) -> None:
        """Step 3: Search for relevant code."""
        keywords = state.task.issue_description.split()[:3]
        search_query = keywords[0] if keywords else ""
        hits = self.git_manager.search_source_code(
            repo_or_worktree_path=state.task.repo_path,
            query=search_query,
            max_results=20,
        )
        state.metadata["search_hits"] = hits
        state.record_event(
            WorkflowStep.SEARCH_CODE, {"query": search_query, "hits_count": len(hits)}
        )
        state.current_step = WorkflowStep.HYPOTHESIZE

    async def _step_hypothesize(self, state: WorkflowState) -> None:
        """Step 4: Produce investigation hypotheses (Planner)."""
        repo_files = state.metadata.get("repo_files", [])
        search_hits = state.metadata.get("search_hits", [])

        planner_out = await self.planner.execute(
            task=state.task,
            repo_files=repo_files,
            search_hits=search_hits,
        )
        state.planner_output = planner_out
        state.record_event(
            WorkflowStep.HYPOTHESIZE,
            {"hypotheses_count": len(planner_out.hypotheses)},
        )
        state.current_step = WorkflowStep.PLAN_INVESTIGATION

    async def _step_plan_investigation(self, state: WorkflowState) -> None:
        """Step 5: Build a bounded investigation plan (Planner)."""
        state.record_event(
            WorkflowStep.PLAN_INVESTIGATION,
            {"plan": state.planner_output.investigation_plan},
        )
        state.current_step = WorkflowStep.EXECUTE_INSPECTION

    async def _step_execute_inspection(self, state: WorkflowState) -> None:
        """Step 6: Execute permitted inspection tools (Investigator)."""
        investigator_out = await self.investigator.execute(
            task=state.task,
            planner_output=state.planner_output,
            repo_path=state.task.repo_path,
        )
        state.investigator_output = investigator_out
        state.record_event(
            WorkflowStep.EXECUTE_INSPECTION,
            {"inspected_files": list(investigator_out.evidence_collected.keys())},
        )
        state.current_step = WorkflowStep.ANALYZE_EVIDENCE

    async def _step_analyze_evidence(self, state: WorkflowState) -> None:
        """Step 7: Analyze the resulting evidence (Investigator)."""
        state.record_event(
            WorkflowStep.ANALYZE_EVIDENCE,
            {"root_cause": state.investigator_output.root_cause_analysis},
        )
        state.current_step = WorkflowStep.PROPOSE_PATCH

    async def _step_propose_patch(
        self,
        state: WorkflowState,
        custom_patch: str | None = None,
    ) -> None:
        """Step 8: Propose a patch (Implementer)."""
        implementer_out = await self.implementer.execute(
            task=state.task,
            investigator_output=state.investigator_output,
            prior_failures=(
                [state.test_analyst_output.failure_diagnostics]
                if state.test_analyst_output.failure_diagnostics
                else None
            ),
            custom_patch=custom_patch,
        )
        state.implementer_output = implementer_out
        state.record_event(
            WorkflowStep.PROPOSE_PATCH,
            {"patch_length": len(implementer_out.patch_diff)},
        )
        state.current_step = WorkflowStep.APPLY_PATCH

    async def _step_apply_patch(self, state: WorkflowState) -> None:
        """Step 9: Apply the patch in an isolated worktree."""
        # Non-idempotent guard: Ensure an isolated worktree exists
        if not state.worktree_path or not Path(state.worktree_path).exists():
            wt_meta = self.git_manager.create_worktree(state.task.repo_path)
            state.worktree_path = wt_meta.worktree_path

        patch_content = state.implementer_output.patch_diff
        if patch_content and patch_content not in state.applied_patches:
            patch_res = self.git_manager.apply_patch(state.worktree_path, patch_content)
            if not patch_res.success:
                state.record_event(
                    WorkflowStep.APPLY_PATCH,
                    {"error": patch_res.error_message},
                    error=patch_res.error_message,
                )
            else:
                state.applied_patches.append(patch_content)
                state.record_event(
                    WorkflowStep.APPLY_PATCH,
                    {"applied_files": patch_res.applied_files},
                )
        else:
            state.record_event(
                WorkflowStep.APPLY_PATCH,
                {"notice": "No new patch or patch already applied"},
            )

        state.current_step = WorkflowStep.RUN_TESTS

    async def _step_run_tests(self, state: WorkflowState) -> None:
        """Step 10: Run relevant tests in the isolated sandbox (Test Analyst)."""
        if not state.worktree_path:
            raise RuntimeError("Cannot execute tests: worktree has not been provisioned")

        executed_cmd = f"{state.task.test_runner} {state.task.test_target or ''}".strip()
        state.executed_commands.append(executed_cmd)

        test_out = await self.test_analyst.execute(
            task=state.task,
            worktree_path=state.worktree_path,
            iteration=state.iteration,
        )
        state.test_analyst_output = test_out
        state.record_event(
            WorkflowStep.RUN_TESTS,
            {
                "exit_code": test_out.exit_code,
                "passed": test_out.tests_passed,
                "failed": test_out.tests_failed,
            },
        )
        state.current_step = WorkflowStep.ANALYZE_TESTS

    async def _step_analyze_tests(self, state: WorkflowState) -> None:
        """Step 11: Analyze failures and optionally retry."""
        test_out = state.test_analyst_output
        if test_out.should_retry and state.iteration < state.task.max_retries:
            state.iteration += 1
            state.record_event(
                WorkflowStep.ANALYZE_TESTS,
                {
                    "decision": "retry",
                    "iteration": state.iteration,
                    "max_retries": state.task.max_retries,
                },
            )
            # Route back to patch synthesis with diagnostics
            state.current_step = WorkflowStep.PROPOSE_PATCH
        else:
            state.record_event(
                WorkflowStep.ANALYZE_TESTS,
                {"decision": "proceed_to_review", "exit_code": test_out.exit_code},
            )
            state.current_step = WorkflowStep.REVIEW_DIFF

    async def _step_review_diff(self, state: WorkflowState) -> None:
        """Step 12: Review the diff in the worktree (Reviewer)."""
        diff_res = self.git_manager.inspect_git_diff(state.worktree_path or state.task.repo_path)
        state.record_event(
            WorkflowStep.REVIEW_DIFF,
            {"files_changed": diff_res.files_changed, "diff_bytes": len(diff_res.diff)},
        )
        state.current_step = WorkflowStep.GENERATE_REPORT

    async def _step_generate_report(self, state: WorkflowState) -> None:
        """Step 13: Produce a final evidence-backed report (Reviewer)."""
        report = await self.reviewer.execute(
            task=state.task,
            worktree_path=state.worktree_path,
            planner_output=state.planner_output,
            investigator_output=state.investigator_output,
            implementer_output=state.implementer_output,
            test_analyst_output=state.test_analyst_output,
            executed_commands=state.executed_commands,
            applied_patches=state.applied_patches,
        )
        state.final_report = report
        state.status = WorkflowStatus.COMPLETED
        state.current_step = WorkflowStep.TERMINAL

        if self.memory_manager:
            try:
                from prometheus_ai.memory.schema import (
                    MemoryRecordCreate,
                    MemoryType,
                    VerificationStatus,
                )

                project_id = state.metadata.get("project_id") or getattr(
                    state.task, "project_id", None
                )
                if report.is_resolved:
                    await self.memory_manager.store(
                        MemoryRecordCreate(
                            memory_type=MemoryType.EPISODIC,
                            key=f"resolution_{state.task.task_id}",
                            content=f"Resolved issue: {state.task.issue_description}\nSummary: {report.summary}",
                            project_id=project_id,
                            task_id=state.task.task_id,
                            run_id=state.run_id,
                            repo_path=state.task.repo_path,
                            evidence=[
                                f"applied_patches={len(state.applied_patches)}",
                                report.summary,
                            ],
                            confidence=0.95,
                            verification_status=VerificationStatus.VERIFIED,
                            is_hypothesis=False,
                        )
                    )
                else:
                    await self.memory_manager.store(
                        MemoryRecordCreate(
                            memory_type=MemoryType.EPISODIC,
                            key=f"failed_attempt_{state.task.task_id}",
                            content=f"Failed attempt for issue: {state.task.issue_description}\nDiagnostic: {report.summary}",
                            project_id=project_id,
                            task_id=state.task.task_id,
                            run_id=state.run_id,
                            repo_path=state.task.repo_path,
                            evidence=[report.summary],
                            confidence=0.7,
                            verification_status=VerificationStatus.OBSERVED,
                            is_hypothesis=False,
                        )
                    )
            except Exception as mem_err:
                logger.warning("Failed to store episodic memory: %s", mem_err)

        state.record_event(
            WorkflowStep.GENERATE_REPORT,
            {"is_resolved": report.is_resolved, "summary": report.summary},
        )
