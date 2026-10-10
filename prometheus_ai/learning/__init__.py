"""Machine Learning Engineering Subsystem Package."""

from dataclasses import dataclass


@dataclass
class TrainingDatasetConfig:
    """Configuration for offline supervised training datasets."""

    dataset_name: str
    target_architecture: str
    split_ratio: float = 0.8
    min_trajectory_reward: float = 1.0
