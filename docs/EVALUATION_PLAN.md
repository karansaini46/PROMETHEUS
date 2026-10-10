# PROMETHEUS — Evaluation Plan & Scientific Benchmarking

**Document Version:** 1.0.0  
**Status:** Approved Research & Evaluation Methodology  
**Author:** Lead AI Systems Architect & Research Engineer  

---

## 1. Evaluation Philosophy & Scientific Grounding

PROMETHEUS adheres to an evidence-based, empirical research discipline. In autonomous software engineering, subjective assessments ("the patch looks reasonable") or unverified syntax checks are unacceptable. 

An autonomous software repair system must be evaluated against **deterministic execution oracles** under strict, reproducible conditions. Furthermore, any claims of machine learning improvements must clearly state **what model weights or parameters are being updated, what dataset is used for training, what held-out split is used for evaluation, and what baseline it is compared against.**

---

## 2. Benchmark Suites & Datasets

### 2.1 Primary Benchmark: SWE-bench Lite & SWE-bench Verified
- **SWE-bench Lite:** 300 curated task instances extracted from 12 real-world, popular Python repositories (Django, SymPy, Matplotlib, Scikit-learn, etc.). Each task represents an authentic GitHub issue accompanied by a pull request and test suite.
- **SWE-bench Verified:** 500 task instances human-verified by software engineers to eliminate underspecified problem statements and flaky test oracles.
- **Standard Dataset Schema:**
  - `repo`: e.g. `django/django`
  - `base_commit`: The git commit SHA of the repository prior to the fix.
  - `problem_statement`: The raw issue description reported by users.
  - `test_patch`: The test case written to reproduce and verify the fix.
  - `PASS_TO_PASS`: Pre-existing tests that must remain passing.
  - `FAIL_TO_PASS`: The reproduction test that must transition from failing to passing after applying the patch.

### 2.2 Secondary Benchmark: Internal Micro-Evaluation Suite (PROMETHEUS-Micro)
Before running extensive, multi-hour SWE-bench evaluations, PROMETHEUS evaluates candidate changes against an internal micro-benchmark of 30 synthetic and real Python bugs:
1. **Type & Attribute Errors (10 tasks):** Missing `None` checks, changed dictionary key names, missing imports.
2. **Algorithmic & Off-by-One Errors (10 tasks):** Boundary condition errors in loops, sorting inversion, indexing bugs.
3. **Refactoring & API Migration Errors (10 tasks):** Renamed internal functions, parameter order mismatch.

---

## 3. Baselines for Comparison

To quantify the true contribution of each architectural subsystem, PROMETHEUS is evaluated against four distinct baselines:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Baseline 0: Dummy / Null Baseline                                      │
│ - Generates empty patch (git diff is empty)                            │
│ - Measures baseline test flakiness and false-positive rate             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Baseline 1: Zero-Shot Direct LLM Prompting                             │
│ - Prompt: Issue text + single candidate file dumped into context       │
│ - No tool calling, no repository search, no sandbox execution          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Baseline 2: Simple ReAct Agent (Aider / SWE-agent Minimalist)          │
│ - Linear thought-action-observation loop with basic bash / grep tools  │
│ - No state checkpointing, no Tree-sitter AST symbol graphs             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Candidate: Full PROMETHEUS Platform                                    │
│ - Cyclic LangGraph state engine with PostgreSQL checkpoints            │
│ - Hybrid Code Intelligence (Tree-sitter AST + BM25 + Ripgrep)          │
│ - Hardened Docker test execution sandbox with test oracle validation   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Evaluation Metrics & Success Criteria

### 4.1 Primary Success Metrics
1. **Pass@1 / Resolve Rate:**
   $$\text{Resolve Rate} = \frac{\text{Number of Tasks with 100\% Tests Passing}}{\text{Total Task Instances}} \times 100\%$$
   A task is resolved **if and only if**:
   - Every test in `FAIL_TO_PASS` transitions from `FAIL` $\rightarrow$ `PASS`.
   - Every test in `PASS_TO_PASS` remains `PASS` (zero test regressions).
2. **Localization Accuracy (Hit@K & MRR):**
   - **Hit@1 / Hit@3 / Hit@5:** Whether the ground-truth modified file(s) and function(s) are present in the agent's top-K candidate list during the localization phase.
   - **Mean Reciprocal Rank (MRR):** Measures ranking precision of the faulty symbol.

### 4.2 Efficiency & Operational Metrics
3. **Token Consumption & Financial Cost:**
   - Input (prompt) tokens, output (completion) tokens, and total cost in USD per task instance.
4. **Execution Latency & Iteration Count:**
   - Wall-clock seconds from issue ingestion to final patch export.
   - Number of agent reasoning turns and sandbox execution cycles.
