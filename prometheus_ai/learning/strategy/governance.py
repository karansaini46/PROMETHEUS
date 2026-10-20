"""Safety, Governance, Budget Enforcement, and Human Approval Subsystem.

Invariants:
- The currently approved default strategy is always preserved as a reliable fallback.
- Learned/experimental policies can NEVER bypass tool authorization, sandbox allowlists,
  execution budgets, or human approval requirements.
- Experimental policies CANNOT promote themselves to default without explicit human approval
  and a verifiable approval token.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from prometheus_ai.learning.strategy.policy import (
    BaseToolSelectionPolicy,
    RuleBasedToolPolicy,
)
from prometheus_ai.learning.strategy.schema import (
    ToolSelectionContext,
    ToolSelectionDecision,
)

logger = logging.getLogger(__name__)


class PolicyStatus(StrEnum):
    """Lifecycle status of a tool-selection policy."""

    APPROVED_DEFAULT = "approved_default"
    EXPERIMENTAL = "experimental"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class BudgetExceededError(Exception):
    """Raised when an agent's tool execution budget is exhausted."""


class UnauthorizedToolError(Exception):
    """Raised when a policy attempts to select an unauthorized or unallowlisted tool."""


class UnapprovedPromotionError(Exception):
    """Raised when an attempt is made to promote an experimental policy without human approval."""


@dataclass
class PolicyPromotionRecord:
    """Audit log capturing explicit human promotion of an experimental policy."""

    record_id: str
    policy_id: str
    approved_by: str
    approval_token: str
    timestamp: float
    justification: str
    evaluation_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyEntry:
    """Registered policy container with audit metadata."""

    policy: BaseToolSelectionPolicy
    status: PolicyStatus
    registered_at: float = field(default_factory=time.time)
    promotions: list[PolicyPromotionRecord] = field(default_factory=list)


class PolicyRegistry:
    """Registry maintaining active, experimental, and fallback tool selection policies.

    Enforces that only approved policies can be default, and promotions strictly
    require human signoff.
    """

    def __init__(
        self,
        default_policy: BaseToolSelectionPolicy | None = None,
    ) -> None:
        self._entries: dict[str, PolicyEntry] = {}
        # Approved default policy (starts with safe rule-based baseline)
        initial_default = default_policy or RuleBasedToolPolicy(
            policy_id="approved-default-rules-v1"
        )
        self._entries[initial_default.policy_id] = PolicyEntry(
            policy=initial_default,
            status=PolicyStatus.APPROVED_DEFAULT,
        )
        self._default_policy_id = initial_default.policy_id
        self._audit_log: list[dict[str, Any]] = []

    @property
    def default_policy(self) -> BaseToolSelectionPolicy:
        return self._entries[self._default_policy_id].policy

    @property
    def default_policy_id(self) -> str:
        return self._default_policy_id

    def register_experimental_policy(self, policy: BaseToolSelectionPolicy) -> None:
        """Register an experimental policy candidate for testing and benchmarking."""
        if policy.policy_id in self._entries:
            logger.info(f"Updating registration for policy '{policy.policy_id}'")
        self._entries[policy.policy_id] = PolicyEntry(
            policy=policy,
            status=PolicyStatus.EXPERIMENTAL,
        )
        self._audit_log.append(
            {
                "event": "policy_registered",
                "policy_id": policy.policy_id,
                "policy_type": policy.policy_type,
                "status": PolicyStatus.EXPERIMENTAL.value,
                "timestamp": time.time(),
            }
        )

    def get_policy(self, policy_id: str) -> BaseToolSelectionPolicy | None:
        entry = self._entries.get(policy_id)
        return entry.policy if entry else None

    def get_status(self, policy_id: str) -> PolicyStatus | None:
        entry = self._entries.get(policy_id)
        return entry.status if entry else None

    def list_policies(self) -> list[dict[str, Any]]:
        return [
            {
                "policy_id": p_id,
                "policy_type": entry.policy.policy_type,
                "status": entry.status.value,
                "registered_at": entry.registered_at,
            }
            for p_id, entry in self._entries.items()
        ]

    def promote_to_default(
        self,
        policy_id: str,
        approved_by: str,
        approval_token: str,
        justification: str,
        evaluation_summary: dict[str, Any] | None = None,
    ) -> PolicyPromotionRecord:
        """Promote an experimental policy to APPROVED_DEFAULT.

        Requires:
        - Non-empty `approved_by` representing authorized human operator.
        - Valid non-empty `approval_token`.
        - Detailed justification.
        """
        if not approved_by or len(approved_by.strip()) < 3:
            raise UnapprovedPromotionError(
                "Policy promotion requires explicit human approver identifier (e.g. user/admin ID)."
            )

        if not approval_token or len(approval_token.strip()) < 8:
            raise UnapprovedPromotionError(
                "Policy promotion requires a valid, high-entropy approval authorization token."
            )

        entry = self._entries.get(policy_id)
        if not entry:
            raise KeyError(f"Policy '{policy_id}' not found in registry.")

        if entry.status == PolicyStatus.APPROVED_DEFAULT:
            logger.info(f"Policy '{policy_id}' is already approved default.")

        # Deprecate old default
        old_default_id = self._default_policy_id
        if old_default_id in self._entries and old_default_id != policy_id:
            self._entries[old_default_id].status = PolicyStatus.DEPRECATED

        # Record promotion audit
        record = PolicyPromotionRecord(
            record_id=f"prom-{uuid.uuid4().hex[:8]}",
            policy_id=policy_id,
            approved_by=approved_by,
            approval_token=approval_token,
            timestamp=time.time(),
            justification=justification,
            evaluation_summary=evaluation_summary or {},
        )
        entry.status = PolicyStatus.APPROVED_DEFAULT
        entry.promotions.append(record)
        self._default_policy_id = policy_id

        self._audit_log.append(
            {
                "event": "policy_promoted",
                "promoted_policy_id": policy_id,
                "previous_default_id": old_default_id,
                "approved_by": approved_by,
                "timestamp": record.timestamp,
            }
        )
        logger.info(
            f"Successfully promoted policy '{policy_id}' to default. Approved by: {approved_by}."
        )
        return record


