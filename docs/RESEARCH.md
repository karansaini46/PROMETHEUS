# PROMETHEUS — Technology Research & Comparative Evaluation

**Document Version:** 1.0.0  
**Status:** Approved Architecture Draft  
**Author:** Lead AI Systems Architect & Research Engineer  

---

## 1. Executive Summary

PROMETHEUS is an open-source AI engineering platform designed to investigate software repositories, localize faults, generate minimal and verifiable patches, and validate them within isolated environments. Building such a platform requires integrating stateful multi-agent orchestration, robust container isolation, multi-provider model routing, observable transactional storage, and rigorous benchmarking.

This document presents a comparative evaluation of core technologies for PROMETHEUS, documenting technical trade-offs, official citations, architectural constraints, and failure modes.

---

## 2. Core Runtime: Python & FastAPI

### 2.1 Technology Evaluation
- **Language:** Python 3.12
- **Framework:** FastAPI (`>=0.115.0`) with Pydantic v2 (`>=2.9.0`) and Starlette (`>=0.38.0`)
- **Server:** Uvicorn (`>=0.31.0`) with `uvloop` (Linux event loop)

### 2.2 Trade-off Analysis & Rationale
| Dimension | Python 3.12 + FastAPI | Node.js / TypeScript | Go (e.g., Gin / Echo) |
| :--- | :--- | :--- | :--- |
| **ML/AI Ecosystem Interop** | **Native** (PyTorch, HuggingFace, Tree-sitter, LangGraph) | Bridge required via IPC/HTTP | Cgo/IPC required |
| **Async Concurrency** | High (asyncio + uvloop for I/O bounds) | High (event loop) | Exceptional (Goroutines) |
| **Schema Validation** | Strict & high-speed (Pydantic v2 compiled in Rust) | Zod / TypeBox (runtime JS overhead) | Compile-time structs |
| **Streaming Responses** | Built-in SSE (`StreamingResponse`) | Native SSE / WebSockets | Native SSE / WebSockets |

**Decision:** Adopt Python 3.12 and FastAPI for the AI runtime, orchestration engine, and core API. Python remains the definitive ecosystem for machine learning, code parsing (Tree-sitter bindings), and LLM frameworks. FastAPI provides OpenAPI 3.1 generation, native async handling for long-lived Server-Sent Events (SSE), and Pydantic v2 validation.

