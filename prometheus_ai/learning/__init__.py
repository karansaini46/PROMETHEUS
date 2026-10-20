"""Machine Learning Engineering Subsystem Package."""

from dataclasses import dataclass

from prometheus_ai.learning import lab
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


@dataclass
class TrainingDatasetConfig:
    """Configuration for offline supervised training datasets."""

    dataset_name: str
    target_architecture: str
    split_ratio: float = 0.8
    min_trajectory_reward: float = 1.0


__all__ = [
    "ArtifactManager",
    "CancellationToken",
    "CharTokenizer",
    "CheckpointManager",
    "CompactDecoderOnlyTransformer",
    "ConditionResult",
    "DataLeakageError",
    "DatasetConfig",
    "DatasetRegistry",
    "DatasetValidationError",
    "DatasetValidator",
    "ExperimentConfig",
    "ExperimentRunner",
    "ExperimentTask",
    "LabEvaluator",
    "LabTrainer",
    "MemoryExperimentReport",
    "MemoryExperimentRunner",
    "ModelComparator",
    "ModelConfig",
    "TrainingConfig",
    "TrainingDatasetConfig",
    "lab",
]
