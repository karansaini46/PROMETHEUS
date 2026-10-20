"""Machine Learning Engineering Subsystem Package."""

from dataclasses import dataclass

from prometheus_ai.learning import lab, strategy
from prometheus_ai.learning.lab import (
    ArtifactManager,
    CancellationToken,
    CharTokenizer,
    CheckpointManager,
    CompactDecoderOnlyTransformer,
    DataLeakageError,
    DatasetConfig,
    DatasetRegistry,
    DatasetValidationError,
    DatasetValidator,
    ExperimentConfig,
    ExperimentRunner,
    LabEvaluator,
    LabTrainer,
    ModelComparator,
    ModelConfig,
    TrainingConfig,
)
from prometheus_ai.learning.memory_experiment import (
    ConditionResult,
    ExperimentTask,
    MemoryExperimentReport,
    MemoryExperimentRunner,
)
from prometheus_ai.learning.strategy import (
    ActionOutcome,
    BaseToolSelectionPolicy,
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceededError,
    ContextualBanditToolPolicy,
    DatasetSplitter,
    EvaluationTask,
    ExecutionTrace,
    ExperienceInformedToolPolicy,
    ExperimentConclusion,
    ExperimentReport,
    LLMToolPolicy,
    PolicyEvaluationMetrics,
    PolicyPromotionRecord,
    PolicyRegistry,
    PolicyStatus,
    RuleBasedToolPolicy,
    SafePolicyExecutor,
    StateFeaturizer,
    StrategyExperimentRunner,
    TaskCategory,
    ToolSelectionContext,
    ToolSelectionDecision,
    TraceCollector,
    TraceSanitizer,
    UnapprovedPromotionError,
    UnauthorizedToolError,
    compute_reward,
)


@dataclass
class TrainingDatasetConfig:
    """Configuration for offline supervised training datasets."""

    dataset_name: str
    target_architecture: str
    split_ratio: float = 0.8
    min_trajectory_reward: float = 1.0


__all__ = [
    "ActionOutcome",
    "ArtifactManager",
    "BaseToolSelectionPolicy",
    "BudgetConfig",
    "BudgetEnforcer",
    "BudgetExceededError",
    "CancellationToken",
    "CharTokenizer",
    "CheckpointManager",
    "CompactDecoderOnlyTransformer",
    "ConditionResult",
    "ContextualBanditToolPolicy",
    "DataLeakageError",
    "DatasetConfig",
    "DatasetRegistry",
    "DatasetSplitter",
    "DatasetValidationError",
    "DatasetValidator",
    "EvaluationTask",
    "ExecutionTrace",
    "ExperienceInformedToolPolicy",
    "ExperimentConclusion",
    "ExperimentConfig",
    "ExperimentReport",
    "ExperimentRunner",
    "ExperimentTask",
    "LLMToolPolicy",
    "LabEvaluator",
    "LabTrainer",
    "MemoryExperimentReport",
    "MemoryExperimentRunner",
    "ModelComparator",
    "ModelConfig",
    "PolicyEvaluationMetrics",
    "PolicyPromotionRecord",
    "PolicyRegistry",
    "PolicyStatus",
    "RuleBasedToolPolicy",
    "SafePolicyExecutor",
    "StateFeaturizer",
    "StrategyExperimentRunner",
    "TaskCategory",
    "ToolSelectionContext",
    "ToolSelectionDecision",
    "TraceCollector",
    "TraceSanitizer",
    "TrainingConfig",
    "TrainingDatasetConfig",
    "UnapprovedPromotionError",
    "UnauthorizedToolError",
    "compute_reward",
    "lab",
    "strategy",
]
