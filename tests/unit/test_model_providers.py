"""Comprehensive Unit Tests for PROMETHEUS Model Integration Layer.

Validates:
- Valid and invalid structured responses (rejection of malformed data)
- Timeouts and cooperative cancellation
- Rate limits and provider error normalization
- Transient retry policy with exponential backoff
- Budget limits enforcement (calls, time, tokens, cost, response size)
- Tool calling requests
- Mock provider explicit labeling
"""

import asyncio

import pytest

from prometheus_ai.models.budget import (
    BudgetLimits,
    BudgetTracker,
    CancellationToken,
)
from prometheus_ai.models.exceptions import (
    ModelAuthenticationError,
    ModelBudgetExceededError,
    ModelCancelledError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelTimeoutError,
)
from prometheus_ai.models.mock_provider import MockModelProvider
from prometheus_ai.models.structured_outputs import (
    FinalReport,
    InvestigationHypothesis,
    InvestigationPlan,
    ProposedPatch,
    TaskPlan,
    TaskStep,
)
from prometheus_ai.models.types import ModelUsage, ToolCallRequest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_text_generation_success() -> None:
    """Verify standard text generation succeeds with complete metadata."""
    provider = MockModelProvider(
        model_name="mock-claude-3-5",
        default_response_text="Analyzed bug in auth_service.py line 42.",
    )

    response = await provider.generate(prompt="Investigate login crash")
    assert response.content == "Analyzed bug in auth_service.py line 42."
    assert response.model == "mock-claude-3-5"
    assert response.is_mock is True  # Mock results must be explicitly labeled
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0
    assert response.usage.is_cost_estimated is True
    assert len(provider.call_history) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_call_requests() -> None:
    """Verify provider emits structured tool-call requests."""
    provider = MockModelProvider()
    provider.canned_tool_calls = [
        ToolCallRequest(
            call_id="call_123",
            name="ripgrep_search",
            arguments={"query": "def authenticate", "path": "services/auth"},
            reasoning="Locate authentication definition",
        )
    ]

    response = await provider.generate(
        prompt="Search for auth",
        tools=[{"name": "ripgrep_search", "parameters": {}}],
    )

    assert response.tool_calls is not None
    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.call_id == "call_123"
    assert call.name == "ripgrep_search"
    assert call.arguments["query"] == "def authenticate"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_structured_investigation_plan() -> None:
    """Verify structured output parsing for InvestigationPlan."""
    provider = MockModelProvider()
    valid_plan = InvestigationPlan(
        hypotheses=[
            InvestigationHypothesis(
                hypothesis_id="hyp-1",
                title="Off-by-one index in buffer read",
                description="Buffer pointer exceeds allocation when payload length is exactly 1024 bytes.",
                confidence=0.85,
                suspected_components=["buffer_reader.py"],
                validation_steps=["Run test_payload_boundary with 1024 byte payload"],
                evidence=["IndexError: string index out of range at line 144"],
            )
        ],
        primary_suspect="hyp-1",
        investigation_strategy="Reproduce boundary condition in sandbox container then test proposed offset.",
    )
    provider.queue_structured(valid_plan)

    parsed, raw_resp = await provider.generate_structured(
        prompt="Propose investigation hypotheses",
        response_schema=InvestigationPlan,
    )

    assert isinstance(parsed, InvestigationPlan)
    assert parsed.primary_suspect == "hyp-1"
    assert len(parsed.hypotheses) == 1
    assert parsed.hypotheses[0].confidence == 0.85
    assert raw_resp.is_mock is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_structured_task_plan() -> None:
    """Verify structured output parsing for TaskPlan."""
    provider = MockModelProvider()
    valid_task_plan = TaskPlan(
        plan_id="plan-42",
        goal="Resolve buffer overflow in network protocol handler",
        steps=[
            TaskStep(
                step_number=1,
                action="reproduce_bug",
                target="tests/reproduce_overflow.py",
                expected_outcome="Test fails with SegmentationFault or IndexError",
            ),
            TaskStep(
                step_number=2,
                action="apply_patch",
                target="src/network/buffer.py",
                expected_outcome="Buffer bound check prevents out-of-range memory access",
                dependencies=[1],
            ),
        ],
        estimated_risk="low",
        rollback_plan="Revert git worktree commit using git reset --hard HEAD~1",
    )
    provider.queue_structured(valid_task_plan)

    parsed, _ = await provider.generate_structured(
        prompt="Formulate plan",
        response_schema=TaskPlan,
    )
    assert parsed.plan_id == "plan-42"
    assert len(parsed.steps) == 2
    assert parsed.estimated_risk == "low"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_structured_proposed_patch() -> None:
    """Verify structured output parsing for ProposedPatch."""
    provider = MockModelProvider()
    patch = ProposedPatch(
        patch_id="patch-001",
        file_path="src/network/buffer.py",
        unified_diff="--- a/buffer.py\n+++ b/buffer.py\n@@ -10,1 +10,1 @@\n-if len > max:\n+if len >= max:",
        rationale="Off-by-one check allowed index equal to capacity to overwrite adjacent memory.",
        reproduction_test_verified=True,
        breaking_change_risk="none",
    )
    provider.queue_structured(patch)

    parsed, _ = await provider.generate_structured(
        prompt="Draft patch",
        response_schema=ProposedPatch,
    )
    assert parsed.patch_id == "patch-001"
    assert parsed.reproduction_test_verified is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_structured_review_and_final_report() -> None:
    """Verify ReviewReport and FinalReport structured parsing."""
    provider = MockModelProvider()
    report = FinalReport(
        report_id="rep-100",
        run_id="run-abc-123",
        status="resolved",
        executive_summary="Successfully localized and patched off-by-one buffer overrun.",
        root_cause_analysis="Comparison operator > instead of >= allowed fence-post overwrite.",
        patches_applied=["src/network/buffer.py"],
        tests_passed=["test_boundary_conditions", "test_regression_suite"],
        tests_failed=[],
        estimated_total_cost_usd=0.045,
        lessons_learned=["Enforce static boundary analysis in CI pipeline."],
    )
    provider.queue_structured(report)

    parsed, _ = await provider.generate_structured(
        prompt="Generate final summary",
        response_schema=FinalReport,
    )
    assert parsed.status == "resolved"
    assert parsed.estimated_total_cost_usd == 0.045


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rejects_malformed_json_response() -> None:
    """Verify that unparseable/corrupted JSON output raises ModelInvalidResponseError."""
    provider = MockModelProvider()
    provider.queue_structured("INVALID JSON { unquoted_key: ")

    with pytest.raises(ModelInvalidResponseError) as exc_info:
        await provider.generate_structured(
            prompt="Return json",
            response_schema=InvestigationPlan,
        )

    assert "Failed to decode model JSON output" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rejects_schema_violating_structured_response() -> None:
    """Verify that structured responses missing required fields or with invalid values are rejected.

    Ensures invalid structured output is NEVER silently replaced with arbitrary defaults.
    """
    provider = MockModelProvider()
    # Missing required 'rollback_plan' and negative step_number
    invalid_dict = {
        "plan_id": "plan-1",
        "goal": "Test goal",
        "steps": [
            {
                "step_number": -5,  # Invalid: ge=1 required
                "action": "act",
                "target": "tgt",
                "expected_outcome": "out",
            }
        ],
        "estimated_risk": "extreme",  # Invalid literal
    }
    provider.queue_structured(invalid_dict)

    with pytest.raises(ModelInvalidResponseError) as exc_info:
        await provider.generate_structured(
            prompt="Generate task plan",
            response_schema=TaskPlan,
        )

    assert "failed schema validation" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_handling() -> None:
    """Verify that model timeout raises ModelTimeoutError."""
    provider = MockModelProvider(max_retries=0)
    provider.should_timeout = True

    with pytest.raises(ModelTimeoutError) as exc_info:
        await provider.generate(prompt="Long running query", timeout=0.01)

    assert "timed out" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cooperative_cancellation() -> None:
    """Verify that cancellation token halts execution before or during request."""
    provider = MockModelProvider()
    token = CancellationToken()
    token.cancel("User aborted debugging session")

    with pytest.raises(ModelCancelledError) as exc_info:
        await provider.generate(prompt="Investigate", cancellation_token=token)

    assert "cancelled" in str(exc_info.value).lower()
    assert "User aborted debugging session" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_retry_and_exhaustion() -> None:
    """Verify transient rate limit errors retry with backoff and exhaust cleanly."""
    provider = MockModelProvider(max_retries=2)
    # Simulate 2 rate limits, then success
    provider.should_rate_limit_count = 2

    # Should succeed after 2 retries
    response = await provider.generate(prompt="Retryable call")
    assert response.content is not None

    # Now simulate 4 rate limits (exceeding max_retries of 2)
    provider.should_rate_limit_count = 4
    with pytest.raises(ModelRateLimitError) as exc_info:
        await provider.generate(prompt="Failing call")

    assert "rate limit" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_authentication_error_fails_immediately() -> None:
    """Verify authentication failures do not retry endlessly."""
    provider = MockModelProvider(max_retries=3)
    provider.should_auth_fail = True

    with pytest.raises(ModelAuthenticationError) as exc_info:
        await provider.generate(prompt="Call with invalid key")

    assert "authentication failure" in str(exc_info.value).lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_budget_call_limit_enforced() -> None:
    """Verify maximum model calls limit is strictly enforced."""
    limits = BudgetLimits(max_calls=2)
    tracker = BudgetTracker(limits=limits)
    provider = MockModelProvider(budget_tracker=tracker)

    # Call 1: succeeds
    await provider.generate(prompt="Call 1")
    # Call 2: succeeds
    await provider.generate(prompt="Call 2")

    # Call 3: must exceed budget
    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await provider.generate(prompt="Call 3")

    assert "Exceeded maximum model calls" in str(exc_info.value)
    assert tracker.calls_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_budget_token_limit_enforced() -> None:
    """Verify maximum token consumption limit is enforced."""
    limits = BudgetLimits(max_total_tokens=100)
    tracker = BudgetTracker(limits=limits)
    provider = MockModelProvider(
        budget_tracker=tracker,
        simulated_usage=ModelUsage(prompt_tokens=60, completion_tokens=50, total_tokens=110),
    )

    # Call 1 consumes 110 tokens (exceeding 100)
    await provider.generate(prompt="Call 1")

    # Call 2 should be rejected pre-call
    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await provider.generate(prompt="Call 2")

    assert "Exceeded maximum token budget" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_budget_cost_limit_enforced() -> None:
    """Verify maximum estimated cost limit is enforced."""
    limits = BudgetLimits(max_estimated_cost_usd=0.05)
    tracker = BudgetTracker(limits=limits)
    provider = MockModelProvider(
        budget_tracker=tracker,
        simulated_usage=ModelUsage(
            prompt_tokens=1000,
            completion_tokens=5000,
            total_tokens=6000,
            estimated_cost_usd=0.06,  # Exceeds $0.05
            is_cost_estimated=True,
        ),
    )

    # First call records cost $0.06
    await provider.generate(prompt="Expensive call")

    # Second call rejected
    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await provider.generate(prompt="Next call")

    assert "Exceeded estimated cost budget" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_budget_response_size_limit_enforced() -> None:
    """Verify response size byte limit rejects oversized responses."""
    limits = BudgetLimits(max_response_bytes=100)
    tracker = BudgetTracker(limits=limits)
    provider = MockModelProvider(
        budget_tracker=tracker,
        default_response_text="A" * 500,  # 500 bytes exceeds 100 bytes limit
    )

    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await provider.generate(prompt="Oversized response test")

    assert "response size (500 bytes) exceeded" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_budget_elapsed_time_limit_enforced() -> None:
    """Verify elapsed time limit rejects execution after timeout window."""
    limits = BudgetLimits(max_elapsed_seconds=0.01)
    tracker = BudgetTracker(limits=limits)
    provider = MockModelProvider(budget_tracker=tracker)

    # Wait for time limit to expire
    await asyncio.sleep(0.02)

    with pytest.raises(ModelBudgetExceededError) as exc_info:
        await provider.generate(prompt="Timed out run")

    assert "Exceeded maximum execution time" in str(exc_info.value)
