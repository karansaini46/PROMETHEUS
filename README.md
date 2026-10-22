# PROMETHEUS

> **Autonomous AI Software Engineering & Diagnostic Copilot**  
> *Evidence-based defect localization, minimal reproduction test synthesis, and patch verification in hardened execution sandboxes.*

[![Release](https://img.shields.io/badge/Release-v0.1.0-blue.svg)](docs/RELEASE_CHECKLIST.md)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue.svg)](apps/dashboard/package.json)
[![Next.js](https://img.shields.io/badge/Next.js-14.2-black.svg)](apps/dashboard/package.json)
[![Docker](https://img.shields.io/badge/Docker-Verified-2496ED.svg)](docker-compose.yml)
[![Tests](https://img.shields.io/badge/Tests-156%20Pytest%20%7C%209%20Vitest-brightgreen.svg)](scripts/test_all.sh)
[![Acceptance](https://img.shields.io/badge/Acceptance-12%2F12%20Verified-success.svg)](scripts/verify_acceptance.py)

---

## 1. System Overview

PROMETHEUS is an open-source, evidence-driven software engineering workbench designed to investigate codebases, isolate root causes of software defects, synthesize minimal reproduction tests, verify candidate patches in isolated containers, and store state transitions in PostgreSQL.

> [!IMPORTANT]
> **Scope & Autonomy Boundaries:**  
> PROMETHEUS is built as an **assistive diagnostic copilot**, not an unsupervised or fully autonomous developer. All candidate patches and diagnostics require human code review. For full details on system boundaries and machine learning constraints, see [Known Limitations](docs/KNOWN_LIMITATIONS.md).

### Key Architectural Pillars
- **Modular Monolith:** Clean domain boundaries without premature microservice overhead.
- **Authoritative Relational State:** PostgreSQL 16 stores all task specifications, LangGraph state checkpoints, and run histories.
- **Defense-in-Depth Sandbox:** Untrusted code executes exclusively inside capability-stripped (`--cap-drop=ALL`), network-isolated (`--network=none`), resource-bounded Docker containers.
- **Deterministic Evaluation Oracles:** Patches are validated against dual test suites (`FAIL_TO_PASS` must pass, `PASS_TO_PASS` must not regress).
- **Graceful Degradation:** Runs seamlessly on standard CPU workstations (Ubuntu 8GB RAM) with mock model providers or local LLM backends (Ollama/vLLM) without requiring GPUs.

---

## 2. Agent Execution Workflow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            AGENT EXECUTION FLOW                              │
└──────────────────────────────────────────────────────────────────────────────┘

  1. ISSUE INGESTION       Parse issue title, stack traces, and problem description
         │
         ▼
  2. LOCALIZATION          Query Tree-sitter AST symbol graphs & BM25 lexical index
         │                 to isolate faulty files, classes, and function spans
         ▼
  3. REPRODUCTION          Synthesize a minimal, standalone reproduction test script
         │                 asserting that the failure reproduces (FAIL state)
         ▼
  4. PATCH SYNTHESIS       Generate unified diff patch adhering strictly to
         │                 syntactic constraints and existing code conventions
         ▼
  5. SANDBOX VERIFICATION  Apply patch in isolated Docker container (--network=none)
         │                 and execute dual-test oracles:
         │                 • FAIL_TO_PASS: Reproduction test transitions FAIL -> PASS
         │                 • PASS_TO_PASS: Pre-existing regression tests remain PASS
         ▼
  6. ARTIFACT & REVIEW     Persist verified diff, execution metrics, and checkpoint
                           to PostgreSQL; render in Next.js review interface
```

---

## 3. High-Level System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ Presentation Plane: Next.js 14+ Control Plane                          │
│ - Live Run Inspection, Diff Viewer, Model Management, Task Board       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / SSE Stream
┌───────────────────────────────────▼────────────────────────────────────┐
│ Gateway & Orchestration Plane: FastAPI 0.115+                          │
│ - REST API (/api/v1), Liveness & Readiness Probes (/health, /ready)    │
│ - Auth Guard & Production Secrets Validator                            │
│ - LangGraph Cyclic State Engine (Ingest -> Localize -> Patch -> Test)  │
│ - Code Intelligence Engine (Tree-sitter AST & Lexical Indexing)        │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
┌───────────────────▼──────────────┐   ┌─────────────▼───────────────────┐
│ Persistence Plane (PostgreSQL 16)│   │ Background Worker & Sandbox     │
│ - Authoritative Run State        │   │ - Async DB Queue Polling Daemon │
│ - State Checkpoints              │   │ - Docker Execution Sandbox      │
│ - pgvector Semantic Memory       │   │   (--network=none, --cap-drop)  │
└──────────────────────────────────┘   └─────────────────────────────────┘
```

Detailed architectural diagrams and component specifications are documented in [Architecture Documentation](docs/ARCHITECTURE.md).

---

## 4. Repository Structure

```
PROMETHEUS/
├── apps/
│   └── dashboard/            # Next.js 14+ / TypeScript Control Plane
├── services/
│   └── api/                  # FastAPI 0.115+ Gateway & Background Worker
├── packages/
│   └── shared-types/         # Typed contracts shared between Backend & UI
├── prometheus_ai/            # Core AI Engineering Subsystems
│   ├── agents/               # LangGraph state machine & reasoning nodes
│   ├── tools/                # Type-safe agent tool protocols
│   ├── memory/               # Checkpoint state persistence & vector search
│   ├── execution/            # Security guards & Docker sandbox runners
│   ├── models/               # Multi-vendor LLM routing abstraction
│   ├── research/             # Scientific hypothesis generation
│   ├── evaluation/           # SWE-bench & benchmark metrics
│   ├── learning/             # Grounded ML training & fine-tuning pipelines
│   └── observability/        # OpenTelemetry tracing instrumentation
├── migrations/               # Alembic database migrations
├── tests/
│   ├── unit/                 # Fast, isolated unit tests
│   ├── integration/          # Service integration tests
│   └── security/             # Path traversal & sandbox isolation tests
├── benchmarks/
│   ├── tasks/                # SWE-bench task definitions & fixtures
│   └── results/              # Verifiable benchmark output artifacts
├── scripts/                  # Development, validation, and acceptance scripts
├── docs/                     # Architectural, research, and operational docs
├── docker-compose.yml        # PostgreSQL 16, API, Worker, Dashboard, Jaeger
└── docker-compose.prod.yml   # Production hardening security overlay
```

---

## 5. Documentation Index

| Document | Description |
|---|---|
| [**Deployment Guide**](docs/DEPLOYMENT_GUIDE.md) | Local Docker Compose, production configuration, migrations, backup/restore, troubleshooting. |
| [**Architecture Specification**](docs/ARCHITECTURE.md) | Modular monolith design, LangGraph state machine, data models, and sequence flows. |
| [**Threat Model & Security**](docs/THREAT_MODEL.md) | STRIDE analysis, prompt injection defense, capability stripping, and network isolation. |
| [**API Reference**](docs/API_REFERENCE.md) | REST API endpoints, request/response schemas, SSE streaming, and error codes. |
| [**Evaluation Methodology**](docs/EVALUATION_METHODOLOGY.md) | Scientific framework: SWE-bench Lite / Verified, test oracles, and A/B evaluations. |
| [**Experiment Report**](docs/EXPERIMENT_REPORT.md) | Real empirical results from micro-benchmarks and ML Lab compact neural model training. |
| [**Known Limitations**](docs/KNOWN_LIMITATIONS.md) | Honest boundaries regarding autonomy, small model non-emergence, sandboxing, and benchmark scale. |
| [**Demonstration Walkthrough**](docs/DEMONSTRATION_WALKTHROUGH.md) | Step-by-step verification walkthrough covering all 12 core acceptance actions. |
| [**Release Checklist**](docs/RELEASE_CHECKLIST.md) | Formal v0.1.0 release sign-off covering 15 checklist criteria and 12 acceptance tests. |
| [**Security Isolation**](docs/SECURITY_ISOLATION.md) | Linux namespace, cgroup, seccomp, and container capability hardening. |
| [**Operational Troubleshooting**](docs/OPERATIONAL_TROUBLESHOOTING.md) | Diagnostic runbooks for database locks, orphaned sandboxes, and worker recovery. |
| [**ML Lab Guide**](docs/ML_LAB.md) | Training, evaluating, and comparing local compact Transformer architectures. |
| [**Research & Trade-Offs**](docs/RESEARCH.md) | Comprehensive analysis of AST search, vector databases, and evaluation frameworks. |

---

## 6. Quickstart: Local Docker Compose

The fastest way to deploy the entire PROMETHEUS platform is using Docker Compose:

### Prerequisites
- Docker Engine `v24.0+` with Docker Compose `v2.20+`
- 8 GB RAM minimum

### 1. Launch Services
```bash
git clone https://github.com/karansaini46/PROMETHEUS.git
cd PROMETHEUS

# Copy configuration
cp .env.example .env

# Build and start all 5 containers
docker compose up -d --build
```

### 2. Verify Health
```bash
docker compose ps
```
Services running:
- **Dashboard UI:** [http://localhost:3000](http://localhost:3000)
- **FastAPI API & Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Liveness Probe:** `curl http://localhost:8000/health`
- **Readiness Probe:** `curl http://localhost:8000/ready`
- **Jaeger Tracing:** [http://localhost:16686](http://localhost:16686)

---

## 7. Development & Manual Setup

### Python Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### Apply Database Migrations
```bash
alembic upgrade head
```

### Run Unified Test Suite
Run all 9 testing and linting stages across backend and frontend:
```bash
./scripts/test_all.sh
```

### Run 12-Point Acceptance Suite
Verify all 12 end-to-end acceptance actions against the live database and sandbox:
```bash
python scripts/verify_acceptance.py
```

---

## 8. Empirical Benchmark Summary

The internal micro-benchmark evaluates reasoning with and without memory retrieval under identical model parameters and evaluation oracles.

| Metric | Condition A (Baseline) | Condition B (With Memory) | Measured Delta |
|---|---|---|---|
| **Resolve Rate** | **66.7%** (2/3) | **100.0%** (3/3) | **+33.3%** |
| **Total Cost** | $0.0567 | $0.0306 | **-$0.0261 (-46.0%)** |
| **Prompt Tokens** | 8,400 | 4,950 | **-3,450 (-41.1%)** |
| **Completion Tokens**| 2,100 | 1,050 | **-1,050 (-50.0%)** |
| **Regressions** | 0 | 0 | **0 (Clean)** |
| **Execution Latency** | 0.03s | 0.03s | 0.00s |

> [!NOTE]
> **Scientific Caveat:** The evaluation sample size ($N=3$ held-out tasks, $N=3$ tuning tasks) validates pipeline mechanics, metric logging, state persistence, and directional delta tracking. It is too small to draw statistically significant general conclusions regarding full SWE-bench performance. See [Experiment Report](docs/EXPERIMENT_REPORT.md).

---

## 9. Security Invariants

1. **Unprivileged Containers:** All services run as non-root users (`prometheus:1000`, `nextjs:1001`, `sandbox:1000`).
2. **Zero Network Sandboxing:** Untrusted repository code executes strictly with `--network=none`.
3. **No Secrets in Images:** All credentials and API keys are injected at runtime via environment variables; `.dockerignore` blocks `.env`, git history, and secrets.
4. **Administrative Protection:** Administrative endpoints require `X-Admin-Key` headers; production mode strictly enforces authentication and strong secret keys.
5. **Path Traversal Defense:** All filesystem interactions validate against canonical root paths via `validate_safe_path()`.

---

## 10. License

PROMETHEUS is released under the [Apache 2.0 License](LICENSE).
