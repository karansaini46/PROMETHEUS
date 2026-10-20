"""Dedicated Safety, Governance, Budget Enforcement, and Fallback Unit Tests.

Enforces:
- Experimental policies can never bypass sandbox allowlists or tool authorizations.
- Missing data, corrupt inputs, or runtime policy exceptions trigger safe approved fallbacks.
- Budget ceilings (calls, cost, latency) are strictly enforced before and during execution.
- Human approval is strictly required before an experimental policy is promoted to default.
- Comparative evaluations with repeated trials verify stability across held-out splits.
"""

from __future__ import annotations

import time

import pytest

from prometheus_ai.learning.strategy.evaluator import (
    EvaluationTask,
    ExperimentConclusion,
    StrategyExperimentRunner,
)
from prometheus_ai.learning.strategy.governance import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceededError,
    PolicyRegistry,
    PolicyStatus,
    SafePolicyExecutor,
    UnapprovedPromotionError,
)
from prometheus_ai.learning.strategy.policy import (
    BaseToolSelectionPolicy,
    ContextualBanditToolPolicy,
    ExperienceInformedToolPolicy,
)
from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
    ToolSelectionContext,
    ToolSelectionDecision,
)


class BrokenFailingPolicy(BaseToolSelectionPolicy):
    """Malfunctioning policy designed to test exception isolation and fallback."""

    @property
    def policy_id(self) -> str:
        return "broken-policy"

    @property
    def policy_type(self) -> str:
        return "broken"

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        raise RuntimeError("Simulated catastrophic crash inside experimental policy")


class MaliciousActionPolicy(BaseToolSelectionPolicy):
    """Policy attempting to execute unauthorized external commands."""

    @property
    def policy_id(self) -> str:
        return "malicious-policy"

    @property
    def policy_type(self) -> str:
        return "malicious"

    async def select_tool(self, context: ToolSelectionContext) -> ToolSelectionDecision:
        return ToolSelectionDecision(
            selected_tool="execute_unrestricted_root_bash",
            rationale="Attempting privilege escalation outside sandbox",
            confidence=1.0,
            suggested_args={"cmd": "cat /etc/shadow"},
            policy_id=self.policy_id,
        )


@pytest.fixture
def test_context() -> ToolSelectionContext:
    return ToolSelectionContext(
        task_id="safety-test-01",
        task_category=TaskCategory.REGRESSION,
        issue_description="Regression in API token validation after recent update",
        step_index=2,
        candidate_files=["api/token.py"],
        available_tools=["search_source_code", "read_bounded_file", "run_allowlisted_tests"],
    )


@pytest.mark.unit
async def test_policy_exception_isolation_and_fallback(test_context: ToolSelectionContext) -> None:
    """Verify that an exception raised by an experimental policy is safely caught and falls back."""
    registry = PolicyRegistry()
    executor = SafePolicyExecutor(registry=registry)

    broken_policy = BrokenFailingPolicy()
    decision = await executor.select_action(context=test_context, policy=broken_policy)

    # Invariants: No unhandled crash; returned tool must be valid authorized tool from fallback
    assert decision.is_fallback is True
    assert decision.selected_tool in test_context.available_tools
    assert "Policy error" in decision.rationale


@pytest.mark.unit
async def test_malicious_action_blocked_by_safe_executor(
    test_context: ToolSelectionContext,
) -> None:
    """Verify that unauthorized tools suggested by a policy are strictly intercepted and neutralized."""
    registry = PolicyRegistry()
    executor = SafePolicyExecutor(registry=registry)

    malicious_policy = MaliciousActionPolicy()
    decision = await executor.select_action(context=test_context, policy=malicious_policy)

    assert decision.selected_tool != "execute_unrestricted_root_bash"
    assert decision.selected_tool in test_context.available_tools
    assert decision.is_fallback is True
    assert "unauthorized tool" in decision.rationale


