"""Comprehensive unit tests for the PROMETHEUS Machine Learning Laboratory.

Validates:
- Dataset registration, validation, splitting, and data-leakage prevention.
- Tokenizer round-trips and special token handling.
- Transformer forward pass, loss calculation, and autoregressive generation.
- Training loop on synthetic datasets with step capping.
- Atomic checkpointing and exact state resumption.
- Held-out evaluation and inference latency/throughput benchmarking.
- Cooperative training cancellation and recovery.
- Error handling for malformed datasets.
- Experiment artifact packaging, manifest hashing, and model configuration comparison.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import torch

from prometheus_ai.learning.lab.artifacts import ArtifactManager
from prometheus_ai.learning.lab.checkpoint import CheckpointManager
from prometheus_ai.learning.lab.comparison import (
    ComparisonRunRecord,
    IncompatibleEvaluationError,
    ModelComparator,
)
from prometheus_ai.learning.lab.config import (
    DatasetConfig,
    ModelConfig,
    TrainingConfig,
)
from prometheus_ai.learning.lab.dataset import (
    DataLeakageError,
    DatasetRegistry,
    DatasetValidationError,
    DatasetValidator,
)
from prometheus_ai.learning.lab.evaluator import LabEvaluator
from prometheus_ai.learning.lab.experiments import (
    ExperimentRunner,
    create_baseline_config,
    create_one_factor_variation,
)
from prometheus_ai.learning.lab.metrics import TrainingLogger
from prometheus_ai.learning.lab.tokenizer import CharTokenizer
from prometheus_ai.learning.lab.trainer import CancellationToken, LabTrainer
from prometheus_ai.learning.lab.transformer import CompactDecoderOnlyTransformer


@pytest.fixture
def tmp_lab_dir() -> Generator[Path, None, None]:
    """Fixture providing an isolated temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_corpus() -> list[str]:
    """Fixture providing a deterministic tiny dataset for tests."""
    return [
        "BUG: ZeroDivisionError. FIX: avoid division by zero",
        "BUG: NameError. FIX: define variable before usage",
        "BUG: IndexError. FIX: check list bounds before indexing",
        "BUG: KeyError. FIX: use dict.get with default",
        "BUG: TypeError. FIX: convert string to integer",
        "BUG: AttributeError. FIX: verify object is not None",
    ]


@pytest.mark.unit
def test_tokenizer_roundtrip() -> None:
    """Verify tokenizer encodes and decodes accurately including special tokens."""
    tokenizer = CharTokenizer()
    text = "BUG: ZeroDivisionError"
    encoded = tokenizer.encode(text, add_special_tokens=True)

    assert encoded[0] == tokenizer.bos_token_id
    assert encoded[-1] == tokenizer.eos_token_id

    decoded = tokenizer.decode(encoded, skip_special_tokens=True)
    assert decoded == text

    # Serialization test
    t_dict = tokenizer.to_dict()
    restored = CharTokenizer.from_dict(t_dict)
    assert restored.vocab_size == tokenizer.vocab_size
    assert restored.decode(encoded, skip_special_tokens=True) == text


@pytest.mark.unit
def test_dataset_validation_and_splitting(tmp_lab_dir: Path, sample_corpus: list[str]) -> None:
    """Verify dataset registration, partition ratios, and metadata tracking."""
    registry = DatasetRegistry(tmp_lab_dir / "datasets")
    config = DatasetConfig(
        name="test_debug",
        version="1.0.0",
        origin="Unit Test",
        license="Apache-2.0",
        intended_use="Testing",
        split_ratios=(0.6, 0.2, 0.2),
    )

    splits = registry.register(config=config, samples=sample_corpus)
    assert len(splits.train) >= 1
    assert len(splits.val) >= 1
    assert len(splits.test) >= 1
    assert splits.total_count == len(sample_corpus)
    assert splits.metadata.sha256_hash != ""

    # Check persistence and retrieval
    retrieved = registry.get("test_debug", "1.0.0")
    assert retrieved.metadata.sha256_hash == splits.metadata.sha256_hash
    assert len(retrieved.train) == len(splits.train)


