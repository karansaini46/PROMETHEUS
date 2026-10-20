"""Evaluation, Leakage Prevention, and Comparative Experiment Runner.

Guarantees:
- Strict zero-leakage verification between Training, Tuning, and Held-Out tasks.
- Multi-baseline comparison:
    1. Fixed Rule-Based strategy (Baseline 1)
    2. LLM-Selected strategy (Baseline 2)
    3. Experience-Informed / Bandit strategy (Experimental)
- Tracks success rate, regression rate, tool-call efficiency, cost, and latency.
- Generates an ExperimentReport with explicit conclusion:
    IMPROVED, DEGRADED, or INCONCLUSIVE.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from prometheus_ai.learning.strategy.collector import TraceCollector
from prometheus_ai.learning.strategy.governance import (
    BudgetConfig,
    BudgetEnforcer,
    PolicyRegistry,
    SafePolicyExecutor,
)
from prometheus_ai.learning.strategy.policy import (
    BaseToolSelectionPolicy,
    LLMToolPolicy,
    RuleBasedToolPolicy,
)
from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
    ToolSelectionContext,
)

logger = logging.getLogger(__name__)


class DataLeakageError(Exception):
    """Raised when data contamination occurs between training/tuning and held-out evaluation tasks."""


class ExperimentConclusion(StrEnum):
    """Rigorous evaluation outcome classification."""

    IMPROVED = "improved"
    DEGRADED = "degraded"
    INCONCLUSIVE = "inconclusive"


@dataclass
class EvaluationTask:
    """Task specification for policy benchmark evaluation."""

    task_id: str
    task_category: TaskCategory
    issue_description: str
    target_files: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)
    optimal_tools: list[str] = field(default_factory=list)
    difficulty: str = "medium"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Cryptographic SHA-256 fingerprint of the task definition."""
        content = f"{self.task_category.value}:{self.issue_description}:{'|'.join(sorted(self.target_files))}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class TaskRunResult:
    """Result of running a single evaluation task with a policy."""

    task_id: str
    resolved: bool
    tool_sequence: list[str]
    uninformative_calls: int
    cost_usd: float
    latency_seconds: float
    traces: list[ExecutionTrace]


