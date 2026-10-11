"""Validated Pydantic Schemas for Agent Structured Outputs.

Enforces strict structural contracts for:
- Investigation hypotheses
- Task plans
- Tool requests
- Proposed patches
- Review findings
- Final reports

Malformed responses are strictly rejected; no silent arbitrary defaulting is permitted.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ==============================================================================
# 1. Investigation Hypotheses Schemas
# ==============================================================================


class InvestigationHypothesis(BaseModel):
    """A candidate hypothesis regarding root cause for a reported failure."""

    hypothesis_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the hypothesis (e.g., 'hyp-1')",
    )
    title: str = Field(..., min_length=3, description="Brief descriptive title")
    description: str = Field(
        ...,
        min_length=10,
        description="Detailed causal explanation of why the failure occurs",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    suspected_components: list[str] = Field(
        ...,
        min_length=1,
        description="Modules, packages, or files suspected to contain the fault",
    )
    validation_steps: list[str] = Field(
        ...,
        min_length=1,
        description="Concrete steps or test assertions to prove or disprove this hypothesis",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Observed stack traces, error messages, or AST symbols supporting this hypothesis",
    )


class InvestigationPlan(BaseModel):
    """Collection of prioritized hypotheses with an overall exploration strategy."""

    hypotheses: list[InvestigationHypothesis] = Field(
        ...,
        min_length=1,
        description="List of candidate hypotheses to explore",
    )
    primary_suspect: str = Field(
        ...,
        min_length=1,
        description="The ID of the top-ranked hypothesis",
    )
    investigation_strategy: str = Field(
        ...,
        min_length=10,
        description="Strategic plan for sequential or parallel hypothesis verification",
    )


# ==============================================================================
# 2. Task Plans Schemas
# ==============================================================================


class TaskStep(BaseModel):
    """An individual atomic action within an autonomous debugging plan."""

    step_number: int = Field(..., ge=1, description="1-indexed sequence order")
    action: str = Field(..., min_length=3, description="Action verb/name (e.g., 'reproduce_bug')")
    target: str = Field(..., min_length=1, description="Target file, symbol, or container")
    expected_outcome: str = Field(
        ...,
        min_length=5,
        description="Success criteria verifying step completion",
    )
    dependencies: list[int] = Field(
        default_factory=list,
        description="List of preceding step numbers that must succeed first",
    )


class TaskPlan(BaseModel):
    """Structured roadmap for diagnosing and resolving an issue."""

    plan_id: str = Field(..., min_length=1, description="Unique plan identifier")
    goal: str = Field(..., min_length=5, description="High-level engineering objective")
    steps: list[TaskStep] = Field(
        ...,
        min_length=1,
        description="Ordered sequence of execution steps",
    )
    estimated_risk: Literal["low", "medium", "high"] = Field(
        ...,
        description="Risk level of side-effects or regressions",
    )
    rollback_plan: str = Field(
        ...,
        min_length=10,
        description="Procedure to revert changes if verification fails",
    )

    @field_validator("steps")
    @classmethod
    def validate_step_sequence(cls, steps: list[TaskStep]) -> list[TaskStep]:
        step_numbers = [s.step_number for s in steps]
        if len(step_numbers) != len(set(step_numbers)):
            raise ValueError("Duplicate step numbers found in TaskPlan")
        return steps


# ==============================================================================
# 3. Tool Requests Schemas
# ==============================================================================


class AgentToolRequest(BaseModel):
    """Structured request by an agent to execute a tool."""

    request_id: str = Field(..., min_length=1, description="Identifier for this invocation request")
    tool_name: str = Field(..., min_length=1, description="Registered name of target tool")
    arguments: dict[str, str | int | float | bool | list[str] | dict[str, str]] = Field(
        ...,
        description="Tool execution parameters conforming to the tool's schema",
    )
    intent: str = Field(
        ...,
        min_length=5,
        description="Detailed engineering intent describing why this tool is needed",
    )


# ==============================================================================
# 4. Proposed Patches Schemas
# ==============================================================================


class ProposedPatch(BaseModel):
    """A proposed code patch fixing the diagnosed root cause."""

    patch_id: str = Field(..., min_length=1, description="Unique patch identifier")
    file_path: str = Field(..., min_length=1, description="Relative path of the target file")
    unified_diff: str = Field(
        ...,
        min_length=5,
        description="Unified diff format patch string (e.g. starting with '--- ' and '+++ ')",
    )
    rationale: str = Field(
        ...,
        min_length=10,
        description="Explanation of why this patch resolves the bug without side-effects",
    )
    reproduction_test_verified: bool = Field(
        ...,
        description="Whether a minimal reproduction test confirmed the fix",
    )
    breaking_change_risk: Literal["none", "low", "medium", "high"] = Field(
        ...,
        description="Assessment of potential backwards-incompatible behavior changes",
    )


# ==============================================================================
# 5. Review Findings Schemas
# ==============================================================================


class ReviewFinding(BaseModel):
    """An individual finding from an automated code or security review."""

    finding_id: str = Field(..., min_length=1, description="Unique finding ID")
    file_path: str = Field(..., min_length=1, description="Path to the reviewed file")
    line_number: int | None = Field(default=None, ge=1, description="Line number if localized")
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        ...,
        description="Impact severity rating",
    )
    category: Literal["correctness", "security", "performance", "style", "testability"] = Field(
        ...,
        description="Category of the finding",
    )
    message: str = Field(..., min_length=10, description="Detailed explanation of the issue")
    suggested_fix: str | None = Field(
        default=None,
        description="Specific recommended code revision or patch",
    )


class ReviewReport(BaseModel):
    """Aggregated review findings with final decision."""

    findings: list[ReviewFinding] = Field(
        default_factory=list,
        description="All findings discovered during inspection",
    )
    verdict: Literal["approved", "changes_requested", "blocked"] = Field(
        ...,
        description="Overall review verdict",
    )
    summary: str = Field(..., min_length=10, description="Executive summary of the review")


# ==============================================================================
# 6. Final Report Schema
# ==============================================================================


class FinalReport(BaseModel):
    """Authoritative outcome report for a completed PROMETHEUS debugging run."""

    report_id: str = Field(..., min_length=1, description="Unique report identifier")
    run_id: str = Field(..., min_length=1, description="PROMETHEUS Run ID")
    status: Literal["resolved", "partially_resolved", "failed", "aborted"] = Field(
        ...,
        description="Final termination status of the run",
    )
    executive_summary: str = Field(
        ...,
        min_length=10,
        description="High-level narrative of what occurred",
    )
    root_cause_analysis: str = Field(
        ...,
        min_length=10,
        description="Comprehensive technical analysis of the underlying fault",
    )
    patches_applied: list[str] = Field(
        default_factory=list,
        description="List of file paths modified by applied patches",
    )
    tests_passed: list[str] = Field(
        default_factory=list,
        description="List of test names or paths passing in the verification sandbox",
    )
    tests_failed: list[str] = Field(
        default_factory=list,
        description="List of test names or paths failing in the verification sandbox",
    )
    estimated_total_cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Cumulative estimated USD cost of all model calls",
    )
    lessons_learned: list[str] = Field(
        default_factory=list,
        description="Long-term learnings or architectural advice for future runs",
    )
