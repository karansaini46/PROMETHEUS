"""Configuration schemas for the PROMETHEUS Machine Learning Laboratory.

Provides reproducible, validated configuration objects for models, training,
datasets, evaluation, and experiments.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelConfig:
    """Configuration for compact decoder-only transformer model."""

    vocab_size: int = 128
    context_length: int = 64
    n_layers: int = 2
    n_heads: int = 2
    d_model: int = 64
    d_ff: int = 128
    dropout: float = 0.1
    tie_weights: bool = True

    def validate(self) -> None:
        """Validate model hyperparameter bounds and invariants."""
        if self.vocab_size < 4:
            raise ValueError(f"vocab_size must be >= 4, got {self.vocab_size}")
        if self.context_length < 4:
            raise ValueError(f"context_length must be >= 4, got {self.context_length}")
        if self.n_layers < 1:
            raise ValueError(f"n_layers must be >= 1, got {self.n_layers}")
        if self.n_heads < 1:
            raise ValueError(f"n_heads must be >= 1, got {self.n_heads}")
        if self.d_model % self.n_heads != 0:
            raise ValueError(
                f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})"
            )
        if self.d_ff < 1:
            raise ValueError(f"d_ff must be >= 1, got {self.d_ff}")
        if not (0.0 <= self.dropout < 1.0):
            raise ValueError(f"dropout must be in [0.0, 1.0), got {self.dropout}")

    def to_dict(self) -> dict[str, Any]:
        """Convert model configuration to dictionary."""
        return asdict(self)


@dataclass
class TrainingConfig:
    """Configuration for small-model training runs and resource controls."""

    batch_size: int = 4
    learning_rate: float = 1e-3
    weight_decay: float = 0.01
    max_steps: int = 100
    max_epochs: int = 50
    warmup_steps: int = 10
    grad_clip: float = 1.0
    eval_every_steps: int = 20
    checkpoint_every_steps: int = 50
    max_train_time_seconds: float | None = None
    seed: int = 42
    device: str = "cpu"

    def validate(self) -> None:
        """Validate training parameters and resource constraints."""
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")
        if self.learning_rate <= 0:
            raise ValueError(f"learning_rate must be > 0, got {self.learning_rate}")
        if self.max_steps < 1:
            raise ValueError(f"max_steps must be >= 1, got {self.max_steps}")
        if self.max_epochs < 1:
            raise ValueError(f"max_epochs must be >= 1, got {self.max_epochs}")
        if self.checkpoint_every_steps < 1:
            raise ValueError(
                f"checkpoint_every_steps must be >= 1, got {self.checkpoint_every_steps}"
            )
        if self.max_train_time_seconds is not None and self.max_train_time_seconds <= 0:
            raise ValueError("max_train_time_seconds must be positive if specified")

    def to_dict(self) -> dict[str, Any]:
        """Convert training configuration to dictionary."""
        return asdict(self)


@dataclass
class DatasetConfig:
    """Metadata and partitioning settings for registered datasets."""

    name: str = "debug_synthetic_v1"
    version: str = "1.0.0"
    origin: str = "PROMETHEUS Synthetic Debugging Corpus"
    license: str = "Apache-2.0"
    intended_use: str = "Educational small-model experimentation and unit testing"
    split_ratios: tuple[float, float, float] = (0.8, 0.1, 0.1)  # train, val, test
    max_samples: int | None = None

    def validate(self) -> None:
        """Validate split ratios and metadata integrity."""
        if not self.name or not self.version:
            raise ValueError("Dataset name and version must be non-empty strings")
        if len(self.split_ratios) != 3:
            raise ValueError("split_ratios must have exactly 3 values: (train, val, test)")
        r_sum = sum(self.split_ratios)
        if not (0.99 <= r_sum <= 1.01):
            raise ValueError(f"split_ratios must sum to 1.0, got sum={r_sum:.4f}")
        for r in self.split_ratios:
            if r <= 0:
                raise ValueError("All split ratios must be strictly positive")
        if self.max_samples is not None and self.max_samples < 1:
            raise ValueError("max_samples must be >= 1 if provided")

    def to_dict(self) -> dict[str, Any]:
        """Convert dataset configuration to dictionary."""
        return asdict(self)


@dataclass
class EvaluationConfig:
    """Configuration for model evaluation and generation benchmarking."""

    batch_size: int = 4
    generate_samples: int = 2
    max_generate_tokens: int = 32
    temperature: float = 0.8
    top_k: int = 20

    def validate(self) -> None:
        """Validate evaluation parameters."""
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if self.max_generate_tokens < 1:
            raise ValueError("max_generate_tokens must be >= 1")
        if self.temperature < 0.0:
            raise ValueError("temperature must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Convert evaluation configuration to dictionary."""
        return asdict(self)


@dataclass
class ExperimentConfig:
    """Comprehensive, reproducible experiment configuration."""

    experiment_id: str
    description: str
    model: ModelConfig = field(default_factory=ModelConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    dataset: DatasetConfig = field(default_factory=DatasetConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    random_seed: int = 42
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate all sub-configurations."""
        if not self.experiment_id:
            raise ValueError("experiment_id must not be empty")
        self.model.validate()
        self.training.validate()
        self.dataset.validate()
        self.evaluation.validate()

    def to_dict(self) -> dict[str, Any]:
        """Convert experiment configuration to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize configuration to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save_json(self, file_path: Path | str) -> None:
        """Persist configuration to a JSON file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentConfig:
        """Instantiate an ExperimentConfig from a dictionary."""
        model = ModelConfig(**data.get("model", {}))
        training = TrainingConfig(**data.get("training", {}))
        dataset_data = dict(data.get("dataset", {}))
        if "split_ratios" in dataset_data and isinstance(dataset_data["split_ratios"], list):
            dataset_data["split_ratios"] = tuple(dataset_data["split_ratios"])
        dataset = DatasetConfig(**dataset_data)
        evaluation = EvaluationConfig(**data.get("evaluation", {}))
        return cls(
            experiment_id=data["experiment_id"],
            description=data.get("description", ""),
            model=model,
            training=training,
            dataset=dataset,
            evaluation=evaluation,
            random_seed=data.get("random_seed", 42),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentConfig:
        """Instantiate an ExperimentConfig from JSON text."""
        return cls.from_dict(json.loads(json_str))
