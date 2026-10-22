# PROMETHEUS Scientific Evaluation Methodology

This document details the scientific evaluation methodology employed by PROMETHEUS to assess defect localization, reproduction test synthesis, candidate patch generation, and learning subsystems.

---

## 1. Principles of Empirical Evaluation

In autonomous and AI-assisted software engineering, subjective claims of performance are insufficient. All performance claims in PROMETHEUS are measured against deterministic execution oracles under controlled, reproducible conditions.

### Core Tenets
1. **Deterministic Oracles:** A candidate patch is evaluated exclusively by executing test suites inside isolated sandboxes.
2. **Dual-Condition Test Oracles:**
   - **`FAIL_TO_PASS`:** Tests specifically targeting the reported defect must transition from failing before the patch to passing after the patch.
   - **`PASS_TO_PASS`:** Pre-existing regression suites must remain passing (0 regression tolerance).
3. **Strict A/B Comparative Testing:** When testing a system variation (e.g., memory-augmented retrieval vs. baseline), all other variables—including model routing, prompts, temperature, tool budgets, and evaluation seeds—are held constant.
4. **Data Leakage Prevention:** The evaluation split is strictly disjoint from any tuning, training, or prompt engineering sets.

---

## 2. Benchmark Topologies

PROMETHEUS supports three tiers of evaluation:

```
┌────────────────────────────────────────────────────────┐
│ Tier 1: SWE-bench Verified (500 Human-Validated Tasks)  │
│ - Full benchmark across 12 prominent open-source repos │
│ - Human-filtered to eliminate ambiguous problem specs  │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Tier 2: SWE-bench Lite (300 Real-World GitHub Issues)   │
│ - Standardized comparative benchmark for research labs │
└──────────────────────────┬─────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────┐
│ Tier 3: Internal Micro-Benchmark (N=6 Tasks)           │
│ - 3 Tuning Tasks (in-domain development/tuning)        │
│ - 3 Held-Out Tasks (out-of-sample evaluation)          │
│ - Sub-second local execution for fast CI/CD validation │
└────────────────────────────────────────────────────────┘
```

---

## 3. Metrics Formulation

### 3.1 Primary Performance Metrics

1. **Resolve Rate (Pass@1):**
   $$\text{Resolve Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\text{Resolved}_i)}{N}$$
   Where $\text{Resolved}_i = 1$ if and only if:
   $$\forall t \in \text{FAIL\_TO\_PASS}_i: \text{status}(t) = \text{PASS} \quad \land \quad \forall t \in \text{PASS\_TO\_PASS}_i: \text{status}(t) = \text{PASS}$$

2. **Regression Rate:**
   $$\text{Regression Rate} = \frac{\sum_{i=1}^N \mathbb{I}(\exists t \in \text{PASS\_TO\_PASS}_i : \text{status}(t) = \text{FAIL})}{N}$$
   PROMETHEUS maintains a strict 0% acceptable regression policy.

### 3.2 Efficiency & Economic Metrics

3. **Total Cost (USD):**
   $$\text{Cost} = (\text{Input Tokens} \times P_{\text{input}}) + (\text{Output Tokens} \times P_{\text{output}})$$
   Calculated per task and aggregated across the evaluation benchmark.

4. **Latency & Duration (Seconds):**
   Wall-clock duration from task submission to completion of patch verification.

5. **Token Consumption:**
   Separate tracking of prompt (input) tokens and completion (output) tokens to monitor token efficiency under memory-augmented retrieval.

---

## 4. Controlled A/B Evaluation Framework

The automated benchmark harness (`scripts/run_benchmark.py`) evaluates the impact of system enhancements using a controlled A/B methodology:

- **Condition A (Baseline):** The agent operates without memory retrieval. It localizes defects using lexical/AST search and reasons in zero-shot context.
- **Condition B (With Memory):** The agent accesses a vector-indexed memory store containing validated diagnostic strategies, verified reproduction templates, and historical patches.
- **Controlled Invariants:**
  - Identical underlying model parameters.
  - Identical tool execution budget (maximum 5 turns).
  - Identical sandbox isolation rules.
  - Core system instructions remain strictly immutable.

---

## 5. Machine Learning & Training Methodology

For local model training (ML Lab), PROMETHEUS implements grounded evaluation metrics:

### 5.1 Training Objectives
- **Causal Language Modeling (CLM):** Standard Cross-Entropy loss over predicted token distributions:
  $$\mathcal{L}_{\text{CLM}} = -\frac{1}{T} \sum_{t=1}^T \log P(x_t \mid x_{<t})$$
- **Contrastive Ranking / InfoNCE:** Used for semantic memory and patch retrieval:
  $$\mathcal{L}_{\text{InfoNCE}} = -\log \frac{\exp(\text{sim}(q, k^+) / \tau)}{\sum_{j} \exp(\text{sim}(q, k_j) / \tau)}$$

### 5.2 Model Comparison Rigor
- **Factor Isolation:** Model comparisons (e.g., `baseline_2layers` vs. `variation_1layer`) must alter exactly one architectural hyperparameter (e.g., `n_layers: 2 -> 1`) while keeping tokenization, dataset version (`debug_synthetic_v1@1.0.0`), optimizer settings, and learning rate schedules identical.
- **Evaluation Integrity:** Validation loss and perplexity are reported exclusively on held-out evaluation splits.

---

## 6. Statistical Significance & Limitations

- **Micro-Benchmark Caution:** Internal benchmarks with small sample sizes ($N < 30$) validate code execution, schema conformance, and directional trends, but **must not be cited as statistically significant indicators of general capability**.
- **Frontier Benchmark Requirements:** Statistically sound claims on code generation require running on the full SWE-bench Verified ($N=500$) with bootstrap confidence intervals.