5. **Patch Minimality & Cleanliness:**
   - **Diff Distance Ratio:** Ratio of lines modified by the agent compared to the ground-truth pull request patch:
     $$\text{Minimality Ratio} = \frac{\text{Lines Added} + \text{Lines Deleted}}{\text{Ground Truth Lines Modified}}$$
   - Penalizes extraneous whitespace edits, commented-out code, and irrelevant refactorings.

---

## 5. Hypothesis Generation & Experimental Methodology

PROMETHEUS structures all research advancements as testable, falsifiable scientific hypotheses.

### Example Research Hypotheses & Experimental Design

#### Hypothesis 1: AST-Guided Symbol Search vs. Pure Vector Semantic Search
- **Hypothesis Statement:** "Integrating Tree-sitter AST symbol graphs for fault localization will achieve $\ge 15\%$ higher localization Hit@3 on SWE-bench Lite compared to dense vector embedding search alone, while consuming $\ge 35\%$ fewer prompt tokens."
- **Experimental Setup:**
  - Condition A (Control): Code intelligence uses dense vector similarity (`pgvector` over chunked source files).
  - Condition B (Treatment): Code intelligence uses Tree-sitter AST symbol definitions and call hierarchy lookups.
  - Sample Size: 100 random SWE-bench Lite tasks.
  - Evaluation: Compare Hit@3 and prompt token counts using a two-tailed paired t-test ($p < 0.05$).

#### Hypothesis 2: Reproduction-First Test Driven Patching vs. Direct Patch Synthesis
- **Hypothesis Statement:** "Requiring the agent to write and execute a failing reproduction script before drafting a patch increases the final Resolve Rate by $\ge 8\%$ by eliminating false-positive patches."
- **Experimental Setup:**
  - Condition A: Agent immediately attempts to draft a patch after localization.
  - Condition B: Agent must write a standalone test script, verify it exits with code $\ne 0$ in the sandbox, draft the patch, and verify the test exits with code $0$.
  - Evaluation: Measure Pass@1 and regression rate across 150 SWE-bench Verified tasks.

---

## 6. Grounded Machine Learning & Fine-Tuning Strategy

PROMETHEUS does not make speculative claims that the system "learns autonomously in real-time." Learning is implemented via **offline, verifiable training pipelines** with clear train/validation/test splits.

### 6.1 What is Learned: Two Concrete ML Targets

```
                                PROMETHEUS Learning Framework
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
       Target 1: Fault Localization Re-Ranker            Target 2: QLoRA Patch Synthesis
  ┌──────────────────────────────────────────────┐  ┌──────────────────────────────────────────────┐
  │ Architecture: Cross-Encoder (ModernBERT /    │  │ Architecture: Qwen2.5-Coder-7B (4-bit QLoRA) │
  │ DeBERTa-v3-large)                            │  │                                              │
  │ Task: Score relevance of retrieved functions │  │ Task: Given issue + localized code, draft    │
  │ Training Data: 10,000 GitHub issues & PRs   │  │ minimal unified diff                         │
  │ Loss: InfoNCE / Contrastive Cross-Entropy    │  │ Training Data: Verified SWE-bench traces     │
  │ Metric: MRR & Hit@3 on test split            │  │ Metric: Pass@1 on held-out test split        │
  └──────────────────────────────────────────────┘  └──────────────────────────────────────────────┘
```

### 6.2 Data Curation & Leakage Prevention
- **Temporal Split:** Training repositories and issues are strictly filtered to dates preceding the SWE-bench evaluation benchmark cutoff date to prevent benchmark contamination.
- **Verification Filter:** Only execution traces where all tests passed and no regressions occurred are admitted into the fine-tuning corpus. Traces with syntactically broken patches or failing tests are rejected.
- **Evaluation on Held-Out Split:** Fine-tuned weights are benchmarked on a disjoint 20% hold-out set of repositories never seen during training.

---

## 7. Execution Protocol & Reproducibility Guidelines

To ensure every benchmark result published by PROMETHEUS is independently reproducible:
1. **Containerized Execution:** Every test run runs inside a Docker sandbox built from a pinned Dockerfile with fixed package hashes (`pip-tools` / `poetry.lock`).
2. **Fixed Random Seeds:** Model provider temperature is fixed to `0.0` (greedy decoding) for primary benchmarks to eliminate non-deterministic variance.
3. **Complete Run Artifacts:** Every benchmark run produces an export package containing:
   - Git patch diff (`patch.diff`).
   - Full OpenTelemetry trace JSON.
   - Raw sandbox stdout/stderr logs.
   - Token accounting breakdown.
4. **Automated Verification Command:**
   ```bash
   python -m backend.eval.verify_run --run-id <run_id> --output-dir ./eval_reports/
   ```
