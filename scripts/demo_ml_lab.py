"""Interactive demonstration script for the PROMETHEUS Machine Learning Laboratory.

Executes:
1. Baseline model configuration & training run.
2. One-factor-at-a-time variation run (depth: 1 layer vs 2 layers).
3. Held-out test evaluation & inference benchmarking.
4. Cryptographic artifact manifest packaging.
5. Strict comparative reporting with compatibility audit.
"""

from __future__ import annotations

from pathlib import Path

from prometheus_ai.learning.lab import (
    ExperimentRunner,
    create_baseline_config,
)


def main() -> None:
    artifacts_root = Path("artifacts/ml_lab")
    artifacts_root.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PROMETHEUS Machine Learning Laboratory - Demonstration Run")
    print("=" * 70)

    runner = ExperimentRunner(base_artifacts_dir=artifacts_root)

    # 1. Baseline Run (2 layers, 2 heads, d_model=64)
    base_config = create_baseline_config(
        experiment_id="baseline_2layers",
        seed=42,
        max_steps=30,
    )
    print("\n[1/3] Executing Baseline Training Run (2 layers, d_model=64)...")
    res_base = runner.run_experiment(base_config)
    print(f" -> Baseline completed in {res_base.training_summary.duration_seconds:.2f}s")
    print(f" -> Final Train Loss: {res_base.training_summary.final_train_loss:.4f}")
    print(f" -> Test Loss: {res_base.evaluation_metrics.val_loss:.4f} | Perplexity: {res_base.evaluation_metrics.val_perplexity:.2f}")
    print(f" -> Inference Latency (p50): {res_base.benchmark_metrics.latency_ms_p50:.2f} ms")
    print(f" -> Artifacts saved to: {res_base.artifact_dir}")

    # 2. One-Factor Variation (1 layer)
    print("\n[2/3] Executing One-Factor Variation (n_layers: 2 -> 1)...")
    comp_report = runner.run_one_factor_comparison(
        base_config=base_config,
        factor_name="n_layers",
        variation_value=1,
        variation_id="variation_1layer",
    )
    print(" -> Variation run completed and compared.")

    # 3. Print Comparison Report Markdown
    print("\n[3/3] Comparative Analysis & Limitations Report:")
    print("-" * 70)
    print(comp_report.to_markdown())
    print("-" * 70)
    print("\nDemonstration completed successfully.")


if __name__ == "__main__":
    main()