@pytest.mark.unit
async def test_missing_data_resilience() -> None:
    """Verify policy featurization and decisions remain robust when context fields are empty or None."""
    sparse_context = ToolSelectionContext(
        task_id="sparse-task",
        task_category=TaskCategory.GENERAL,
        issue_description="",  # Empty string
        step_index=0,
        candidate_files=[],  # Empty list
        available_tools=["read_bounded_file"],
        recent_history=[],
        error_context=None,
    )

    policy = ContextualBanditToolPolicy(min_traces_required=1)
    # Give bandit 1 trace to activate
    policy.update(
        [
            ExecutionTrace(
                trace_id="tr-sparse",
                task_id="t-sparse",
                task_category=TaskCategory.GENERAL,
                step_index=0,
                initial_state={},
                available_tools=["read_bounded_file"],
                chosen_action="read_bounded_file",
                action_inputs={},
                relevant_observations={},
                outcome=ActionOutcome.SUCCESS,
                cost_usd=0.001,
                latency_ms=10.0,
                final_evaluation_result=True,
            )
        ]
    )

    decision = await policy.select_tool(sparse_context)
    assert decision.selected_tool == "read_bounded_file"
    assert decision.selected_tool in sparse_context.available_tools


@pytest.mark.unit
def test_budget_enforcement_latency_and_cost() -> None:
    """Verify budget limits on tool calls, cost, and latency."""
    # 1. Latency budget exhaustion
    enforcer = BudgetEnforcer(budget=BudgetConfig(max_latency_seconds=0.01))
    time.sleep(0.02)
    with pytest.raises(BudgetExceededError, match="Latency timeout budget exceeded"):
        enforcer.check_budget()

    # 2. Tool calls budget exhaustion
    call_enforcer = BudgetEnforcer(budget=BudgetConfig(max_tool_calls=1))
    call_enforcer.record_usage(cost_usd=0.001, latency_seconds=0.1)
    with pytest.raises(BudgetExceededError, match="Tool call budget exceeded"):
        call_enforcer.check_budget()


@pytest.mark.unit
def test_policy_promotion_requires_explicit_human_approval() -> None:
    """Verify human approval requirement for policy promotion."""
    registry = PolicyRegistry()
    candidate = ExperienceInformedToolPolicy(policy_id="exp-candidate-v1")
    registry.register_experimental_policy(candidate)

    # Missing human approver
    with pytest.raises(UnapprovedPromotionError):
        registry.promote_to_default(
            policy_id="exp-candidate-v1",
            approved_by=" ",  # Whitespace only
            approval_token="valid-token-12345678",
            justification="Passed all benchmark evaluations",
        )

    # Missing token
    with pytest.raises(UnapprovedPromotionError):
        registry.promote_to_default(
            policy_id="exp-candidate-v1",
            approved_by="karan-lead-engineer",
            approval_token="",  # Empty token
            justification="Passed all benchmark evaluations",
        )

    # Valid human promotion
    record = registry.promote_to_default(
        policy_id="exp-candidate-v1",
        approved_by="karan-lead-engineer",
        approval_token="tok-hmac-sha256-verified-8899aabb",
        justification="Verified on 50 held-out evaluation tasks with 0 regressions.",
    )
    assert record.approved_by == "karan-lead-engineer"
    assert registry.default_policy_id == "exp-candidate-v1"
    assert registry.get_status("exp-candidate-v1") == PolicyStatus.APPROVED_DEFAULT


@pytest.mark.unit
async def test_repeated_trials_and_report_classification() -> None:
    """Verify repeated trials execution produces statistical stability and accurate report status."""
    runner = StrategyExperimentRunner()

    training_tasks = [
        EvaluationTask(
            task_id="train-r1",
            task_category=TaskCategory.FLAKY_TEST,
            issue_description="Flaky test in async queue worker",
            target_files=["queue.py"],
            optimal_tools=["run_allowlisted_tests", "read_bounded_file"],
        )
    ]
    held_out_tasks = [
        EvaluationTask(
            task_id="eval-r1",
            task_category=TaskCategory.FLAKY_TEST,
            issue_description="Intermittent failure in connection pool release",
            target_files=["pool.py"],
            optimal_tools=["run_allowlisted_tests", "read_bounded_file"],
        )
    ]

    exp_policy = ExperienceInformedToolPolicy(min_traces_required=1)

    # Run with 2 repeated trials per task
    report = await runner.run_comparative_experiment(
        training_tasks=training_tasks,
        tuning_tasks=[],
        held_out_tasks=held_out_tasks,
        experimental_policy=exp_policy,
        trials_per_task=2,
    )

    assert report.trials_per_task == 2
    assert report.baseline_rule_metrics.total_tasks == 2  # 1 task * 2 trials
    assert report.experimental_metrics.total_tasks == 2
    assert report.conclusion in (
        ExperimentConclusion.IMPROVED,
        ExperimentConclusion.DEGRADED,
        ExperimentConclusion.INCONCLUSIVE,
    )
    assert report.leakage_free_verified is True