@pytest.mark.unit
def test_dataset_leakage_detection() -> None:
    """Verify that DataLeakageError is raised if train and evaluation splits overlap."""
    train = ["BUG: NameError. FIX: define var", "BUG: TypeError. FIX: cast type"]
    val = ["BUG: NameError. FIX: define var"]  # Leaked!
    test = ["BUG: IndexError. FIX: check len"]

    with pytest.raises(DataLeakageError) as exc_info:
        DatasetValidator.verify_no_leakage(train, val, test)
    assert "Data leakage detected" in str(exc_info.value)


@pytest.mark.unit
def test_malformed_dataset_rejection() -> None:
    """Verify that DatasetValidationError is raised for empty or malformed inputs."""
    with pytest.raises(DatasetValidationError):
        DatasetValidator.validate_raw_texts([])  # Empty list

    with pytest.raises(DatasetValidationError):
        DatasetValidator.validate_raw_texts([""])  # Empty string

    with pytest.raises(DatasetValidationError):
        DatasetValidator.validate_raw_texts(["Valid text", "Bad\x00NullByte"])  # Null byte


@pytest.mark.unit
def test_transformer_forward_and_shapes() -> None:
    """Verify compact decoder-only transformer parameter initialization, forward shapes, and loss."""
    cfg = ModelConfig(
        vocab_size=64,
        context_length=32,
        n_layers=2,
        n_heads=2,
        d_model=32,
        d_ff=64,
        dropout=0.0,
    )
    model = CompactDecoderOnlyTransformer(cfg, pad_token_id=0)

    # Check parameter count
    summary = model.get_summary()
    assert summary["trainable_parameters"] > 0
    assert summary["n_layers"] == 2

    # Forward without targets
    x = torch.randint(0, cfg.vocab_size, (2, 16))
    logits, loss = model(x)
    assert logits.shape == (2, 16, cfg.vocab_size)
    assert loss is None

    # Forward with targets
    y = torch.randint(0, cfg.vocab_size, (2, 16))
    logits, loss = model(x, targets=y)
    assert loss is not None
    assert loss.item() > 0.0


@pytest.mark.unit
def test_training_loop_synthetic_dataset(tmp_lab_dir: Path, sample_corpus: list[str]) -> None:
    """Verify that the training loop executes, logs steps, and produces decreasing or finite loss."""
    registry = DatasetRegistry(tmp_lab_dir / "datasets")
    ds_config = DatasetConfig(name="synth_tiny", split_ratios=(0.6, 0.2, 0.2))
    splits = registry.register(ds_config, sample_corpus)

    tokenizer = CharTokenizer()
    m_config = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        context_length=32,
        n_layers=1,
        n_heads=2,
        d_model=32,
        d_ff=64,
    )
    model = CompactDecoderOnlyTransformer(m_config)

    t_config = TrainingConfig(
        batch_size=2,
        learning_rate=1e-3,
        max_steps=15,
        max_epochs=10,
        eval_every_steps=5,
        checkpoint_every_steps=10,
    )

    ckpt_dir = tmp_lab_dir / "checkpoints"
    ckpt_mgr = CheckpointManager(ckpt_dir)
    logger = TrainingLogger(tmp_lab_dir / "train.jsonl")

    trainer = LabTrainer(
        model=model,
        tokenizer=tokenizer,
        config=t_config,
        splits=splits,
        checkpoint_manager=ckpt_mgr,
        logger=logger,
    )

    summary = trainer.train()

    assert summary.total_steps == 15
    assert summary.final_train_loss > 0.0
    assert summary.interrupted is False
    assert len(logger.step_history) == 15
    assert len(logger.validation_history) >= 2
    assert ckpt_mgr.get_latest_checkpoint() is not None


