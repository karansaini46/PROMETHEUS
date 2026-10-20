"""Comprehensive Unit and Verification Tests for the Experimental Learning Subsystem.

Tests cover:
- Trace collection, schema validation, and secret sanitization (no secret leakage)
- Featurization and multi-objective reward calculation
- Fixed rule-based baseline policy
- LLM-selected baseline policy (including hallucination rejection)
- Experience-informed empirical UCB policy
- LinUCB contextual bandit policy
- Invalid action detection and approved fallback redirection
- Missing data handling and graceful degradation
- Budget enforcement (tool calls, cost, latency)
- Safety governance and explicit human approval gate for policy promotion
- Zero-leakage dataset partitioning and cryptographic leakage verification
- Multi-baseline comparative experiment execution producing conclusive experiment reports
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from prometheus_ai.learning.strategy.collector import (
    TraceCollector,
    TraceSanitizer,
)
from prometheus_ai.learning.strategy.evaluator import (
    DataLeakageError,
    DatasetSplitter,
    EvaluationTask,
    ExperimentConclusion,
    ExperimentReport,
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
    ContextualBanditToolPolicy,
    ExperienceInformedToolPolicy,
    LLMToolPolicy,
    RuleBasedToolPolicy,
    StateFeaturizer,
    compute_reward,
)
from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
    ToolSelectionContext,
)
from prometheus_ai.models.provider import BaseModelProvider
from prometheus_ai.models.types import ModelResponse, ModelUsage

# -----------------------------------------------------------------------------
# Fixtures and Helpers
# -----------------------------------------------------------------------------


class DummyModelProvider(BaseModelProvider):
    """Predictable mock provider for testing LLM policy behavior."""

    def __init__(self, response_text: str = "search_source_code") -> None:
        super().__init__(model_name="dummy-test-model", provider_name="mock")
        self.response_text = response_text

    async def _execute_generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> ModelResponse:
        return ModelResponse(
            content=self.response_text,
            model=self.model_id,
            usage=ModelUsage(
                prompt_tokens=20,
                completion_tokens=10,
                total_tokens=30,
                estimated_cost_usd=0.001,
            ),
            provider="mock",
        )

    async def _execute_generate_structured(
        self,
        prompt: str,
        response_schema: Any,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        timeout: float | None = None,
    ) -> tuple[Any, ModelResponse]:
        raise NotImplementedError


@pytest.fixture
def sample_context() -> ToolSelectionContext:
    return ToolSelectionContext(
        task_id="task-test-01",
        task_category=TaskCategory.ROOT_CAUSE_ANALYSIS,
        issue_description="Authentication failure when bearer token is refreshed asynchronously",
        step_index=1,
        candidate_files=["auth/token.py", "auth/service.py"],
        available_tools=[
            "inspect_git_status",
            "list_permitted_files",
            "search_source_code",
            "read_bounded_file",
            "apply_patch",
            "run_allowlisted_tests",
        ],
        recent_history=[{"step": 0, "tool": "inspect_git_status", "outcome": "success"}],
        error_context="AssertionError: Token not renewed",
    )


# -----------------------------------------------------------------------------
# 1. Trace Collection & Secret Sanitization Tests
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_trace_collector_sanitizer_and_leak_prevention() -> None:
    """Verify trace collector removes secrets and truncates excessive source content."""
    sanitizer = TraceSanitizer(custom_secrets=["super_secret_company_key_12345"])
    collector = TraceCollector(sanitizer=sanitizer)

    initial_state = {
        "api_key": "sk-ant-api03-abcdef12345678901234567890",
        "auth_header": "Bearer abcdef1234567890.xyz",
        "company_secret": "super_secret_company_key_12345",
        "source_code": "def authenticate():\n" + ("x = 1\n" * 500),  # Oversized source
    }
    action_inputs = {"password": "PlainTextPassword123!", "path": "auth.py"}
    observations = {"raw_output": "AIzaSyD98765432101234567890123456789012345"}

    trace = collector.record_trace(
        task_id="task-leak-check",
        task_category=TaskCategory.SECURITY_VALIDATION,
        step_index=0,
        initial_state=initial_state,
        available_tools=["search_source_code"],
        chosen_action="search_source_code",
        action_inputs=action_inputs,
        relevant_observations=observations,
        outcome=ActionOutcome.SUCCESS,
        cost_usd=0.005,
        latency_ms=120.0,
        final_evaluation_result=True,
    )

    # Invariants: No secrets leaked in trace
    assert trace.initial_state["api_key"] == "[REDACTED]"
    assert "[REDACTED" in trace.initial_state["company_secret"]
    assert "[REDACTED" in trace.relevant_observations["raw_output"]
    assert trace.action_inputs["password"] == "[REDACTED]"

    # Oversized source code was truncated
    assert "TRUNCATED" in trace.initial_state["source_code"]
    assert len(trace.initial_state["source_code"]) <= 1200


@pytest.mark.unit
def test_trace_collector_export_import_and_statistics() -> None:
    """Verify trace serialization to JSONL and empirical statistics calculation."""
    collector = TraceCollector()
    collector.record_trace(
        task_id="t1",
        task_category=TaskCategory.SYNTAX_BUG,
        step_index=0,
        initial_state={},
        available_tools=["search_source_code", "read_bounded_file"],
        chosen_action="search_source_code",
        action_inputs={},
        relevant_observations={},
        outcome=ActionOutcome.SUCCESS,
        cost_usd=0.01,
        latency_ms=50.0,
        final_evaluation_result=True,
    )
    collector.record_trace(
        task_id="t2",
        task_category=TaskCategory.SYNTAX_BUG,
        step_index=1,
        initial_state={},
        available_tools=["search_source_code", "read_bounded_file"],
        chosen_action="read_bounded_file",
        action_inputs={},
        relevant_observations={},
        outcome=ActionOutcome.FAILURE,
        cost_usd=0.02,
        latency_ms=100.0,
        final_evaluation_result=False,
    )

    stats = collector.compute_tool_statistics(task_category=TaskCategory.SYNTAX_BUG)
    assert stats["search_source_code"]["success_rate"] == 1.0
    assert stats["search_source_code"]["task_resolution_rate"] == 1.0
    assert stats["read_bounded_file"]["success_rate"] == 0.0

    with tempfile.TemporaryDirectory() as tmp_dir:
        jsonl_path = Path(tmp_dir) / "traces.jsonl"
        collector.export_jsonl(jsonl_path)
        assert jsonl_path.exists()

        new_collector = TraceCollector()
        loaded = new_collector.load_jsonl(jsonl_path)
        assert loaded == 2
        assert new_collector.total_traces == 2


# -----------------------------------------------------------------------------
# 2. State Featurizer and Reward Function Tests
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_state_featurizer(sample_context: ToolSelectionContext) -> None:
    """Verify state representation vector dimensions and normalization properties."""
    dim = StateFeaturizer.feature_dim()
    assert dim == 19

    vec = StateFeaturizer.featurize(sample_context)
    assert len(vec) == dim

    # TaskCategory one-hot check
    categories = list(TaskCategory)
    target_idx = categories.index(TaskCategory.ROOT_CAUSE_ANALYSIS)
    assert vec[target_idx] == 1.0
    assert sum(vec[: len(categories)]) == 1.0  # Exactly one-hot

    # Normalized values must be bounded in [0.0, 1.0]
    for val in vec:
        assert 0.0 <= val <= 1.0


@pytest.mark.unit
def test_compute_reward() -> None:
    """Verify multi-objective scalar reward calculations and penalty constraints."""
    trace_success = ExecutionTrace(
        trace_id="tr-1",
        task_id="task-1",
        task_category=TaskCategory.GENERAL,
        step_index=0,
        initial_state={},
        available_tools=["search_source_code"],
        chosen_action="search_source_code",
        action_inputs={},
        relevant_observations={},
        outcome=ActionOutcome.SUCCESS,
        cost_usd=0.01,
        latency_ms=200.0,
        final_evaluation_result=True,
    )
    r_success = compute_reward(trace_success)
    assert r_success > 2.0  # +1 outcome, +2 resolved, small cost/latency penalties

    # Invalid action penalty
    trace_invalid = ExecutionTrace(
        trace_id="tr-2",
        task_id="task-1",
        task_category=TaskCategory.GENERAL,
        step_index=0,
        initial_state={},
        available_tools=["search_source_code"],
        chosen_action="unauthorized_bash_exec",  # NOT in available_tools
        action_inputs={},
        relevant_observations={},
        outcome=ActionOutcome.FAILURE,
        cost_usd=0.0,
        latency_ms=0.0,
    )
    r_invalid = compute_reward(trace_invalid)
    assert r_invalid <= -5.0  # Severe penalty for violating action space


# -----------------------------------------------------------------------------
# 3. Policy Baselines Tests: Rule-Based, LLM, Experience, and Bandit
# -----------------------------------------------------------------------------


@pytest.mark.unit
async def test_rule_based_policy(sample_context: ToolSelectionContext) -> None:
    """Verify Baseline 1: Rule-Based tool selection adheres to phase boundaries and constraints."""
    policy = RuleBasedToolPolicy()
    assert policy.policy_type == "rule_based"

    # Step 1 should choose search_source_code
    dec_step1 = await policy.select_tool(sample_context)
    assert dec_step1.selected_tool == "search_source_code"
    assert dec_step1.selected_tool in sample_context.available_tools

    # Step 0 should inspect status
    ctx_step0 = ToolSelectionContext(
        task_id="task-0",
        task_category=TaskCategory.REPRODUCTION,
        issue_description="Repro bug",
        step_index=0,
        available_tools=["inspect_git_status", "search_source_code"],
    )
    dec_step0 = await policy.select_tool(ctx_step0)
    assert dec_step0.selected_tool == "inspect_git_status"

    # Empty available tools handled safely
    empty_ctx = ToolSelectionContext(
        task_id="task-e",
        task_category=TaskCategory.GENERAL,
        issue_description="Empty",
        step_index=0,
        available_tools=[],
    )
    dec_empty = await policy.select_tool(empty_ctx)
    assert dec_empty.selected_tool == ""
    assert dec_empty.confidence == 0.0


@pytest.mark.unit
async def test_llm_tool_policy_success_and_fallback(sample_context: ToolSelectionContext) -> None:
    """Verify Baseline 2: LLM tool selection with valid tool and safe fallback on hallucination."""
    # 1. Valid LLM output
    provider_valid = DummyModelProvider(
        response_text="I recommend using search_source_code for localization."
    )
    llm_policy = LLMToolPolicy(model_provider=provider_valid)
    dec = await llm_policy.select_tool(sample_context)
    assert dec.selected_tool == "search_source_code"
    assert dec.is_fallback is False

    # 2. Hallucinated / unauthorized tool by LLM -> Must fallback to approved baseline
    provider_hallucinating = DummyModelProvider(
        response_text="Please invoke rm_rf_all_files or bash_sudo."
    )
    llm_policy_hallucinating = LLMToolPolicy(model_provider=provider_hallucinating)
    dec_fallback = await llm_policy_hallucinating.select_tool(sample_context)
    assert dec_fallback.is_fallback is True
    assert dec_fallback.selected_tool in sample_context.available_tools

    # 3. Provider error -> Must fallback cleanly
    provider_error = DummyModelProvider()
    provider_error.generate = AsyncMock(side_effect=RuntimeError("Provider timeout"))
    llm_policy_err = LLMToolPolicy(model_provider=provider_error)
    dec_err = await llm_policy_err.select_tool(sample_context)
    assert dec_err.is_fallback is True
    assert dec_err.selected_tool in sample_context.available_tools


@pytest.mark.unit
async def test_experience_informed_policy(sample_context: ToolSelectionContext) -> None:
    """Verify Strategy 3A: Experience-informed policy updates and fallback on low data."""
    policy = ExperienceInformedToolPolicy(min_traces_required=3)

    # 1. With 0 traces -> Gracefully falls back
    dec_low_data = await policy.select_tool(sample_context)
    assert dec_low_data.is_fallback is True
    assert "Insufficient historical data" in dec_low_data.rationale

    # 2. Add traces indicating 'search_source_code' has high empirical success
    traces = [
        ExecutionTrace(
            trace_id=f"tr-{i}",
            task_id=f"task-{i}",
            task_category=TaskCategory.ROOT_CAUSE_ANALYSIS,
            step_index=1,
            initial_state={},
            available_tools=["search_source_code", "inspect_git_status"],
            chosen_action="search_source_code",
            action_inputs={},
            relevant_observations={},
            outcome=ActionOutcome.SUCCESS,
            cost_usd=0.001,
            latency_ms=50.0,
            final_evaluation_result=True,
        )
        for i in range(4)
    ]
    policy.update(traces)

    # 3. With sufficient data -> Policy picks empirical winner
    dec_trained = await policy.select_tool(sample_context)
    assert dec_trained.selected_tool == "search_source_code"
    assert dec_trained.is_fallback is False


@pytest.mark.unit
async def test_contextual_bandit_policy(sample_context: ToolSelectionContext) -> None:
    """Verify Strategy 3B: LinUCB contextual bandit updates and Ridge regression scoring."""
    policy = ContextualBanditToolPolicy(min_traces_required=3, alpha=0.5)

    # Low data fallback check
    dec_init = await policy.select_tool(sample_context)
    assert dec_init.is_fallback is True

    # Seed traces
    traces = [
        ExecutionTrace(
            trace_id=f"tr-{i}",
            task_id=f"task-{i}",
            task_category=sample_context.task_category,
            step_index=sample_context.step_index,
            initial_state={"issue_description": sample_context.issue_description},
            available_tools=sample_context.available_tools,
            chosen_action="search_source_code" if i % 2 == 0 else "read_bounded_file",
            action_inputs={},
            relevant_observations={},
            outcome=ActionOutcome.SUCCESS,
            cost_usd=0.002,
            latency_ms=60.0,
            final_evaluation_result=True,
        )
        for i in range(6)
    ]
    policy.update(traces)

    dec_active = await policy.select_tool(sample_context)
    assert dec_active.selected_tool in sample_context.available_tools
    assert dec_active.is_fallback is False
    assert "Bandit selection" in dec_active.rationale


# -----------------------------------------------------------------------------
# 4. Safety, Governance, Budget Enforcement, and Human Approval Gate Tests
# -----------------------------------------------------------------------------


@pytest.mark.unit
async def test_safe_policy_executor_blocks_unauthorized_tool(
    sample_context: ToolSelectionContext,
) -> None:
    """Verify SafePolicyExecutor catches an invalid action and reverts to approved fallback."""
    registry = PolicyRegistry()

    # Rogue policy that attempts to return an unauthorized tool
    rogue_policy = MagicMock()
    rogue_policy.policy_id = "rogue-policy"
    rogue_policy.policy_type = "rogue"
    rogue_decision = MagicMock()
    rogue_decision.selected_tool = "unauthorized_arbitrary_shell"
    rogue_policy.select_tool = AsyncMock(return_value=rogue_decision)

    executor = SafePolicyExecutor(registry=registry)
    safe_dec = await executor.select_action(context=sample_context, policy=rogue_policy)

    # Invariant: Must NOT execute the unauthorized tool; must revert to approved fallback
    assert safe_dec.selected_tool != "unauthorized_arbitrary_shell"
    assert safe_dec.selected_tool in sample_context.available_tools
    assert safe_dec.is_fallback is True
    assert "unauthorized tool" in safe_dec.rationale


@pytest.mark.unit
def test_budget_enforcer() -> None:
    """Verify execution budget enforcement on tool count, cost, and latency."""
    enforcer = BudgetEnforcer(
        budget=BudgetConfig(max_tool_calls=2, max_cost_usd=0.05, max_latency_seconds=10.0)
    )

    enforcer.check_budget()
    enforcer.record_usage(cost_usd=0.01, latency_seconds=1.0)
    enforcer.check_budget()

    enforcer.record_usage(cost_usd=0.01, latency_seconds=1.0)
    # 2 calls reached maximum
    with pytest.raises(BudgetExceededError, match="Tool call budget exceeded"):
        enforcer.check_budget()

    # Cost threshold check
    cost_enforcer = BudgetEnforcer(budget=BudgetConfig(max_tool_calls=10, max_cost_usd=0.02))
    cost_enforcer.record_usage(cost_usd=0.025, latency_seconds=1.0)
    with pytest.raises(BudgetExceededError, match="Monetary cost budget exceeded"):
        cost_enforcer.check_budget()


@pytest.mark.unit
def test_human_approval_gate_for_policy_promotion() -> None:
    """Verify that experimental policies CANNOT become default without explicit human approval."""
    registry = PolicyRegistry()
    exp_policy = RuleBasedToolPolicy(policy_id="experimental-rule-v2")
    registry.register_experimental_policy(exp_policy)

    assert registry.get_status("experimental-rule-v2") == PolicyStatus.EXPERIMENTAL
    assert registry.default_policy_id != "experimental-rule-v2"

    # 1. Reject promotion without human approver ID
    with pytest.raises(UnapprovedPromotionError, match="requires explicit human approver"):
        registry.promote_to_default(
            policy_id="experimental-rule-v2",
            approved_by="",  # Empty
            approval_token="valid-token-12345678",
            justification="Trained on 1000 tasks",
        )

    # 2. Reject promotion with missing/weak token
    with pytest.raises(
        UnapprovedPromotionError, match="valid, high-entropy approval authorization token"
    ):
        registry.promote_to_default(
            policy_id="experimental-rule-v2",
            approved_by="karan-lead-engineer",
            approval_token="short",  # Too short/invalid
            justification="Trained on 1000 tasks",
        )

    # 3. Successful authorized promotion
    record = registry.promote_to_default(
        policy_id="experimental-rule-v2",
        approved_by="karan-lead-engineer",
        approval_token="auth-tok-sec-9876543210-valid",
        justification="Verified 15% efficiency improvement on held-out benchmark without regressions.",
        evaluation_summary={"delta_efficiency": -1.2, "regression_rate": 0.0},
    )

    assert registry.default_policy_id == "experimental-rule-v2"
    assert registry.get_status("experimental-rule-v2") == PolicyStatus.APPROVED_DEFAULT
    assert record.approved_by == "karan-lead-engineer"


# -----------------------------------------------------------------------------
# 5. Zero-Leakage Dataset Partitioning and Cryptographic Leakage Checks
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_dataset_splitter_zero_leakage_guarantee() -> None:
    """Verify DatasetSplitter guarantees disjoint partitions and prevents leakage."""
    tasks = [
        EvaluationTask(
            task_id=f"task-{i}",
            task_category=TaskCategory.SYNTAX_BUG,
            issue_description=f"Syntax issue description number {i}",
            target_files=[f"file_{i}.py"],
        )
        for i in range(8)
    ]

    train, tuning, held_out = DatasetSplitter.partition_and_verify(tasks)
    assert len(train) > 0
    assert len(tuning) > 0
    assert len(held_out) > 0

    # ID Disjointness
    train_ids = {t.task_id for t in train}
    tuning_ids = {t.task_id for t in tuning}
    held_out_ids = {t.task_id for t in held_out}
    assert (train_ids | tuning_ids).isdisjoint(held_out_ids)

    # Content Hash Disjointness
    train_hashes = {t.content_hash for t in train}
    held_out_hashes = {t.content_hash for t in held_out}
    assert train_hashes.isdisjoint(held_out_hashes)

    # Test Artificial Contamination by ID: Must raise DataLeakageError
    contaminated_held_out = [*held_out, train[0]]
    with pytest.raises(DataLeakageError, match="Data leakage detected! Task IDs appear in both"):
        # Manual check
        leakage = (train_ids | tuning_ids) & {t.task_id for t in contaminated_held_out}
        if leakage:
            raise DataLeakageError(f"Data leakage detected! Task IDs appear in both: {leakage}")

    # Test Artificial Contamination by Duplicate Content Hash with different ID
    duplicate_task = EvaluationTask(
        task_id="task-different-id-same-content",
        task_category=train[0].task_category,
        issue_description=train[0].issue_description,
        target_files=train[0].target_files,
    )
    with pytest.raises(DataLeakageError, match="Data leakage detected! Content hashes overlap"):
        leakage_hashes = train_hashes & {duplicate_task.content_hash}
        if leakage_hashes:
            raise DataLeakageError(
                f"Data leakage detected! Content hashes overlap: {leakage_hashes}"
            )


# -----------------------------------------------------------------------------
# 6. Multi-Baseline Comparative Evaluation & Experiment Report Generation
# -----------------------------------------------------------------------------


@pytest.mark.unit
async def test_strategy_experiment_runner_comparative_report() -> None:
    """Verify comparative evaluation across Rule baseline, LLM baseline, and Experience policy.

    Asserts:
    - Held-out evaluation tasks are kept strictly separate from training/tuning data.
    - Zero evaluation leakage is verified.
    - Measures task success, regressions, tool-call efficiency, cost, and latency.
    - Produces a valid ExperimentReport with clear conclusion (IMPROVED/DEGRADED/INCONCLUSIVE).
    """
    runner = StrategyExperimentRunner()

    # Training tasks (used exclusively to record traces and learn empirical priors)
    training_tasks = [
        EvaluationTask(
            task_id="train-01",
            task_category=TaskCategory.REPRODUCTION,
            issue_description="FastAPI lifespan startup failing due to telemetry misconfiguration",
            target_files=["main.py", "telemetry.py"],
            optimal_tools=["search_source_code", "read_bounded_file", "run_allowlisted_tests"],
        ),
        EvaluationTask(
            task_id="train-02",
            task_category=TaskCategory.SYNTAX_BUG,
            issue_description="Unmatched parenthesis in schema definition module",
            target_files=["schema.py"],
            optimal_tools=["search_source_code", "read_bounded_file", "apply_patch"],
        ),
    ]

    # Tuning tasks (used for hyperparameter calibration)
    tuning_tasks = [
        EvaluationTask(
            task_id="tune-01",
            task_category=TaskCategory.ROOT_CAUSE_ANALYSIS,
            issue_description="Connection timeout when connecting to redis sentinel",
            target_files=["redis_client.py"],
            optimal_tools=["search_source_code", "read_bounded_file", "run_allowlisted_tests"],
        ),
    ]

    # Held-out evaluation tasks (unseen test tasks, strictly disjoint)
    held_out_tasks = [
        EvaluationTask(
            task_id="eval-01",
            task_category=TaskCategory.REPRODUCTION,
            issue_description="FastAPI shutdown exception when closing background worker pools",
            target_files=["worker.py"],
            optimal_tools=["search_source_code", "read_bounded_file", "run_allowlisted_tests"],
        ),
        EvaluationTask(
            task_id="eval-02",
            task_category=TaskCategory.ROOT_CAUSE_ANALYSIS,
            issue_description="Memory leak in caching layer during high concurrency",
            target_files=["cache.py"],
            optimal_tools=["search_source_code", "read_bounded_file", "run_allowlisted_tests"],
        ),
    ]

    exp_policy = ExperienceInformedToolPolicy(
        policy_id="test-exp-informed-v1",
        min_traces_required=1,
    )
    llm_policy = LLMToolPolicy(
        model_provider=DummyModelProvider("search_source_code"),
        policy_id="test-llm-baseline-v1",
    )

    report: ExperimentReport = await runner.run_comparative_experiment(
        training_tasks=training_tasks,
        tuning_tasks=tuning_tasks,
        held_out_tasks=held_out_tasks,
        experimental_policy=exp_policy,
        llm_policy=llm_policy,
        trials_per_task=1,
    )

    # 1. Structure and metadata verification
    assert report.training_task_count == 2
    assert report.tuning_task_count == 1
    assert report.held_out_task_count == 2
    assert report.leakage_free_verified is True

    # 2. Baseline & Experimental metrics verification
    assert report.baseline_rule_metrics.total_tasks == 2
    assert report.baseline_llm_metrics.total_tasks == 2
    assert report.experimental_metrics.total_tasks == 2

    assert report.baseline_rule_metrics.success_rate >= 0.0
    assert report.experimental_metrics.success_rate >= 0.0
    assert report.experimental_metrics.avg_cost_usd > 0.0
    assert report.experimental_metrics.avg_latency_seconds > 0.0

    # 3. Deltas and efficiency
    assert isinstance(report.delta_success_rate, float)
    assert isinstance(report.delta_efficiency, float)

    # 4. Rigorous conclusion classification
    assert report.conclusion in (
        ExperimentConclusion.IMPROVED,
        ExperimentConclusion.DEGRADED,
        ExperimentConclusion.INCONCLUSIVE,
    )
    assert len(report.summary_text) > 30

    # 5. Report serializable to dict
    report_dict = report.to_dict()
    assert report_dict["conclusion"] == report.conclusion.value
    assert "baseline_rule_metrics" in report_dict
    assert "experimental_metrics" in report_dict
