"""Specialized Agent Roles for Autonomous Software Debugging.

Each role has a defined input schema, output schema, and distinct responsibility:
- Planner: Hypothesis generation and bounded investigation planning.
- Investigator: Code inspection and evidence-backed root cause analysis.
- Implementer: Minimal patch synthesis and worktree application.
- Test Analyst: Test execution in isolated sandbox and failure diagnostics.
- Reviewer: Independent diff audit, evidence synthesis, and final reporting.
"""

import logging
import re
from pathlib import Path
from typing import Any

from prometheus_ai.agents.state import (
    FinalReport,
    ImplementerOutput,
    InvestigatorOutput,
    PlannerOutput,
    TaskSpec,
    TestAnalystOutput,
)
from prometheus_ai.execution.git_manager import GitManager
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.tools.execution import RunAllowlistedTestsTool

logger = logging.getLogger(__name__)


class PlannerRole:
    """Planner: Formulates testable hypotheses and bounded investigation plans."""

    def __init__(self, model_provider: BaseModelProvider | None = None) -> None:
        self.model_provider = model_provider

    async def execute(
        self,
        task: TaskSpec,
        repo_files: list[str],
        search_hits: list[dict[str, Any]],
    ) -> PlannerOutput:
        """Analyze issue and search results to produce hypotheses and plan."""
        # 1. Identify candidate files from issue keywords and search hits
        candidate_files: list[str] = []
        for hit in search_hits:
            f = hit.get("file")
            if f and f in repo_files and f not in candidate_files:
                candidate_files.append(f)

        # Keyword matching against permitted repo files
        keywords = re.findall(r"[a-zA-Z_0-9]+", task.issue_description.lower())
        for rf in repo_files:
            rf_lower = rf.lower()
            if any(kw in rf_lower for kw in keywords if len(kw) > 3) and rf not in candidate_files:
                candidate_files.append(rf)

        # Cap target files to prevent unbounded investigation
        target_files = candidate_files[:5] if candidate_files else repo_files[:3]

        # 2. Formulate hypotheses
        hypotheses = [
            f"Defect is located in '{target_files[0]}': logic contradicts requirement in '{task.issue_description[:60]}...'"
        ]
        if len(target_files) > 1:
            hypotheses.append(f"Secondary defect or dependency interaction in '{target_files[1]}'")

        # 3. Formulate bounded investigation plan
        investigation_plan = [
            f"Read and inspect target file: '{f}' (lines 1 to 100)" for f in target_files
        ]

        return PlannerOutput(
            hypotheses=hypotheses,
            investigation_plan=investigation_plan,
            target_files=target_files,
        )


class InvestigatorRole:
    """Investigator: Gathers concrete code evidence and pinpoints root causes."""

    def __init__(self, git_manager: GitManager) -> None:
        self.git_manager = git_manager

    async def execute(
        self,
        task: TaskSpec,
        planner_output: PlannerOutput,
        repo_path: str,
    ) -> InvestigatorOutput:
        """Inspect target files and formulate evidence-backed root cause analysis."""
        evidence_collected: dict[str, Any] = {}
        analyzed_files: list[str] = []

        for target_file in planner_output.target_files:
            try:
                file_data = self.git_manager.read_bounded_file(
                    repo_or_worktree_path=repo_path,
                    file_path=target_file,
                    start_line=1,
                    end_line=150,
                    max_bytes=50000,
                )
                evidence_collected[target_file] = {
                    "content": file_data["content"],
                    "total_lines": file_data["total_lines"],
                }
                analyzed_files.append(target_file)
            except Exception as err:
                evidence_collected[target_file] = {"error": str(err)}

        root_cause = (
            f"Identified discrepant logic in {analyzed_files[0] if analyzed_files else 'target files'} "
            f"inconsistent with issue description: {task.issue_description}"
        )

        return InvestigatorOutput(
            evidence_collected=evidence_collected,
            root_cause_analysis=root_cause,
            candidate_files=analyzed_files,
        )


class ImplementerRole:
    """Implementer: Synthesizes minimal code patches to resolve root causes."""

    def __init__(self, model_provider: BaseModelProvider | None = None) -> None:
        self.model_provider = model_provider

    async def execute(
        self,
        task: TaskSpec,
        investigator_output: InvestigatorOutput,
        prior_failures: list[str] | None = None,
        custom_patch: str | None = None,
    ) -> ImplementerOutput:
        """Draft a unified diff patch addressing the investigated root cause."""
        # If a custom patch is provided (e.g. from tests or model)
        if custom_patch:
            files_modified = []
            for line in custom_patch.splitlines():
                if line.startswith("+++ b/"):
                    files_modified.append(line[6:].strip())
            return ImplementerOutput(
                patch_diff=custom_patch,
                explanation="Patch synthesized based on localized bug fix.",
                files_modified=files_modified,
            )

        # If LLM model provider is configured, request structured patch
        if self.model_provider:
            try:
                prompt = (
                    f"Issue: {task.issue_description}\n"
                    f"Root Cause: {investigator_output.root_cause_analysis}\n"
                    f"Candidate Files: {investigator_output.candidate_files}\n"
                    "Generate a standard unified diff patch (starting with diff --git) to fix this issue."
                )
                resp = await self.model_provider.generate(prompt)
                patch_text = resp.content.strip()
                files_mod = []
                for line in patch_text.splitlines():
                    if line.startswith("+++ b/"):
                        files_mod.append(line[6:].strip())
                return ImplementerOutput(
                    patch_diff=patch_text,
                    explanation="Synthesized by model provider.",
                    files_modified=files_mod,
                )
            except Exception as err:
                logger.warning("Model patch synthesis failed: %s", err)

        # Fallback minimal placeholder patch if candidate files exist
        target = (
            investigator_output.candidate_files[0]
            if investigator_output.candidate_files
            else "unknown.py"
        )
        return ImplementerOutput(
            patch_diff="",
            explanation=f"No automatic patch generated for {target}.",
            files_modified=[],
        )


