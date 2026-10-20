"""PROMETHEUS Machine Learning Laboratory Subsystem.

A clean, self-contained educational machine learning engineering lab
for training, evaluating, checkpointing, and benchmarking small transformer models.
Kept strictly separate from the autonomous debugging runtime.
"""

from prometheus_ai.learning.lab.artifacts import (
    ArtifactManager,
    ArtifactManifest,
)
from prometheus_ai.learning.lab.checkpoint import (
    CheckpointManager,
    CheckpointMetadata,
)
from prometheus_ai.learning.lab.comparison import (
    ComparisonReport,
    ComparisonRunRecord,
    IncompatibleEvaluationError,
    ModelComparator,
)
from prometheus_ai.learning.lab.config import (
    DatasetConfig,
    EvaluationConfig,
    ExperimentConfig,
    ModelConfig,
    TrainingConfig,
)
from prometheus_ai.learning.lab.dataset import (
    DataLeakageError,
    DatasetMetadata,
    DatasetRegistry,
    DatasetSplits,
    DatasetValidationError,
    DatasetValidator,
    TokenizedDataset,
    create_synthetic_debug_corpus,
)
from prometheus_ai.learning.lab.evaluator import LabEvaluator
from prometheus_ai.learning.lab.experiments import (
    ExperimentResult,
    ExperimentRunner,
    create_baseline_config,
    create_one_factor_variation,
)
from prometheus_ai.learning.lab.metrics import (
    InferenceBenchmarkMetrics,
    StepMetrics,
    TrainingLogger,
    ValidationMetrics,
    calculate_perplexity,
    get_peak_memory_mb,
)
from prometheus_ai.learning.lab.tokenizer import (
    BaseTokenizer,
    CharTokenizer,
)
from prometheus_ai.learning.lab.trainer import (
    CancellationToken,
    LabTrainer,
    TrainingInterruptedError,
    TrainingSummary,
)
from prometheus_ai.learning.lab.transformer import (
    CausalSelfAttention,
    CompactDecoderOnlyTransformer,
    TransformerBlock,
)

__all__ = [
    "ArtifactManager",
    "ArtifactManifest",
    "BaseTokenizer",
    "CancellationToken",
    "CausalSelfAttention",
    "CharTokenizer",
    "CheckpointManager",
    "CheckpointMetadata",
    "CompactDecoderOnlyTransformer",
    "ComparisonReport",
    "ComparisonRunRecord",
    "DataLeakageError",
    "DatasetConfig",
    "DatasetMetadata",
    "DatasetRegistry",
    "DatasetSplits",
    "DatasetValidationError",
    "DatasetValidator",
    "EvaluationConfig",
    "ExperimentConfig",
    "ExperimentResult",
    "ExperimentRunner",
    "IncompatibleEvaluationError",
    "InferenceBenchmarkMetrics",
    "LabEvaluator",
    "LabTrainer",
    "ModelComparator",
    "ModelConfig",
    "StepMetrics",
    "TokenizedDataset",
    "TrainingConfig",
    "TrainingInterruptedError",
    "TrainingLogger",
    "TrainingSummary",
    "TransformerBlock",
    "ValidationMetrics",
    "calculate_perplexity",
    "create_baseline_config",
    "create_one_factor_variation",
    "create_synthetic_debug_corpus",
    "get_peak_memory_mb",
]
