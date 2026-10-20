"""Rigorous model configuration comparison and experiment delta analysis.

Enforces dataset and tokenizer compatibility checks before comparing metrics,
preventing invalid direct comparisons across incompatible evaluation domains.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class IncompatibleEvaluationError(Exception):
    """Raised when an attempt is made to directly equate metrics from incompatible evaluations."""


@dataclass
class ComparisonRunRecord:
    """Summary record of an individual experiment run for comparative analysis."""

    experiment_id: str
    description: str
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    tokenizer_type: str
    vocab_size: int
    context_length: int
    n_layers: int
    n_heads: int
    d_model: int
    total_parameters: int
    final_train_loss: float
    best_val_loss: float | None
    best_val_perplexity: float | None
    token_accuracy: float | None = None
    mean_latency_ms: float | None = None
    throughput_tokens_per_sec: float | None = None
    duration_seconds: float = 0.0


@dataclass
class ComparisonReport:
    """Detailed comparative evaluation report across multiple model configurations."""

    runs: list[ComparisonRunRecord]
    is_directly_comparable: bool
    compatibility_notes: list[str] = field(default_factory=list)
    factor_variations: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the comparison as a clean GitHub-flavored markdown report."""
        lines = [
            "# Model Configuration Comparison Report",
            "",
            f"**Directly Comparable**: {'YES' if self.is_directly_comparable else 'NO (Incompatible Conditions)'}",
            "",
        ]

        if self.compatibility_notes:
            lines.append("### Compatibility Audit Notes")
            for note in self.compatibility_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Markdown comparison table
        lines.extend(
            [
                "| Experiment ID | Layers | Dim | Params | Val Loss | Perplexity | Acc (%) | Latency (ms) | Throughput (tok/s) |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
        )

        for r in self.runs:
            val_loss_str = f"{r.best_val_loss:.4f}" if r.best_val_loss is not None else "N/A"
            perp_str = (
                f"{r.best_val_perplexity:.2f}" if r.best_val_perplexity is not None else "N/A"
            )
            acc_str = f"{r.token_accuracy * 100:.1f}%" if r.token_accuracy is not None else "N/A"
            lat_str = f"{r.mean_latency_ms:.2f}" if r.mean_latency_ms is not None else "N/A"
            tp_str = (
                f"{r.throughput_tokens_per_sec:.1f}"
                if r.throughput_tokens_per_sec is not None
                else "N/A"
            )

            lines.append(
                f"| `{r.experiment_id}` | {r.n_layers} | {r.d_model} | {r.total_parameters:,} | "
                f"{val_loss_str} | {perp_str} | {acc_str} | {lat_str} | {tp_str} |"
            )

        lines.append("")

        if self.factor_variations:
            lines.append("### Factor Variation Analysis")
            for fv in self.factor_variations:
                lines.append(f"- **{fv['factor']}**: {fv['comparison_detail']}")
            lines.append("")

        lines.extend(
            [
                "### Limitations of Small-Scale Experiments",
                "- **No Emergence**: Compact models (e.g., <1M parameters) perform simple statistical n-gram or pattern memorization and lack reasoning, planning, or general understanding.",
                "- **Evaluation Integrity**: Perplexity is strictly domain- and vocabulary-dependent. A lower loss on a smaller vocabulary does not denote superior intelligence.",
                "- **Resource Context**: Sub-second execution enables fast iteration on architectures, tokenizers, and scheduling algorithms within local resource bounds.",
            ]
        )

        return "\n".join(lines)


class ModelComparator:
    """Audits and contrasts experiment configurations and their training/benchmark metrics."""

    @staticmethod
    def load_run_record(exp_dir: Path | str) -> ComparisonRunRecord:
        """Extract a ComparisonRunRecord from an experiment artifact folder."""
        path = Path(exp_dir)
        config_data = json.loads((path / "config.json").read_text(encoding="utf-8"))
        model_sum = json.loads((path / "model_summary.json").read_text(encoding="utf-8"))
        train_sum = json.loads((path / "training_summary.json").read_text(encoding="utf-8"))

        eval_path = path / "evaluation_report.json"
        eval_data = json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.exists() else {}

        bench_path = path / "inference_benchmark.json"
        bench_data = (
            json.loads(bench_path.read_text(encoding="utf-8")) if bench_path.exists() else {}
        )

        manifest_path = path / "manifest.json"
        manifest_data = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        )

        return ComparisonRunRecord(
            experiment_id=config_data["experiment_id"],
            description=config_data.get("description", ""),
            dataset_name=config_data["dataset"]["name"],
            dataset_version=config_data["dataset"]["version"],
            dataset_hash=manifest_data.get("metadata", {}).get("dataset_hash", ""),
            tokenizer_type="CharTokenizer",
            vocab_size=model_sum.get("vocab_size", config_data["model"]["vocab_size"]),
            context_length=model_sum.get("context_length", config_data["model"]["context_length"]),
            n_layers=model_sum.get("n_layers", config_data["model"]["n_layers"]),
            n_heads=model_sum.get("n_heads", config_data["model"]["n_heads"]),
            d_model=model_sum.get("d_model", config_data["model"]["d_model"]),
            total_parameters=model_sum.get("total_parameters", 0),
            final_train_loss=train_sum.get("final_train_loss", 0.0),
            best_val_loss=train_sum.get("best_val_loss"),
            best_val_perplexity=train_sum.get("best_val_perplexity"),
            token_accuracy=eval_data.get("token_accuracy"),
            mean_latency_ms=bench_data.get("latency_ms_mean"),
            throughput_tokens_per_sec=bench_data.get("throughput_tokens_per_sec"),
            duration_seconds=train_sum.get("duration_seconds", 0.0),
        )

    @classmethod
    def compare_runs(
        cls,
        runs: list[ComparisonRunRecord],
        strict_dataset_matching: bool = True,
    ) -> ComparisonReport:
        """Compare multiple runs with strict compatibility validation."""
        if len(runs) < 2:
            raise ValueError("Comparison requires at least 2 experiment runs")

        base = runs[0]
        compatibility_notes: list[str] = []
        is_comparable = True

        for r in runs[1:]:
            if r.dataset_name != base.dataset_name or r.dataset_version != base.dataset_version:
                is_comparable = False
                note = (
                    f"Incompatible datasets: `{base.experiment_id}` used {base.dataset_name}@{base.dataset_version}, "
                    f"while `{r.experiment_id}` used {r.dataset_name}@{r.dataset_version}. "
                    "Loss and perplexity values are not directly comparable across different datasets."
                )
                compatibility_notes.append(note)
                if strict_dataset_matching:
                    raise IncompatibleEvaluationError(note)

            if r.vocab_size != base.vocab_size:
                is_comparable = False
                note = (
                    f"Incompatible vocabularies: `{base.experiment_id}` vocab_size={base.vocab_size}, "
                    f"while `{r.experiment_id}` vocab_size={r.vocab_size}. "
                    "Perplexity cannot be equated across disparate vocabulary partitions."
                )
                compatibility_notes.append(note)
                if strict_dataset_matching:
                    raise IncompatibleEvaluationError(note)

        if is_comparable:
            compatibility_notes.append(
                f"Valid comparison baseline: All {len(runs)} runs share identical dataset "
                f"`{base.dataset_name}@{base.dataset_version}` and vocab_size={base.vocab_size}."
            )

        # Factor variations analysis
        factor_variations = []
        for r in runs[1:]:
            diffs = []
            if r.n_layers != base.n_layers:
                diffs.append(f"n_layers: {base.n_layers} -> {r.n_layers}")
            if r.d_model != base.d_model:
                diffs.append(f"d_model: {base.d_model} -> {r.d_model}")
            if r.n_heads != base.n_heads:
                diffs.append(f"n_heads: {base.n_heads} -> {r.n_heads}")
            if r.context_length != base.context_length:
                diffs.append(f"context_length: {base.context_length} -> {r.context_length}")

            factor_str = ", ".join(diffs) if diffs else "Identical architecture"
            val_loss_delta = (
                f"{r.best_val_loss - base.best_val_loss:+.4f}"
                if (r.best_val_loss is not None and base.best_val_loss is not None)
                else "N/A"
            )
            factor_variations.append(
                {
                    "factor": factor_str,
                    "comparison_detail": (
                        f"{r.experiment_id} vs {base.experiment_id} | "
                        f"Params: {r.total_parameters:,} vs {base.total_parameters:,} | "
                        f"Val Loss Delta: {val_loss_delta}"
                    ),
                }
            )

        limitations = [
            "Toy scale experiments (parameters < 1M) do not exhibit emergent abilities.",
            "Synthetic educational datasets provide controlled testbeds, not general capabilities.",
            "Evaluation metrics must not be interpreted as evidence of human-level reasoning.",
        ]

        return ComparisonReport(
            runs=runs,
            is_directly_comparable=is_comparable,
            compatibility_notes=compatibility_notes,
            factor_variations=factor_variations,
            limitations=limitations,
        )