class TestAnalystRole:
    """Test Analyst: Executes allowlisted tests inside the sandbox and analyzes outcomes."""

    def __init__(self, test_tool: RunAllowlistedTestsTool) -> None:
        self.test_tool = test_tool

    async def execute(
        self,
        task: TaskSpec,
        worktree_path: str,
        iteration: int,
    ) -> TestAnalystOutput:
        """Run allowlisted test suite in the isolated sandbox and parse results."""
        # ponytail: Simple regex parsing for pytest/unittest stdout captures pass/fail status
        # with zero external test-runner plugins.
        res = await self.test_tool.execute(
            worktree_path=worktree_path,
            test_runner=task.test_runner,
            test_target=task.test_target,
            extra_args=task.extra_args,
        )

        exit_code = int(res.get("exit_code", -1))
        stdout = str(res.get("stdout", ""))
        stderr = str(res.get("stderr", ""))
        duration = float(res.get("duration_seconds", 0.0))

        tests_passed: list[str] = []
        tests_failed: list[str] = []
        tests_not_run: list[str] = []

        combined_out = stdout + "\n" + stderr

        # Parse test outcomes
        for line in combined_out.splitlines():
            line_str = line.strip()
            if "PASSED" in line_str:
                tests_passed.append(line_str)
            elif "FAILED" in line_str or "ERROR" in line_str:
                tests_failed.append(line_str)

        # Fallback if no individual test lines parsed
        if not tests_passed and not tests_failed:
            target_desc = task.test_target or "test suite"
            if exit_code == 0:
                tests_passed.append(f"{target_desc} (all passed)")
            else:
                tests_failed.append(f"{target_desc} (failed with exit code {exit_code})")

        should_retry = (exit_code != 0) and (iteration < task.max_retries)
        diagnostics = stderr if stderr.strip() else stdout[-500:]

        return TestAnalystOutput(
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_not_run=tests_not_run,
            should_retry=should_retry,
            failure_diagnostics=diagnostics if exit_code != 0 else None,
            exit_code=exit_code,
            duration_seconds=duration,
        )


class ReviewerRole:
    """Reviewer: Independent diff review, evidence synthesis, and final report generation."""

    def __init__(self, git_manager: GitManager) -> None:
        self.git_manager = git_manager

    async def execute(
        self,
        task: TaskSpec,
        worktree_path: str | None,
        planner_output: PlannerOutput,
        investigator_output: InvestigatorOutput,
        implementer_output: ImplementerOutput,
        test_analyst_output: TestAnalystOutput,
        executed_commands: list[str],
        applied_patches: list[str],
    ) -> FinalReport:
        """Conduct independent diff audit and compile the final evidence-backed report."""
        changes_actually_applied: list[str] = []
        if worktree_path and Path(worktree_path).exists():
            try:
                diff_res = self.git_manager.inspect_git_diff(worktree_path)
                changes_actually_applied = diff_res.files_changed
            except Exception as err:
                logger.warning("Error inspecting worktree diff: %s", err)

        proposed_changes = list(implementer_output.files_modified)

        # STRICT VERIFICATION RULE:
        # Never claim a bug is fixed merely because the model says so.
        # Only resolved if allowlisted tests actually executed and passed.
        is_resolved = (
            test_analyst_output.exit_code == 0
            and len(test_analyst_output.tests_passed) > 0
            and len(test_analyst_output.tests_failed) == 0
            and len(changes_actually_applied) > 0
        )

        uncertainties: list[str] = []
        if not is_resolved:
            uncertainties.append(
                "Fix verification incomplete: test suite failed or no changes were applied."
            )
        if not test_analyst_output.tests_passed:
            uncertainties.append("No positive test assertion records were confirmed.")

        summary_status = "RESOLVED" if is_resolved else "UNRESOLVED"
        summary = (
            f"Debugging Task {task.task_id}: {summary_status}. "
            f"Modified files: {changes_actually_applied}. "
            f"Passed tests: {len(test_analyst_output.tests_passed)}, "
            f"Failed tests: {len(test_analyst_output.tests_failed)}. "
            f"Requires explicit human review before merging."
        )

        return FinalReport(
            task_id=task.task_id,
            proposed_changes=proposed_changes,
            changes_actually_applied=changes_actually_applied,
            commands_actually_executed=list(executed_commands),
            tests_passed=test_analyst_output.tests_passed,
            tests_failed=test_analyst_output.tests_failed,
            tests_not_run=test_analyst_output.tests_not_run,
            findings_remain_uncertain=uncertainties,
            is_resolved=is_resolved,
            requires_human_approval=True,  # Invariant: human approval always required
            summary=summary,
        )