@dataclass
class PolicyEvaluationMetrics:
    """Aggregated evaluation metrics for a single policy over a task split."""

    policy_id: str
    policy_type: str
    total_tasks: int
    resolved_tasks: int
    success_rate: float
    regressions: int
    regression_rate: float
    avg_tool_calls_per_resolved: float
    avg_uninformative_ratio: float
    total_cost_usd: float
    avg_cost_usd: float
    avg_latency_seconds: float
    task_results: list[TaskRunResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("task_results", None)
        return data


@dataclass
class ExperimentReport:
    """Comprehensive comparative evaluation report across baselines and experimental policies."""

    timestamp: float
    training_task_count: int
    tuning_task_count: int
    held_out_task_count: int
    trials_per_task: int
    baseline_rule_metrics: PolicyEvaluationMetrics
    baseline_llm_metrics: PolicyEvaluationMetrics
    experimental_metrics: PolicyEvaluationMetrics
    delta_success_rate: float
    delta_efficiency: float  # Difference in average tool calls (negative = saved tool calls)
    delta_cost_usd: float
    delta_latency_seconds: float
    generalizes_to_held_out: bool
    leakage_free_verified: bool
    conclusion: ExperimentConclusion
    summary_text: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["conclusion"] = self.conclusion.value
        data["baseline_rule_metrics"] = self.baseline_rule_metrics.to_dict()
        data["baseline_llm_metrics"] = self.baseline_llm_metrics.to_dict()
        data["experimental_metrics"] = self.experimental_metrics.to_dict()
        return data


class DatasetSplitter:
    """Splits evaluation tasks into Training, Tuning, and Held-Out sets with zero-leakage guarantee."""

    @staticmethod
    def partition_and_verify(
        tasks: list[EvaluationTask],
        train_ratio: float = 0.5,
        tuning_ratio: float = 0.25,
    ) -> tuple[list[EvaluationTask], list[EvaluationTask], list[EvaluationTask]]:
        """Partition tasks into strictly disjoint train, tuning, and held-out subsets."""
        if not tasks:
            return [], [], []

        n = len(tasks)
        n_train = max(1, int(n * train_ratio))
        n_tuning = max(1, int(n * tuning_ratio)) if n > 2 else 0

        train_tasks = tasks[:n_train]
        tuning_tasks = tasks[n_train : n_train + n_tuning]
        held_out_tasks = tasks[n_train + n_tuning :]

        if not held_out_tasks and len(tasks) >= 3:
            held_out_tasks = [tasks[-1]]
            if tuning_tasks:
                tuning_tasks = tuning_tasks[:-1]

        # Audit 1: ID Disjointness
        train_ids = {t.task_id for t in train_tasks}
        tuning_ids = {t.task_id for t in tuning_tasks}
        held_out_ids = {t.task_id for t in held_out_tasks}

        leakage_ids = (train_ids | tuning_ids) & held_out_ids
        if leakage_ids:
            raise DataLeakageError(
                f"Data leakage detected! Task IDs appear in both training/tuning and held-out: {leakage_ids}"
            )

        # Audit 2: Content Hash Disjointness (catches duplicate tasks with different IDs)
        train_hashes = {t.content_hash for t in train_tasks}
        tuning_hashes = {t.content_hash for t in tuning_tasks}
        held_out_hashes = {t.content_hash for t in held_out_tasks}

        leakage_hashes = (train_hashes | tuning_hashes) & held_out_hashes
        if leakage_hashes:
            raise DataLeakageError(
                f"Data leakage detected! Content hashes overlap between training/tuning and held-out: {leakage_hashes}"
            )

        return train_tasks, tuning_tasks, held_out_tasks


class StrategyExperimentRunner:
    """Executes controlled multi-baseline experiments evaluating tool-selection policies."""

    def __init__(
        self,
        trace_collector: TraceCollector | None = None,
        budget: BudgetConfig | None = None,
    ) -> None:
        self.trace_collector = trace_collector or TraceCollector()
        self.budget = budget or BudgetConfig(
            max_tool_calls=10, max_cost_usd=0.5, max_latency_seconds=30.0
        )

    async def _simulate_task_execution(
        self,
        task: EvaluationTask,
        policy: BaseToolSelectionPolicy,
        executor: SafePolicyExecutor,
        max_steps: int = 6,
    ) -> TaskRunResult:
        """Simulate a multi-step investigation for a task under a specific policy."""
        history: list[dict[str, Any]] = []
        tool_sequence: list[str] = []
        traces: list[ExecutionTrace] = []
        uninformative_calls = 0
        total_cost = 0.0
        total_latency = 0.0
        resolved = False

        # Available tools for this task
        avail = task.available_tools or [
            "inspect_git_status",
            "list_permitted_files",
            "search_source_code",
            "read_bounded_file",
            "apply_patch",
            "run_allowlisted_tests",
        ]

        # Key target tools needed to resolve this task
        required_tools = (
            set(task.optimal_tools)
            if task.optimal_tools
            else {
                "search_source_code",
                "read_bounded_file",
                "run_allowlisted_tests",
            }
        )
        covered_tools: set[str] = set()

        for step in range(max_steps):
            ctx = ToolSelectionContext(
                task_id=task.task_id,
                task_category=task.task_category,
                issue_description=task.issue_description,
                step_index=step,
                candidate_files=task.target_files,
                available_tools=avail,
                recent_history=history,
                error_context="Test assertion failed: Expected status 200 got 500"
                if step > 2
                else None,
            )

            decision = await executor.select_action(context=ctx, policy=policy)

            action = decision.selected_tool
            tool_sequence.append(action)

            # Determine simulated step outcome
            is_informative = action in required_tools
            if is_informative:
                covered_tools.add(action)
                outcome = ActionOutcome.SUCCESS
            else:
                uninformative_calls += 1
                outcome = ActionOutcome.NO_OP if action in avail else ActionOutcome.FAILURE

            # Simulated cost & latency based on tool type
            step_cost = 0.005 if "llm" in policy.policy_type else 0.0005
            if action == "run_allowlisted_tests":
                step_latency = 120.0
                step_cost += 0.001
            elif action in ("search_source_code", "read_bounded_file"):
                step_latency = 40.0
            else:
                step_latency = 15.0

            total_cost += step_cost
            total_latency += step_latency

            history.append(
                {
                    "step": step,
                    "tool": action,
                    "outcome": outcome.value,
                    "informative": is_informative,
                }
            )

            # Check if all required investigation tools have been executed
            if required_tools.issubset(covered_tools):
                resolved = True
                # Record final successful trace and finish
                trace = self.trace_collector.record_trace(
                    task_id=task.task_id,
                    task_category=task.task_category,
                    step_index=step,
                    initial_state={
                        "issue_description": task.issue_description,
                        "candidate_files": task.target_files,
                    },
                    available_tools=avail,
                    chosen_action=action,
                    action_inputs={"step": step},
                    relevant_observations={"informative": True, "covered": list(covered_tools)},
                    outcome=outcome,
                    cost_usd=step_cost,
                    latency_ms=step_latency,
                    final_evaluation_result=True,
                )
                traces.append(trace)
                break

            # Record intermediate trace
            trace = self.trace_collector.record_trace(
                task_id=task.task_id,
                task_category=task.task_category,
                step_index=step,
                initial_state={
                    "issue_description": task.issue_description,
                    "candidate_files": task.target_files,
                },
                available_tools=avail,
                chosen_action=action,
                action_inputs={"step": step},
                relevant_observations={"informative": is_informative},
                outcome=outcome,
                cost_usd=step_cost,
                latency_ms=step_latency,
                final_evaluation_result=False if step == max_steps - 1 else None,
            )
            traces.append(trace)

        return TaskRunResult(
            task_id=task.task_id,
            resolved=resolved,
            tool_sequence=tool_sequence,
            uninformative_calls=uninformative_calls,
            cost_usd=total_cost,
            latency_seconds=total_latency / 1000.0,
            traces=traces,
        )

    async def evaluate_policy_on_split(
        self,
        policy: BaseToolSelectionPolicy,
        tasks: list[EvaluationTask],
        baseline_results: dict[str, bool] | None = None,
        trials_per_task: int = 1,
    ) -> PolicyEvaluationMetrics:
        """Run policy across tasks in a split and compute comprehensive metrics."""
        reg = PolicyRegistry(default_policy=RuleBasedToolPolicy())
        executor = SafePolicyExecutor(registry=reg, budget_enforcer=BudgetEnforcer(self.budget))

        all_results: list[TaskRunResult] = []
        resolved_count = 0
        total_runs = len(tasks) * trials_per_task
        regressions = 0

        for task in tasks:
            task_resolved_any = False
            for _ in range(trials_per_task):
                res = await self._simulate_task_execution(
                    task=task,
                    policy=policy,
                    executor=executor,
                )
                all_results.append(res)
                if res.resolved:
                    task_resolved_any = True
                    resolved_count += 1

            # Check regression vs baseline
            if baseline_results is not None:
                baseline_passed = baseline_results.get(task.task_id, False)
                if baseline_passed and not task_resolved_any:
                    regressions += 1

        resolved_runs = [r for r in all_results if r.resolved]
        avg_calls = (
            sum(len(r.tool_sequence) for r in resolved_runs) / len(resolved_runs)
            if resolved_runs
            else 0.0
        )
        total_calls = sum(len(r.tool_sequence) for r in all_results)
        total_uninf = sum(r.uninformative_calls for r in all_results)
        uninf_ratio = total_uninf / total_calls if total_calls > 0 else 0.0

        total_cost = sum(r.cost_usd for r in all_results)
        total_lat = sum(r.latency_seconds for r in all_results)

        return PolicyEvaluationMetrics(
            policy_id=policy.policy_id,
            policy_type=policy.policy_type,
            total_tasks=total_runs,
            resolved_tasks=resolved_count,
            success_rate=resolved_count / total_runs if total_runs > 0 else 0.0,
            regressions=regressions,
            regression_rate=regressions / len(tasks) if tasks else 0.0,
            avg_tool_calls_per_resolved=avg_calls,
            avg_uninformative_ratio=uninf_ratio,
            total_cost_usd=total_cost,
            avg_cost_usd=total_cost / total_runs if total_runs > 0 else 0.0,
            avg_latency_seconds=total_lat / total_runs if total_runs > 0 else 0.0,
            task_results=all_results,
        )

    async def run_comparative_experiment(
        self,
        training_tasks: list[EvaluationTask],
        tuning_tasks: list[EvaluationTask],
        held_out_tasks: list[EvaluationTask],
        experimental_policy: BaseToolSelectionPolicy,
        llm_policy: BaseToolSelectionPolicy | None = None,
        trials_per_task: int = 1,
    ) -> ExperimentReport:
        """Execute full comparative evaluation across baselines and experimental policy."""
        # Step 1: Zero-Leakage Audit
        train_ids = {t.task_id for t in training_tasks}
        tuning_ids = {t.task_id for t in tuning_tasks}
        held_out_ids = {t.task_id for t in held_out_tasks}

        if (train_ids | tuning_ids) & held_out_ids:
            raise DataLeakageError(
                "Leakage detected: Training/Tuning IDs overlap with Held-Out IDs."
            )

        train_hashes = {t.content_hash for t in training_tasks}
        tuning_hashes = {t.content_hash for t in tuning_tasks}
        held_out_hashes = {t.content_hash for t in held_out_tasks}

        if (train_hashes | tuning_hashes) & held_out_hashes:
            raise DataLeakageError(
                "Leakage detected: Training/Tuning content hashes overlap with Held-Out."
            )

        # Step 2: Seed experience into experimental policy using training and tuning tasks
        pre_training_traces: list[ExecutionTrace] = []
        reg = PolicyRegistry()
        executor = SafePolicyExecutor(registry=reg)

        for task in training_tasks + tuning_tasks:
            res = await self._simulate_task_execution(
                task=task,
                policy=RuleBasedToolPolicy(),
                executor=executor,
            )
            pre_training_traces.extend(res.traces)

        # Update experimental policy with training experience
        experimental_policy.update(pre_training_traces)

        # Step 3: Run Baseline 1 (Fixed Rule-Based) on Held-Out tasks
        rule_baseline = RuleBasedToolPolicy(policy_id="baseline-rule-eval")
        rule_metrics = await self.evaluate_policy_on_split(
            policy=rule_baseline,
            tasks=held_out_tasks,
            baseline_results=None,
            trials_per_task=trials_per_task,
        )

        rule_resolutions = {r.task_id: r.resolved for r in rule_metrics.task_results}

        # Step 4: Run Baseline 2 (LLM-Selected) on Held-Out tasks
        active_llm_policy = llm_policy or LLMToolPolicy(policy_id="baseline-llm-eval")
        llm_metrics = await self.evaluate_policy_on_split(
            policy=active_llm_policy,
            tasks=held_out_tasks,
            baseline_results=rule_resolutions,
            trials_per_task=trials_per_task,
        )

        # Step 5: Run Experimental Policy on Held-Out tasks
        exp_metrics = await self.evaluate_policy_on_split(
            policy=experimental_policy,
            tasks=held_out_tasks,
            baseline_results=rule_resolutions,
            trials_per_task=trials_per_task,
        )

        # Step 6: Compute comparative deltas
        delta_success = exp_metrics.success_rate - rule_metrics.success_rate
        delta_eff = (
            exp_metrics.avg_tool_calls_per_resolved - rule_metrics.avg_tool_calls_per_resolved
        )
        delta_cost = exp_metrics.total_cost_usd - rule_metrics.total_cost_usd
        delta_lat = exp_metrics.avg_latency_seconds - rule_metrics.avg_latency_seconds

        # Step 7: Classify conclusion: IMPROVED, DEGRADED, or INCONCLUSIVE
        # Improvement condition:
        # Higher or equal success rate AND strictly better efficiency (fewer tool calls)
        # OR significantly higher success rate (> +5%) with low regression rate (< 10%)
        if (delta_success >= 0.05 and exp_metrics.regression_rate <= 0.1) or (
            abs(delta_success) < 0.05 and delta_eff < -0.2 and exp_metrics.regression_rate == 0.0
        ):
            conclusion = ExperimentConclusion.IMPROVED
            generalizes = True
            summary = (
                f"Experimental strategy '{experimental_policy.policy_id}' IMPROVED overall performance: "
                f"Success rate delta: {delta_success:+.1%}, Tool calls delta: {delta_eff:+.2f} calls/resolved, "
                f"Regression rate: {exp_metrics.regression_rate:.1%} on unseen held-out tasks."
            )
        elif delta_success <= -0.05 or exp_metrics.regression_rate >= 0.2:
            conclusion = ExperimentConclusion.DEGRADED
            generalizes = False
            summary = (
                f"Experimental strategy '{experimental_policy.policy_id}' DEGRADED performance: "
                f"Success rate delta: {delta_success:+.1%}, Regression rate: {exp_metrics.regression_rate:.1%}."
            )
        else:
            conclusion = ExperimentConclusion.INCONCLUSIVE
            generalizes = True if exp_metrics.success_rate >= 0.5 else False
            summary = (
                f"Experimental strategy '{experimental_policy.policy_id}' produced INCONCLUSIVE results: "
                f"Success rate delta: {delta_success:+.1%}, Efficiency delta: {delta_eff:+.2f}. "
                f"Deltas lie within empirical noise margins."
            )

        return ExperimentReport(
            timestamp=time.time(),
            training_task_count=len(training_tasks),
            tuning_task_count=len(tuning_tasks),
            held_out_task_count=len(held_out_tasks),
            trials_per_task=trials_per_task,
            baseline_rule_metrics=rule_metrics,
            baseline_llm_metrics=llm_metrics,
            experimental_metrics=exp_metrics,
            delta_success_rate=delta_success,
            delta_efficiency=delta_eff,
            delta_cost_usd=delta_cost,
            delta_latency_seconds=delta_lat,
            generalizes_to_held_out=generalizes,
            leakage_free_verified=True,
            conclusion=conclusion,
            summary_text=summary,
        )
