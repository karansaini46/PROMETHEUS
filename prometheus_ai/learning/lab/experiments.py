"""Experiment runner and one-factor-at-a-time comparative suite for the ML Lab.

Provides baseline configurations, reproducible seed enforcement, factor variation,
and artifact publication.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from prometheus_ai.learning.lab.artifacts import ArtifactManager
from prometheus_ai.learning.lab.checkpoint import CheckpointManager
from prometheus_ai.learning.lab.comparison import ComparisonReport, ModelComparator
from prometheus_ai.learning.lab.config import (
    DatasetConfig,
    EvaluationConfig,
    ExperimentConfig,
    ModelConfig,
    TrainingConfig,
)
from prometheus_ai.learning.lab.dataset import (
    DatasetRegistry,
    DatasetSplits,
    create_synthetic_debug_corpus,
)
from prometheus_ai.learning.lab.evaluator import LabEvaluator
from prometheus_ai.learning.lab.metrics import (
    InferenceBenchmarkMetrics,
    TrainingLogger,
    ValidationMetrics,
)
from prometheus_ai.learning.lab.tokenizer import BaseTokenizer, CharTokenizer
from prometheus_ai.learning.lab.trainer import (
    CancellationToken,
    LabTrainer,
    TrainingSummary,
)
from prometheus_ai.learning.lab.transformer import CompactDecoderOnlyTransformer


@dataclass
class ExperimentResult:
    """Consolidated outcome of an executed experiment."""

    config: ExperimentConfig
    artifact_dir: Path
    model_summary: dict[str, Any]
    training_summary: TrainingSummary
    evaluation_metrics: ValidationMetrics
    benchmark_metrics: InferenceBenchmarkMetrics


def create_baseline_config(
    experiment_id: str = "exp_baseline_v1",
    seed: int = 42,
    max_steps: int = 40,
) -> ExperimentConfig:
    """Build a standard reproducible baseline experiment configuration.

    Default settings are kept small enough for resource-constrained local development.
    """
    return ExperimentConfig(
        experiment_id=experiment_id,
        description="Baseline educational compact decoder-only transformer",
        model=ModelConfig(
            vocab_size=128,
            context_length=64,
            n_layers=2,
            n_heads=2,
            d_model=64,
            d_ff=128,
            dropout=0.1,
            tie_weights=True,
        ),
        training=TrainingConfig(
            batch_size=4,
            learning_rate=1e-3,
            weight_decay=0.01,
            max_steps=max_steps,
            max_epochs=15,
            eval_every_steps=10,
            checkpoint_every_steps=20,
            seed=seed,
            device="cpu",
        ),
        dataset=DatasetConfig(
            name="debug_synthetic_v1",
            version="1.0.0",
            origin="PROMETHEUS Synthetic Debugging Corpus",
            license="Apache-2.0",
            intended_use="Educational small-model experimentation and unit testing",
            split_ratios=(0.8, 0.1, 0.1),
        ),
        evaluation=EvaluationConfig(
            batch_size=4,
            generate_samples=2,
            max_generate_tokens=24,
            temperature=0.7,
            top_k=15,
        ),
        random_seed=seed,
    )


def create_one_factor_variation(
    base_config: ExperimentConfig,
    factor_name: str,
    new_value: Any,
    new_experiment_id: str,
    description: str = "",
) -> ExperimentConfig:
    """Create a new ExperimentConfig changing exactly one factor from the baseline."""
    new_cfg = copy.deepcopy(base_config)
    new_cfg.experiment_id = new_experiment_id
    new_cfg.description = description or f"Variation of {factor_name}={new_value}"

    if hasattr(new_cfg.model, factor_name):
        setattr(new_cfg.model, factor_name, new_value)
    elif hasattr(new_cfg.training, factor_name):
        setattr(new_cfg.training, factor_name, new_value)
    elif hasattr(new_cfg.dataset, factor_name):
        setattr(new_cfg.dataset, factor_name, new_value)
    elif hasattr(new_cfg.evaluation, factor_name):
        setattr(new_cfg.evaluation, factor_name, new_value)
    elif factor_name == "random_seed":
        new_cfg.random_seed = int(new_value)
        new_cfg.training.seed = int(new_value)
    else:
        raise AttributeError(f"Factor '{factor_name}' is not recognized in ExperimentConfig")

    new_cfg.validate()
    return new_cfg


class ExperimentRunner:
    """Orchestrates end-to-end execution of machine learning experiments."""

    def __init__(self, base_artifacts_dir: Path | str) -> None:
        self.base_artifacts_dir = Path(base_artifacts_dir)
        self.base_artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_manager = ArtifactManager(self.base_artifacts_dir)
        self.dataset_registry = DatasetRegistry(self.base_artifacts_dir / "datasets")

    def run_experiment(
        self,
        config: ExperimentConfig,
        custom_corpus: list[str] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ExperimentResult:
        """Execute experiment: dataset preparation, training, evaluation, benchmark, and packaging."""
        config.validate()

        # Deterministic seed initialization
        torch.manual_seed(config.random_seed)
        random.seed(config.random_seed)

        # 1. Dataset Registration & Partitioning
        corpus = custom_corpus or create_synthetic_debug_corpus()
        splits: DatasetSplits = self.dataset_registry.register(
            config=config.dataset,
            samples=corpus,
            description="Synthetic educational debug examples",
        )

        # 2. Tokenizer initialization
        tokenizer: BaseTokenizer = CharTokenizer()
        # Adjust model vocab_size to match tokenizer
        config.model.vocab_size = tokenizer.vocab_size

        # 3. Model construction
        model = CompactDecoderOnlyTransformer(
            config=config.model,
            pad_token_id=tokenizer.pad_token_id,
        )
        model_summary = model.get_summary()

        # 4. Checkpoint & Logging setup
        exp_dir = self.artifact_manager.get_experiment_dir(config.experiment_id)
        ckpt_dir = exp_dir / "checkpoints"
        checkpoint_manager = CheckpointManager(ckpt_dir, max_to_keep=3)
        training_logger = TrainingLogger(exp_dir / "training_logs.jsonl")

        # 5. Training
        trainer = LabTrainer(
            model=model,
            tokenizer=tokenizer,
            config=config.training,
            splits=splits,
            experiment_config=config,
            checkpoint_manager=checkpoint_manager,
            logger=training_logger,
            cancellation_token=cancellation_token,
        )
        training_summary = trainer.train()

        # 6. Held-Out Evaluation on Test Partition
        test_dataset = trainer.val_dataset.__class__(
            texts=splits.test,
            tokenizer=tokenizer,
            context_length=config.model.context_length,
        )
        test_loader = trainer.val_loader.__class__(
            test_dataset,
            batch_size=min(config.evaluation.batch_size, max(len(test_dataset), 1)),
            shuffle=False,
        )

        sample_prompts = [
            "BUG: ZeroDivisionError",
            "BUG: NameError",
        ]
        eval_metrics = LabEvaluator.evaluate(
            model=model,
            dataloader=test_loader,
            tokenizer=tokenizer,
            device=config.training.device,
            split_name="test",
            sample_prompts=sample_prompts,
            max_generate_tokens=config.evaluation.max_generate_tokens,
        )

        # 7. Inference Benchmarking
        bench_metrics = LabEvaluator.benchmark_inference(
            model=model,
            tokenizer=tokenizer,
            prompt="BUG: ",
            max_new_tokens=config.evaluation.max_generate_tokens,
            batch_size=1,
            iterations=5,
            warmup_iterations=2,
            device=config.training.device,
        )

        # 8. Artifact Packaging & Manifest
        artifact_dir = self.artifact_manager.package_run(
            config=config,
            tokenizer=tokenizer,
            model_summary=model_summary,
            training_summary=training_summary,
            evaluation_metrics=eval_metrics,
            benchmark_metrics=bench_metrics,
        )

        return ExperimentResult(
            config=config,
            artifact_dir=artifact_dir,
            model_summary=model_summary,
            training_summary=training_summary,
            evaluation_metrics=eval_metrics,
            benchmark_metrics=bench_metrics,
        )

    def run_one_factor_comparison(
        self,
        base_config: ExperimentConfig,
        factor_name: str,
        variation_value: Any,
        variation_id: str,
        custom_corpus: list[str] | None = None,
    ) -> ComparisonReport:
        """Run a baseline and a one-factor variation, then generate a comparative analysis."""
        var_config = create_one_factor_variation(
            base_config=base_config,
            factor_name=factor_name,
            new_value=variation_value,
            new_experiment_id=variation_id,
        )

        res_base = self.run_experiment(base_config, custom_corpus=custom_corpus)
        res_var = self.run_experiment(var_config, custom_corpus=custom_corpus)

        rec_base = ModelComparator.load_run_record(res_base.artifact_dir)
        rec_var = ModelComparator.load_run_record(res_var.artifact_dir)

        report = ModelComparator.compare_runs([rec_base, rec_var])

        # Write comparative report artifact
        comp_path = (
            self.base_artifacts_dir / f"comparison_{base_config.experiment_id}_vs_{variation_id}.md"
        )
        comp_path.write_text(report.to_markdown(), encoding="utf-8")

        return report
