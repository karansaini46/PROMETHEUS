"""Model artifact management, packaging, integrity verification, and export.

Structures experiment artifacts including model checkpoints, tokenizer configurations,
evaluation reports, inference benchmarks, and cryptographic checksum manifests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prometheus_ai.learning.lab.config import ExperimentConfig
from prometheus_ai.learning.lab.metrics import (
    InferenceBenchmarkMetrics,
    ValidationMetrics,
)
from prometheus_ai.learning.lab.tokenizer import BaseTokenizer
from prometheus_ai.learning.lab.trainer import TrainingSummary


@dataclass
class ArtifactManifest:
    """Cryptographic manifest documenting all assets belonging to an experiment run."""

    experiment_id: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    dataset_name: str = ""
    dataset_version: str = ""
    files: dict[str, str] = field(default_factory=dict)  # relative_path -> sha256_hash
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactManager:
    """Manages the creation, manifest tracking, and verification of experiment artifacts."""

    def __init__(self, base_artifacts_dir: Path | str) -> None:
        self.base_dir = Path(base_artifacts_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_experiment_dir(self, experiment_id: str) -> Path:
        """Return directory path dedicated to a specific experiment."""
        exp_dir = self.base_dir / "experiments" / experiment_id
        exp_dir.mkdir(parents=True, exist_ok=True)
        return exp_dir

    def package_run(
        self,
        config: ExperimentConfig,
        tokenizer: BaseTokenizer,
        model_summary: dict[str, Any],
        training_summary: TrainingSummary,
        evaluation_metrics: ValidationMetrics | None = None,
        benchmark_metrics: InferenceBenchmarkMetrics | None = None,
    ) -> Path:
        """Package all run outputs into an experiment artifact directory."""
        exp_dir = self.get_experiment_dir(config.experiment_id)

        # 1. Config JSON
        config_path = exp_dir / "config.json"
        config.save_json(config_path)

        # 2. Tokenizer vocab
        tokenizer_path = exp_dir / "tokenizer.json"
        tokenizer.save(tokenizer_path)

        # 3. Model Architecture Summary
        model_summary_path = exp_dir / "model_summary.json"
        model_summary_path.write_text(json.dumps(model_summary, indent=2), encoding="utf-8")

        # 4. Training Summary
        train_sum_path = exp_dir / "training_summary.json"
        train_sum_path.write_text(
            json.dumps(training_summary.to_dict(), indent=2), encoding="utf-8"
        )

        # 5. Evaluation Report
        if evaluation_metrics:
            eval_path = exp_dir / "evaluation_report.json"
            eval_path.write_text(
                json.dumps(evaluation_metrics.to_dict(), indent=2), encoding="utf-8"
            )

        # 6. Inference Benchmark
        if benchmark_metrics:
            bench_path = exp_dir / "inference_benchmark.json"
            bench_path.write_text(
                json.dumps(benchmark_metrics.to_dict(), indent=2), encoding="utf-8"
            )

        # 7. Generate SUMMARY.md
        summary_md_path = exp_dir / "SUMMARY.md"
        summary_md_path.write_text(
            self._render_summary_markdown(
                config=config,
                model_summary=model_summary,
                training_summary=training_summary,
                evaluation_metrics=evaluation_metrics,
                benchmark_metrics=benchmark_metrics,
            ),
            encoding="utf-8",
        )

        # 8. Compute cryptographic manifest
        files_map: dict[str, str] = {}
        for p in sorted(exp_dir.rglob("*")):
            if p.is_file() and p.name != "manifest.json":
                rel = str(p.relative_to(exp_dir))
                files_map[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

        manifest = ArtifactManifest(
            experiment_id=config.experiment_id,
            dataset_name=config.dataset.name,
            dataset_version=config.dataset.version,
            files=files_map,
            metadata={"description": config.description},
        )
        (exp_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
        )

        return exp_dir

    def verify_integrity(self, experiment_id: str) -> bool:
        """Verify the SHA-256 checksums of all files against the manifest."""
        exp_dir = self.get_experiment_dir(experiment_id)
        manifest_path = exp_dir / "manifest.json"
        if not manifest_path.exists():
            return False

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files_map: dict[str, str] = manifest_data.get("files", {})

        for rel_path, expected_hash in files_map.items():
            target_file = exp_dir / rel_path
            if not target_file.exists():
                return False
            actual_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                return False

        return True

    def _render_summary_markdown(
        self,
        config: ExperimentConfig,
        model_summary: dict[str, Any],
        training_summary: TrainingSummary,
        evaluation_metrics: ValidationMetrics | None,
        benchmark_metrics: InferenceBenchmarkMetrics | None,
    ) -> str:
        lines = [
            f"# Experiment Report: {config.experiment_id}",
            "",
            f"**Description**: {config.description}",
            f"**Dataset**: `{config.dataset.name}` (v{config.dataset.version})",
            f"**Origin**: {config.dataset.origin} | **License**: {config.dataset.license}",
            "",
            "## Model Architecture",
            f"- Parameters: {model_summary.get('total_parameters', 'N/A'):,} (Trainable: {model_summary.get('trainable_parameters', 'N/A'):,})",
            f"- Layers: {model_summary.get('n_layers')} | Heads: {model_summary.get('n_heads')} | Dim: {model_summary.get('d_model')}",
            f"- Context Length: {model_summary.get('context_length')} tokens | Vocab: {model_summary.get('vocab_size')}",
            "",
            "## Training Outcomes",
            f"- Steps Completed: {training_summary.total_steps} / {config.training.max_steps}",
            f"- Final Train Loss: {training_summary.final_train_loss:.4f}",
            f"- Best Val Loss: {training_summary.best_val_loss if training_summary.best_val_loss is not None else 'N/A'}",
            f"- Best Val Perplexity: {training_summary.best_val_perplexity if training_summary.best_val_perplexity is not None else 'N/A'}",
            f"- Total Duration: {training_summary.duration_seconds:.2f}s",
            f"- Interrupted: {training_summary.interrupted}",
            "",
        ]

        if evaluation_metrics:
            lines.extend(
                [
                    "## Held-Out Evaluation",
                    f"- Split: `{evaluation_metrics.split_name}`",
                    f"- Loss: {evaluation_metrics.val_loss:.4f}",
                    f"- Perplexity: {evaluation_metrics.val_perplexity:.4f}",
                    f"- Next-Token Accuracy: {evaluation_metrics.token_accuracy * 100:.2f}%",
                    "",
                ]
            )

        if benchmark_metrics:
            lines.extend(
                [
                    "## Inference Benchmark",
                    f"- Mean Latency: {benchmark_metrics.latency_ms_mean:.2f} ms",
                    f"- p50 / p90 / p99: {benchmark_metrics.latency_ms_p50:.2f} / {benchmark_metrics.latency_ms_p90:.2f} / {benchmark_metrics.latency_ms_p99:.2f} ms",
                    f"- Throughput: {benchmark_metrics.throughput_tokens_per_sec:.2f} tokens/sec",
                    f"- Device: `{benchmark_metrics.device}` | Batch Size: {benchmark_metrics.batch_size}",
                    "",
                ]
            )

        lines.extend(
            [
                "## Small-Scale Experiment Limitations",
                "- **No Emergence**: Small transformers (<1M parameters) do not exhibit general reasoning capabilities.",
                "- **Domain-Restricted**: Evaluations reflect pattern matching over small synthetic distributions.",
                "- **Metric Comparability**: Perplexities and losses are only comparable when using the identical dataset and tokenizer.",
                "",
            ]
        )
        return "\n".join(lines)