### 2.3 Official Documentation & Specifications
- FastAPI Documentation: [https://fastapi.tiangolo.com](https://fastapi.tiangolo.com)
- Pydantic v2 Documentation: [https://docs.pydantic.dev/latest/](https://docs.pydantic.dev/latest/)
- Python 3.12 asyncio specification: [https://docs.python.org/3.12/library/asyncio.html](https://docs.python.org/3.12/library/asyncio.html)

### 2.4 Limitations & Mitigations
- **GIL & CPU Bottlenecks:** Heavy computations (AST parsing large repositories, embedding calculations, model weights execution) must not block the asyncio event loop.  
  *Mitigation:* Dispatch CPU-bound operations to `asyncio.to_thread()` or `concurrent.futures.ProcessPoolExecutor`.
- **Async DB Drivers:** Synchronous drivers (e.g. `psycopg2`) block worker loops.  
  *Mitigation:* Enforce `asyncpg` (`>=0.29.0`) with SQLAlchemy 2.0 AsyncEngine.

---

## 3. Deep Learning & Experimentation Framework: PyTorch

### 3.1 Technology Evaluation
- **Library:** PyTorch (`>=2.4.0, <2.6.0`)
- **Supplementary Packages:** Hugging Face `transformers` (`>=4.45.0`), `peft` (`>=0.13.0`), `accelerate` (`>=0.34.0`)

### 3.2 CPU vs. GPU Deployment & Graceful Degradation
PROMETHEUS must function cleanly on CPU-only workstations, edge servers, or CI environments while scaling up when NVIDIA GPUs (CUDA 12.x) or Apple Silicon (MPS) are detected.

```
                    ┌───────────────────────────────────┐
                    │      Hardware Detection Layer     │
                    └─────────────────┬─────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
   CUDA Available?             Apple MPS?                CPU Only
   (torch.cuda.is_available)   (torch.backends.mps)     (Fallback)
            │                         │                         │
   ┌────────┴────────┐       ┌────────┴────────┐       ┌────────┴────────┐
   │ FP16/BF16 Model │       │ FP16 / MPS      │       │ Remote API /    │
   │ Training & LoRA │       │ Local Eval      │       │ 4-bit Quant /   │
   │ vLLM Inference  │       │                 │       │ CPU Embeddings  │
   └─────────────────┘       └─────────────────┘       └─────────────────┘
```

### 3.3 Trade-offs & Local Fine-Tuning Strategy
- **Fine-Tuning Scope:** Autonomous debugging benefits from targeted fine-tuning (e.g., training a lightweight cross-encoder ranker for fault localization, or fine-tuning small open weights like Qwen2.5-Coder-7B via QLoRA).
- **Execution Strategy:** Offline, decoupled experiment scripts rather than inline agent steps. PROMETHEUS will never require an active GPU for its core debugging workflow; local model serving and training are optional plugins.

### 3.4 Official Documentation
- PyTorch Official Docs: [https://pytorch.org/docs/stable/](https://pytorch.org/docs/stable/)
- Hugging Face PEFT: [https://huggingface.co/docs/peft/](https://huggingface.co/docs/peft/)

---

## 4. Stateful Workflow Engine: LangGraph vs. Alternatives

### 4.1 Comparative Analysis
We evaluated three approaches for stateful, multi-step agent orchestration:
1. **LangGraph (`>=0.2.35`)**: Directed cyclic graph engine with first-class state checkpointing and human-in-the-loop interruption.
2. **Temporal / Cadence**: Enterprise distributed workflow engine.
3. **Custom Async State Machine**: Pure Python state machine with custom DB tables.

| Evaluation Criteria | LangGraph | Temporal | Custom State Machine |
| :--- | :--- | :--- | :--- |
| **Cyclic Agent Graphs** | Native support for reflection/re-try loops | Awkward loop modelling | Manual state tracking |
| **State Persistence** | Native Postgres checkpointer (`langgraph-checkpoint-postgres`) | Native cluster persistence | Custom serialization logic |
| **Operational Overhead** | Zero extra services (embeds in FastAPI) | Requires Temporal Server + DB | Zero extra services |
| **Human-in-the-Loop** | Native (`interrupt_before`, `interrupt_after`) | Signals and queries | Custom event handling |
| **Vendor Lock-in** | Low (LangGraph core is modular graph library) | Moderate (Temporal SDK) | None |

### 4.2 Decision & Architecture
Adopt **LangGraph** with `PostgresSaver` (`langgraph-checkpoint-postgres`). It provides:
- **Resumability:** Every agent turn (plan, file read, AST search, edit, test run) commits a snapshot to PostgreSQL. If an API request times out or the server restarts, the workflow resumes from the last known state thread.
- **Controlled Execution:** Cyclical execution with fixed maximum recursion limits prevents runaway agent loops.
- **Human Approval Gates:** Ability to halt execution before destructive tool operations (e.g. running non-sandboxed commands or pushing commits).

### 4.3 Official Documentation
- LangGraph Documentation: [https://langchain-ai.github.io/langgraph/](https://langchain-ai.github.io/langgraph/)
- LangGraph Checkpointer Specification: [https://langchain-ai.github.io/langgraph/reference/checkpoints/](https://langchain-ai.github.io/langgraph/reference/checkpoints/)

---

## 5. Authoritative Storage & Retrieval: PostgreSQL & pgvector

### 5.1 Technology Evaluation
- **Database:** PostgreSQL 16+
- **Extensions:** `pgvector` (`>=0.7.0`), `pg_trgm`, `btree_gist`
- **ORM / Query Engine:** SQLAlchemy 2.0 (asyncio) + Alembic migrations + raw `asyncpg` for high-throughput vector queries.

### 5.2 The Authoritative State vs. Vector Search Stance
A core tenet of PROMETHEUS is: **Use PostgreSQL as the authoritative store for application state. Use vector search only where it provides measurable value.**

```
                       ┌────────────────────────────┐
                       │   PostgreSQL 16 Storage    │
                       └──────────────┬─────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            ▼                                                   ▼
 ┌──────────────────────┐                           ┌──────────────────────┐
 │ Authoritative Data   │                           │ Optional Retrieval   │
 ├──────────────────────┤                           ├──────────────────────┤
 │ - Workflows & States │                           │ - Code Chunk Vectors │
 │ - Checkpoints & Runs │                           │ - Issue Similarity   │
 │ - Repos & Branches   │                           │ - Doc Semantic Search│
 │ - Audit Logs & Traces│                           │ (HNSW Indexing)      │
 └──────────────────────┘                           └──────────────────────┘
```

### 5.3 Vector Indexing: HNSW vs. IVFFlat
- **IVFFlat:** Requires training on pre-existing dataset; recall degrades when new repositories with divergent vocabularies are indexed; index build can be slow.
- **HNSW (Hierarchical Navigable Small World):** Supported natively in `pgvector >= 0.5.0`.
  - Superior recall (>98%) without pre-training.
  - Incrementally updatable as new source files are parsed.
  - Higher memory usage (~1.5x) offset by single-database simplicity.

### 5.4 Hybrid Code Search Strategy
Pure vector embeddings frequently fail on exact identifier lookups (e.g. finding `test_reproduce_auth_error_v2` or `NullPointerException`). PROMETHEUS implements a tri-tier hybrid retrieval:
1. **Symbol Table Search (Exact):** Tree-sitter AST symbol definitions and call hierarchies.
2. **Lexical / BM25 Search:** PostgreSQL `tsvector` with English or custom code dictionary and `pg_trgm` fuzzy matching.
3. **Dense Vector Search:** `pgvector` cosine similarity over code comments, function docstrings, and issue descriptions using lightweight embeddings (e.g., `text-embedding-3-small` or `all-MiniLM-L6-v2`).

If vector embeddings or GPU/API services are unavailable, the system transparently falls back to AST symbol graphs and full-text ripgrep/lexical search with zero downtime.

### 5.5 Official Documentation
- PostgreSQL 16 Docs: [https://www.postgresql.org/docs/16/index.html](https://www.postgresql.org/docs/16/index.html)
- pgvector GitHub & Docs: [https://github.com/pgvector/pgvector](https://github.com/pgvector/pgvector)

---

## 6. Frontend: Next.js & TypeScript

### 6.1 Technology Evaluation
- **Framework:** Next.js (`>=14.2.0, <16.0.0`) App Router
- **Language:** TypeScript (`>=5.5.0`)
- **State & Data Fetching:** TanStack Query (`v5`) + React Server Components + SSE streaming
- **Styling:** Vanilla CSS / Modern CSS Modules (per design guidelines: vibrant dark mode, glassmorphism, micro-animations, no ad-hoc Tailwind bloat)

### 6.2 Architectural Boundaries
The Next.js web application acts strictly as a presentation and human-in-the-loop control plane:
- Consumes the FastAPI backend via typed REST endpoints and SSE streams (`/api/v1/runs/{id}/stream`).
- Visualizes interactive code diffs, execution terminal outputs, agent trajectory trees, and benchmark metrics.
- No direct database access or execution logic runs inside Next.js API routes.

---

## 7. Execution Sandbox & Isolation: Docker Engine API

### 7.1 Security & Sandboxing Architecture
Autonomous software debugging requires running untrusted code: cloning public repositories, running `pytest`, `npm test`, or executing arbitrary compiler commands. Running untrusted code on the host system is unacceptable.

```
Host OS (PROMETHEUS Engine)
  │
  ├─ Unix Socket: /var/run/docker.sock (Controlled Proxy / Daemon)
  │
  ▼
Sandbox Container
  ├── Security Constraints:
  │   ├── --cap-drop=ALL (No Linux Capabilities)
  │   ├── --security-opt=no-new-privileges:true
  │   ├── --security-opt seccomp=profiles/default-sandbox.json
  │   ├── --pids-limit=256 (Fork-bomb defense)
  │   ├── --memory=4g --cpus=2.0 (Resource limits)
  │   ├── --read-only (Read-only root filesystem)
  │   └── --tmpfs /tmp:rw,noexec,nosuid,size=512m
  │
  ├── Storage Mount:
  │   └── Target Worktree mounted at /workspace (read-write, isolated)
  │
  └── Network Policies:
      ├── Phase 1 (Dep Resolution): Restricted outbound network (filtered proxy)
      └── Phase 2 (Test Execution): --network=none (Zero network access)
```

### 7.2 Container Runtimes: `runc` vs. `gVisor (runsc)`
- **Standard `runc`:** Default Docker runtime. Shares host kernel. Mitigation requires aggressive seccomp, capability stripping, and non-root user.
- **`gVisor (runsc)`:** Application kernel in user-space written in Go. Intercepts all syscalls.
- **Architectural Decision:** Default configuration utilizes hardened `runc` with `--cap-drop=ALL`, `no-new-privileges`, seccomp filters, and `--network=none`. The sandbox runner architecture abstracts the container runtime, allowing plug-and-play activation of `runsc` (gVisor) or Kata Containers when available in host environments.

### 7.3 Official Documentation
- Docker Security Guidelines: [https://docs.docker.com/engine/security/](https://docs.docker.com/engine/security/)
- Docker Python SDK: [https://docker-py.readthedocs.io/en/stable/](https://docker-py.readthedocs.io/en/stable/)
- Linux Seccomp: [https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)

---

## 8. Multi-Branch Repository Manipulation: Git Worktrees

### 8.1 Why Git Worktrees?
Traditional agent systems either:
1. Re-clone large repositories per attempt (wasteful disk I/O and network bandwidth).
2. Execute `git checkout -b` inside a single working directory (precludes concurrent test runs, causes race conditions, pollutes dirty state).

### 8.2 Worktree Architecture
PROMETHEUS maintains a single **bare repository mirror** per project (`/data/repos/<project_id>.git`). For each debugging hypothesis or concurrent patch candidate:
- Creates an isolated worktree:
  ```bash
  git --git-dir=/data/repos/<project_id>.git worktree add -b patch-attempt-1 /data/worktrees/<run_id>/attempt-1 <base_commit>
  ```
- Fast disk operations (shared object database).
- True isolation: multiple agents or validation containers test competing patches simultaneously.
- Clean teardown:
  ```bash
  git --git-dir=/data/repos/<project_id>.git worktree remove --force /data/worktrees/<run_id>/attempt-1
  ```

### 8.3 Official Documentation
- Git Worktree Manual: [https://git-scm.com/docs/git-worktree](https://git-scm.com/docs/git-worktree)

---

## 9. Model-Provider Abstraction & Local Inference

### 9.1 Multi-Vendor Provider Architecture
Coupling an agent system to a single model provider (e.g. OpenAI or Anthropic) introduces significant vendor risk, cost volatility, and deployment barriers for air-gapped or privacy-conscious teams.

```
                    ┌───────────────────────────────────┐
                    │      Model Provider Interface     │
                    │      (BaseLLMProvider Protocol)   │
                    └─────────────────┬─────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            ▼                         ▼                         ▼
   Anthropic Adapter         OpenAI Adapter            Local Inference
   (Claude 3.5 Sonnet)       (GPT-4o, o1, etc.)        (Ollama / vLLM / SGLang)
   - Messages API            - Chat Completions API    - OpenAI-compatible API
   - Tool Calling Schema     - Structured Outputs      - Zero outbound telemetry
```

### 9.2 Abstraction Framework: LiteLLM vs. Direct Client Adapters
- **Evaluation:** LiteLLM (`>=1.50.0`) provides an open-source, standard interface mapping Claude, GPT, Mistral, Ollama, and vLLM to a unified format with token accounting, latency metrics, and exponential backoff retry logic.
- **Architectural Policy:** Implement a native `ModelProvider` abstract protocol in PROMETHEUS, backed by LiteLLM for routing, with custom fallbacks for local OpenAI-compatible endpoints (`http://localhost:11434/v1` for Ollama, `http://localhost:8000/v1` for vLLM).

---

## 10. Observability & Telemetry: OpenTelemetry

### 10.1 Observability Requirements for Agentic Systems
Agent runs are inherently non-deterministic, long-running, and prone to cascading errors (e.g. tool hallucination, loop recursion). Standard HTTP request logging is insufficient. PROMETHEUS requires:
- **Trace Spans:** Every agent iteration, LLM generation, tool call, sandbox execution, and DB checkpoint must be represented as nested spans within a single OpenTelemetry trace.
- **Span Attributes:** Input token counts, output token counts, cost estimations, model names, exit codes, and diff sizes.
- **Export Targets:** Standard OTLP (`opentelemetry-exporter-otlp`) to Jaeger, Grafana Tempo, or Honeycomb; local file-based JSONL traces for offline benchmark evaluations.

### 10.2 Official Documentation
- OpenTelemetry Python SDK: [https://opentelemetry.io/docs/languages/python/](https://opentelemetry.io/docs/languages/python/)

---

## 11. Benchmarking & Evaluation: SWE-bench

### 11.1 Benchmark Selection
Autonomous software engineering requires rigorous, real-world benchmarks:
1. **SWE-bench Lite (300 task instances):** High-signal subset of real GitHub issues across 12 popular Python repositories (Django, SymPy, Matplotlib, etc.).
2. **SWE-bench Verified (500 task instances):** Human-validated subset resolving ambiguous problem statements and flaky tests.
3. **Internal Micro-Benchmarks:** Fast regression test suite covering synthetic bug scenarios (syntax errors, off-by-one errors, missing imports, mock API regression).

### 11.2 Evaluation Methodology & Metrics
- **Strict Execution Oracle:** An issue is only considered resolved if:
  1. The pre-existing test suite passes.
  2. The issue-specific reproduce test fails before the patch and passes after the patch.
  3. No collateral test regressions occur.
- **Key Metrics:**
  - **Pass@1 / Resolve Rate:** Percentage of issues cleanly resolved.
  - **Localization Accuracy:** Precision and Recall of identified faulty files and functions.
  - **Token & Cost Efficiency:** Total prompt + completion tokens and financial cost per resolved bug.
  - **Iterations to Convergence:** Number of reasoning turns and sandbox runs required.

### 11.3 Reference Papers
- Jimenez et al., *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*, ICLR 2024. [https://arxiv.org/abs/2310.06770](https://arxiv.org/abs/2310.06770)

---

## 12. Automated Testing & Continuous Integration

### 12.1 Testing Strategy
- **Unit Testing:** `pytest` (`>=8.3.0`) with `pytest-asyncio` (`>=0.24.0`) for isolated service and utility tests with mocked external APIs.
- **Integration Testing:** `testcontainers` or Docker Compose to spin up clean PostgreSQL and sandbox daemons.
- **Frontend Testing:** `vitest` + React Testing Library for Next.js components.
- **Type Checking & Linting:** `ruff` (linter & formatter) + `mypy` (strict type checking) for Python; ESLint + TypeScript `tsc --noEmit` for the frontend.
- **CI Pipelines:** GitHub Actions matrix testing across Python 3.12, Docker sandbox verification, and end-to-end synthetic issue resolution.
