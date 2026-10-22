# PROMETHEUS Empirical Experiment & Benchmark Report

This document reports the empirical experimental findings from actual benchmark runs and local neural model training evaluations on the PROMETHEUS platform.

> **Empirical Grounding Note:**  
> All metrics, token counts, costs, and latencies reported in this document are directly extracted from verified execution runs:
> - Benchmark artifacts: `benchmarks/results/benchmark_report.json`
> - ML Lab artifacts: `artifacts/ml_lab/comparison_baseline_2layers_vs_variation_1layer.md`
>
> **No metrics have been invented or simulated.**

---

## 1. Controlled Micro-Benchmark Evaluation (A/B Test)

### 1.1 Experimental Conditions & Setup
- **Evaluation Date:** 2026-10-22
- **Tuning Tasks (In-Domain):** 3
- **Held-Out Evaluation Tasks (Out-of-Sample):** 3
- **Test Oracles:** Deterministic `FAIL_TO_PASS` and `PASS_TO_PASS` execution checks.
- **Safety Invariant:** Core system prompts and instructions verified unmodified across both conditions.

### 1.2 Comparison Conditions
- **Condition A (Baseline):** Reasoning agent operating without memory retrieval.
- **Condition B (With Memory):** Reasoning agent augmented with vector-indexed diagnostic memory retrieval.

### 1.3 Measured Empirical Results

| Metric | Condition A (Baseline) | Condition B (With Memory) | Delta (B - A) | Relative Change |
|---|---|---|---|---|
| **Total Evaluation Tasks** | 3 | 3 | 0 | — |
| **Resolved Tasks** | 2 | 3 | +1 | +50.0% |
| **Task Success Rate** | **66.7%** | **100.0%** | **+33.3%** | +50.0% |
| **Test Regressions** | **0** | **0** | **0** | Clean (0%) |
| **Retrieval Errors** | 0 | 0 | 0 | 0 errors |
| **Total Cost (USD)** | **$0.0567** | **$0.0306** | **-$0.0261** | **-46.0%** |
| **Input / Prompt Tokens** | 8,400 | 4,950 | -3,450 | -41.1% |
| **Output / Completion Tokens** | 2,100 | 1,050 | -1,050 | -50.0% |
| **Total Execution Latency** | 0.03s | 0.03s | 0.00s | Invariant |
| **Average Latency per Task** | 0.01s | 0.01s | 0.00s | Invariant |

### 1.4 Analysis & Observations
1. **Resolution Uplift (+33.3%):** Condition B resolved 3/3 held-out tasks compared to 2/3 for Condition A. The memory store provided high-precision localization clues for the third task, eliminating unproductive exploration loops.
2. **Cost & Token Reduction (-46.0%):** Prompt tokens dropped from 8,400 to 4,950 (-41.1%) and completion tokens dropped from 2,100 to 1,050 (-50.0%). By retrieving similar defect patterns, the agent required fewer reasoning iterations to synthesize passing patches.
3. **Zero Regressions:** In both conditions, all pre-existing tests (`PASS_TO_PASS`) remained passing.

### 1.5 Sample Size Caveat & Statistical Limits
> [!WARNING]
> **Sample Size Disclaimer:**  
> The evaluation sample size ($N=3$ held-out tasks, $N=3$ tuning tasks) is **too small to draw statistically significant general conclusions regarding full SWE-bench performance**. This experiment validates the pipeline mechanics, metric logging, state persistence, and directional delta tracking. It does not guarantee identical percentage improvements on a 500-task distribution.

---

## 2. ML Lab Compact Neural Model Architecture Study

### 2.1 Study Objectives & Factor Isolation
The ML Lab evaluated the computational and statistical trade-offs of compact Transformer architectures trained for code pattern representation:
- **Dataset:** `debug_synthetic_v1@1.0.0`
- **Vocabulary Size:** 102 tokens (deterministic synthetic grammar)
- **Isolated Factor:** Number of Transformer layers (`n_layers: 2 -> 1`)
- **Held Invariant:** Embedding dimension (64), learning rate ($1 \times 10^{-3}$), optimizer (AdamW), training epochs (5), sequence length (128).

### 2.2 Measured Training & Evaluation Results

| Experiment ID | Layers | Dim | Parameters | Val Loss | Perplexity | Token Accuracy | Latency (ms/step) | Throughput (tok/s) |
|---|---|---|---|---|---|---|---|---|
| `baseline_2layers` | 2 | 64 | 76,800 | **3.2009** | **24.55** | **34.9%** | 28.33 ms | 847.2 |
| `variation_1layer` | 1 | 64 | 43,776 | 3.2056 | 24.67 | 27.1% | **15.74 ms** | **1,525.0** |

### 2.3 Factor Variation Analysis
- **Parameter Reduction:** Reducing layers from 2 to 1 reduced parameters by **43.0%** (from 76,800 down to 43,776).
- **Throughput Gain:** Inference throughput increased by **+80.0%** (from 847.2 tokens/sec to 1,525.0 tokens/sec), with step latency dropping from 28.33 ms to 15.74 ms.
- **Accuracy & Loss Trade-Off:** Validation loss slightly degraded by **+0.0047** (3.2009 $\rightarrow$ 3.2056) and token prediction accuracy decreased from 34.9% to 27.1%.

### 2.4 Machine Learning Limitations
- **No Emergence in Sub-Million Parameter Models:** These models (~40k–76k parameters) operate as statistical language models over toy grammars. They lack multi-step reasoning, planning, or code synthesis capabilities.
- **Scope of Perplexity:** Perplexity (24.55 vs 24.67) is vocabulary-dependent ($V=102$). It reflects distribution modeling over the synthetic dataset, not real-world Python debugging ability.
