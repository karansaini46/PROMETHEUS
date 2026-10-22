# PROMETHEUS: Known Limitations & System Boundaries

This document provides an explicit, transparent accounting of the architectural, machine learning, operational, and security boundaries of the PROMETHEUS platform. PROMETHEUS is designed as an assistive software engineering copilot and diagnostic workbench—**it is not a fully autonomous replacement for human engineers**.

---

## 1. Autonomy & Human-in-the-Loop Boundaries

### Assistive Copilot vs. Autonomous Agent
- **No Unsupervised Merging:** PROMETHEUS does not auto-merge synthesized patches into upstream Git repositories. All candidate patches and diagnostic hypotheses are submitted as candidate pull requests or review artifacts requiring human engineering sign-off.
- **Verification Failure Ambiguity:** When an agent's synthesized reproduction test fails or candidate patch fails regression suites, the agent can cycle through hypotheses, but will terminate at `max_iterations` (default: 5) to prevent infinite loops and runaway LLM billing.
- **Ambiguous Requirements:** Natural language issue descriptions lacking reproducible tracebacks or expected behavior specifications frequently result in speculative defect localization.

---

## 2. Machine Learning & Model Limitations

### Small-Scale Neural Models (<1M Parameters)
- **Lack of Emergence:** The local models trained in the ML Lab (e.g., compact 1-to-2 layer Transformers with ~40k–76k parameters) are designed for local experimentation, synthetic grammar debugging, and algorithmic fast-iteration. They **do not possess emergent reasoning, multi-step planning, or semantic code comprehension**.
- **Memorization vs. Generalization:** On toy synthetic datasets (`debug_synthetic_v1`), compact models memorize n-gram transitions and basic syntax patterns. They cannot synthesize multi-line bug fixes across real-world codebases without large frontier model routing (Claude 3.5 Sonnet, GPT-4o, etc.).
- **Perplexity Metric Scope:** Perplexity and cross-entropy loss are vocabulary- and domain-dependent. Lower validation loss on a toy vocabulary (vocab_size=102) reflects distribution fit, not software engineering capability.

### Frontier LLM Routing & Hallucination
- **Patch Hallucination:** Even with frontier LLMs, candidate patches can introduce subtle logical bugs, hallucinated third-party dependencies, or break undocumented system invariants.
- **Context Window Exhaustion:** Repositories exceeding 50,000 lines of code cannot be loaded into model contexts simultaneously. PROMETHEUS relies on lexical, AST, and vector retrieval to identify relevant files; if the retrieval phase misses the defect site, the agent cannot fix the issue.

---

## 3. Execution Sandbox & Isolation Constraints

### Docker Socket Dependency
- Containerized execution requires access to the host's Docker socket (`/var/run/docker.sock`). While the inner sandboxes are unprivileged (`--cap-drop=ALL`, `--network=none`), granting Docker socket access to the worker host container is an operational prerequisite. Organizations with strict "no-Docker-in-Docker" or "no-socket-mounting" policies must configure remote Docker daemons over mutual TLS.

### Strict Network Isolation (`--network=none`)
- Sandbox containers run with zero network access to guarantee that untrusted code cannot exfiltrate environment secrets or attack internal infrastructure.
- **Trade-Off:** Test suites that depend on live network connections, external API calls, downloading packages dynamically (`pip install` / `npm install`), or remote databases will fail inside the sandbox unless mocked or pre-baked into the sandbox Docker image.

### Host Resource Exhaustion
- Multi-tenant or concurrent task execution is constrained by host CPU and RAM. Each sandbox container allocates up to 2 GB RAM and 2 CPU cores. Running more than 4 concurrent sandboxes on a standard 8 GB workstation can cause Linux OOM (Out Of Memory) killer interventions.

---

## 4. Benchmark & Empirical Scope

### Sample Size Constraints
- The built-in benchmark harness (`scripts/run_benchmark.py`) runs on an internal micro-benchmark suite of N=3 tuning tasks and N=3 held-out evaluation tasks.
- **Scientific Caveat:** While this micro-benchmark empirically proves pipeline mechanics, deterministic regression tracking, and positive relative deltas (+33.3% resolve rate, -$0.0261 cost reduction), **an N=3 sample size is too small to draw statistically significant conclusions regarding performance on full benchmarks such as SWE-bench Verified (500 tasks)**.
- Public benchmark evaluations require significant API budget, distributed sandboxes, and several hours of multi-worker execution.

---

## 5. Architectural & Deployment Constraints

### Single-Node Asynchronous Queue
- The default worker implementation uses an asynchronous PostgreSQL-backed polling loop (`services/api/worker.py`). While robust against process restarts, it is designed for single-node deployments.
- Horizontal scaling across multi-node worker clusters requires an external distributed broker (e.g., Celery with Redis or RabbitMQ) and shared network storage (NFS/EFS) for worktrees.

### File System Traversal Protection
- While path validation (`validate_safe_path`) strictly prevents directory traversal attacks outside the designated worktree base directory, symbolic links pointing outside the sandbox root are blocked by sandbox mount rules. Complex build systems using external symlinks may require custom volume mounts.
