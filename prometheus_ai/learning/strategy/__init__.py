"""Experimental Strategy Learning and Tool Selection Subsystem for PROMETHEUS.

Scope & Principles:
-------------------
- Does NOT claim language model self-modification or autonomous intelligence expansion.
- Narrow, empirical objective: Optimize tool-selection and investigation strategies
  using recorded execution outcomes.
- Implements and compares:
  1. Fixed Rule-Based Baseline
  2. LLM-Selected Baseline
  3. Experience-Informed Strategy (Empirical UCB and LinUCB Contextual Bandit)
- Enforces strict zero-leakage between training, tuning, and held-out evaluation tasks.
- Enforces safety: sandbox compliance, execution budgets, and human approval for promotion.
"""

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
    PolicyEvaluationMetrics,
    StrategyExperimentRunner,
    TaskRunResult,
)
from prometheus_ai.learning.strategy.governance import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceededError,
    PolicyEntry,
    PolicyPromotionRecord,
    PolicyRegistry,
    PolicyStatus,
    SafePolicyExecutor,
    UnapprovedPromotionError,
    UnauthorizedToolError,
)
from prometheus_ai.learning.strategy.policy import (
    BaseToolSelectionPolicy,
    ContextualBanditToolPolicy,
    ExperienceInformedToolPolicy,
    LLMToolPolicy,
    RewardWeights,
    RuleBasedToolPolicy,
    StateFeaturizer,
    compute_reward,
)
from prometheus_ai.learning.strategy.schema import (
    ActionOutcome,
    ExecutionTrace,
    TaskCategory,
    ToolSelectionContext,
    ToolSelectionDecision,
)

__all__ = [
    "ActionOutcome",
    "BaseToolSelectionPolicy",
    "BudgetConfig",
    "BudgetEnforcer",
    "BudgetExceededError",
    "ContextualBanditToolPolicy",
    "DataLeakageError",
    "DatasetSplitter",
    "EvaluationTask",
    "ExecutionTrace",
    "ExperienceInformedToolPolicy",
    "ExperimentConclusion",
    "ExperimentReport",
    "LLMToolPolicy",
    "PolicyEntry",
    "PolicyEvaluationMetrics",
    "PolicyPromotionRecord",
    "PolicyRegistry",
    "PolicyStatus",
    "RewardWeights",
    "RuleBasedToolPolicy",
    "SafePolicyExecutor",
    "StateFeaturizer",
    "StrategyExperimentRunner",
    "TaskCategory",
    "TaskRunResult",
    "ToolSelectionContext",
    "ToolSelectionDecision",
    "TraceCollector",
    "TraceSanitizer",
    "UnapprovedPromotionError",
    "UnauthorizedToolError",
    "compute_reward",
]