@pytest.mark.unit
def test_checkpoint_saving_and_resumption(tmp_lab_dir: Path, sample_corpus: list[str]) -> None:
    """Verify that training state can be saved and accurately resumed from checkpoint."""
    registry = DatasetRegistry(tmp_lab_dir / "datasets")
    splits = registry.register(DatasetConfig(name="ckpt_test"), sample_corpus)

    tokenizer = CharTokenizer()
    m_config = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        context_length=32,
        n_layers=1,
        n_heads=2,
        d_model=32,
        d_ff=64,
    )
    model = CompactDecoderOnlyTransformer(m_config)
    ckpt_dir = tmp_lab_dir / "checkpoints"
    ckpt_mgr = CheckpointManager(ckpt_dir)

    # Train phase 1 for 10 steps
    t_config_1 = TrainingConfig(max_steps=10, eval_every_steps=5, checkpoint_every_steps=10)
    trainer_1 = LabTrainer(
        model=model,
        tokenizer=tokenizer,
        config=t_config_1,
        splits=splits,
        checkpoint_manager=ckpt_mgr,
    )
    sum_1 = trainer_1.train()
    assert sum_1.total_steps == 10

    latest_ckpt = ckpt_mgr.get_latest_checkpoint()
    assert latest_ckpt is not None

    # Train phase 2: resume with a new model instance up to 20 steps
    model_resumed = CompactDecoderOnlyTransformer(m_config)
    t_config_2 = TrainingConfig(max_steps=20, eval_every_steps=5, checkpoint_every_steps=10)
    trainer_2 = LabTrainer(
        model=model_resumed,
        tokenizer=tokenizer,
        config=t_config_2,
        splits=splits,
        checkpoint_manager=ckpt_mgr,
    )
    sum_2 = trainer_2.train(resume_from=latest_ckpt)

    assert sum_2.total_steps == 20
    assert sum_2.final_train_loss > 0.0


@pytest.mark.unit
def test_training_cancellation(tmp_lab_dir: Path, sample_corpus: list[str]) -> None:
    """Verify cooperative cancellation stops training cleanly and records interruption state."""
    registry = DatasetRegistry(tmp_lab_dir / "datasets")
    splits = registry.register(DatasetConfig(name="cancel_test"), sample_corpus)

    tokenizer = CharTokenizer()
    m_config = ModelConfig(vocab_size=tokenizer.vocab_size, context_length=32, d_model=32)
    model = CompactDecoderOnlyTransformer(m_config)

    t_config = TrainingConfig(max_steps=50)
    cancel_token = CancellationToken()

    # Pre-cancel before run or during step
    cancel_token.cancel("Abort requested by test harness")

    trainer = LabTrainer(
        model=model,
        tokenizer=tokenizer,
        config=t_config,
        splits=splits,
        cancellation_token=cancel_token,
        checkpoint_manager=CheckpointManager(tmp_lab_dir / "ckpts"),
    )

    summary = trainer.train()
    assert summary.interrupted is True
    assert "Abort requested" in (summary.interruption_reason or "")
    assert summary.total_steps < 50


@pytest.mark.unit
def test_evaluation_and_inference_benchmarking(sample_corpus: list[str]) -> None:
    """Verify held-out evaluation metrics, perplexity, and inference latency percentiles."""
    tokenizer = CharTokenizer()
    m_config = ModelConfig(
        vocab_size=tokenizer.vocab_size,
        context_length=32,
        n_layers=1,
        n_heads=2,
        d_model=32,
        d_ff=64,
    )
    model = CompactDecoderOnlyTransformer(m_config)

    splits = DatasetRegistry().register(DatasetConfig(name="eval_test"), sample_corpus)
    test_ds = LabTrainer(
        model=model,
        tokenizer=tokenizer,
        config=TrainingConfig(),
        splits=splits,
    ).val_dataset

    test_loader = torch.utils.data.DataLoader(test_ds, batch_size=2)

    eval_metrics = LabEvaluator.evaluate(
        model=model,
        dataloader=test_loader,
        tokenizer=tokenizer,
        split_name="test",
        sample_prompts=["BUG: NameError"],
    )

    assert eval_metrics.val_loss > 0.0
    assert eval_metrics.val_perplexity >= 1.0
    assert 0.0 <= eval_metrics.token_accuracy <= 1.0
    assert len(eval_metrics.sample_generations) == 1

    # Inference benchmarking
    bench = LabEvaluator.benchmark_inference(
        model=model,
        tokenizer=tokenizer,
        prompt="BUG: ",
        max_new_tokens=16,
        iterations=4,
        warmup_iterations=1,
    )

    assert bench.latency_ms_mean > 0.0
    assert bench.latency_ms_p50 > 0.0
    assert bench.throughput_tokens_per_sec > 0.0
    assert bench.total_tokens > 16


