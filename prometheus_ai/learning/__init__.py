"""Machine Learning Engineering Subsystem Package."""

from dataclasses import dataclass

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
    "ConditionResult",
    "ExperimentTask",
    "MemoryExperimentReport",
    "MemoryExperimentRunner",
    "TrainingDatasetConfig",
]