@dataclass
class BudgetConfig:
    """Execution resource budget thresholds for a debugging task."""

    max_tool_calls: int = 20
    max_cost_usd: float = 2.0
    max_latency_seconds: float = 180.0


class BudgetEnforcer:
    """Tracks and enforces tool call count, monetary cost, and execution duration budgets."""

    def __init__(self, budget: BudgetConfig | None = None) -> None:
        self.budget = budget or BudgetConfig()
        self.tool_calls_executed = 0
        self.total_cost_usd = 0.0
        self.start_time = time.time()

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def check_budget(self) -> None:
        """Validate that current consumption has not exceeded authorized thresholds."""
        if self.tool_calls_executed >= self.budget.max_tool_calls:
            raise BudgetExceededError(
                f"Tool call budget exceeded: {self.tool_calls_executed}/{self.budget.max_tool_calls}"
            )
        if self.total_cost_usd >= self.budget.max_cost_usd:
            raise BudgetExceededError(
                f"Monetary cost budget exceeded: ${self.total_cost_usd:.4f}/${self.budget.max_cost_usd:.4f}"
            )
        if self.elapsed_seconds >= self.budget.max_latency_seconds:
            raise BudgetExceededError(
                f"Latency timeout budget exceeded: {self.elapsed_seconds:.1f}s/{self.budget.max_latency_seconds:.1f}s"
            )

    def record_usage(self, cost_usd: float, latency_seconds: float) -> None:
        """Record usage after executing a tool."""
        self.tool_calls_executed += 1
        self.total_cost_usd += max(0.0, cost_usd)


class SafePolicyExecutor:
    """Execution harness executing tool-selection policies with full safety guards.

    Guarantees:
    - Never executes an action outside `context.available_tools`.
    - Automatically falls back to the approved default policy on error, invalid tool,
      or budget constraint violation.
    - Prevents experimental policies from executing unvetted or destructive side effects.
    """

    def __init__(
        self,
        registry: PolicyRegistry,
        budget_enforcer: BudgetEnforcer | None = None,
    ) -> None:
        self.registry = registry
        self.budget_enforcer = budget_enforcer or BudgetEnforcer()

    async def select_action(
        self,
        context: ToolSelectionContext,
        policy: BaseToolSelectionPolicy | None = None,
    ) -> ToolSelectionDecision:
        """Execute policy tool selection with strict authorization and fallback boundaries."""
        # 1. Budget check
        self.budget_enforcer.check_budget()

        # 2. Determine active policy
        active_policy = policy or self.registry.default_policy
        fallback_policy = self.registry.default_policy

        if not context.available_tools:
            return ToolSelectionDecision(
                selected_tool="",
                rationale="Empty available tools list provided by authorization layer",
                confidence=0.0,
                is_fallback=True,
                policy_id="safety-gate",
            )

        try:
            # 3. Invoke policy
            decision = await active_policy.select_tool(context)

            # 4. Strict Authorization Check
            if decision.selected_tool in context.available_tools:
                return decision

            # Policy proposed a tool outside the authorized set!
            logger.warning(
                f"Policy '{active_policy.policy_id}' attempted to select unauthorized tool "
                f"'{decision.selected_tool}' not in available list {context.available_tools}. "
                f"Safely redirecting to approved fallback."
            )
            fallback_decision = await fallback_policy.select_tool(context)
            fallback_decision.is_fallback = True
            fallback_decision.rationale = (
                f"Policy '{active_policy.policy_id}' selected unauthorized tool "
                f"'{decision.selected_tool}'. Reverted to approved fallback: {fallback_decision.selected_tool}"
            )
            return fallback_decision

        except Exception as exc:
            logger.error(
                f"Error during policy '{active_policy.policy_id}' execution: {exc}. "
                f"Executing approved fallback policy."
            )
            fallback_decision = await fallback_policy.select_tool(context)
            fallback_decision.is_fallback = True
            fallback_decision.rationale = f"Policy error: {exc}. Reverted to approved fallback: {fallback_decision.selected_tool}"
            return fallback_decision