@pytest.mark.unit
def test_model_comparator_validation() -> None:
    """Verify that ModelComparator enforces compatibility checks and rejects mismatched datasets."""
    r1 = ComparisonRunRecord(
        experiment_id="exp-1",
        description="Base 1 layer",
        dataset_name="debug_v1",
        dataset_version="1.0.0",
        dataset_hash="hash123",
        tokenizer_type="CharTokenizer",
        vocab_size=128,
        context_length=64,
        n_layers=1,
        n_heads=2,
        d_model=64,
        total_parameters=20000,
        final_train_loss=2.5,
        best_val_loss=2.6,
        best_val_perplexity=13.4,
        token_accuracy=0.45,
        mean_latency_ms=10.0,
        throughput_tokens_per_sec=200.0,
    )

    # Compatible run 2 (one factor changed: n_layers = 2)
    r2 = ComparisonRunRecord(
        experiment_id="exp-2",
        description="Varied 2 layers",
        dataset_name="debug_v1",
        dataset_version="1.0.0",
        dataset_hash="hash123",
        tokenizer_type="CharTokenizer",
        vocab_size=128,
        context_length=64,
        n_layers=2,
        n_heads=2,
        d_model=64,
        total_parameters=35000,
        final_train_loss=2.1,
        best_val_loss=2.2,
        best_val_perplexity=9.0,
        token_accuracy=0.55,
        mean_latency_ms=18.0,
        throughput_tokens_per_sec=120.0,
    )

    report = ModelComparator.compare_runs([r1, r2])
    assert report.is_directly_comparable is True
    assert len(report.factor_variations) == 1
    assert "n_layers" in report.factor_variations[0]["factor"]

    # Incompatible run 3 (mismatched dataset)
    r3 = ComparisonRunRecord(
        experiment_id="exp-3",
        description="Mismatched dataset",
        dataset_name="different_corpus",
        dataset_version="2.0.0",
        dataset_hash="different_hash",
        tokenizer_type="CharTokenizer",
        vocab_size=128,
        context_length=64,
        n_layers=1,
        n_heads=2,
        d_model=64,
        total_parameters=20000,
        final_train_loss=1.5,
        best_val_loss=1.6,
        best_val_perplexity=4.9,
    )

    with pytest.raises(IncompatibleEvaluationError):
        ModelComparator.compare_runs([r1, r3], strict_dataset_matching=True)


@pytest.mark.unit
def test_end_to_end_experiment_runner(tmp_lab_dir: Path) -> None:
    """Verify complete lifecycle: baseline creation, factor variation, artifact export, and manifest verification."""
    runner = ExperimentRunner(tmp_lab_dir)
    base_cfg = create_baseline_config("baseline_run", max_steps=12)

    result = runner.run_experiment(base_cfg)

    # Validate output structure
    assert result.training_summary.total_steps == 12
    assert result.evaluation_metrics.val_loss > 0.0
    assert result.benchmark_metrics.latency_ms_mean > 0.0

    # Verify artifacts and cryptographic manifest
    mgr = ArtifactManager(tmp_lab_dir)
    assert mgr.verify_integrity("baseline_run") is True

    # Validate one-factor variation
    var_cfg = create_one_factor_variation(
        base_config=base_cfg,
        factor_name="n_layers",
        new_value=1,
        new_experiment_id="variation_1layer",
    )
    assert var_cfg.model.n_layers == 1
    assert var_cfg.model.d_model == base_cfg.model.d_model  # Unchanged factor
