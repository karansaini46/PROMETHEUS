# PROMETHEUS

> **Autonomous AI Software Engineering & Debugging Platform**  
> *Combining AI Systems Engineering, Machine Learning Engineering, Applied AI, and AI Research Engineering.*

---

## 1. System Vision

PROMETHEUS is an ambitious open-source AI platform built to autonomously investigate software repositories, localize complex defects, synthesize minimal reproduction tests, verify candidate patches in isolated execution environments, and produce verifiable diagnostic reports.

### Architectural Foundations
- **Modular Monolith:** Clean separation of concerns without unnecessary microservice overhead.
- **Authoritative State:** PostgreSQL 16 stores all application state, execution runs, and state checkpoints.
- **Graceful Degradation:** Runs seamlessly on standard CPU workstations (Ubuntu 8GB RAM) with optional local model providers (Ollama / vLLM), zero-GPU fallback, and hybrid lexical/AST search when vector databases are disabled.
- **Sandbox Security:** Docker containers stripped of all Linux capabilities (`--cap-drop=ALL`), with seccomp filters, strict PID limits (preventing fork-bombs), and zero network access (`--network=none`) during test execution.

---

## 2. Monorepo Organization

```
PROMETHEUS/
├── apps/
│   └── dashboard/            # Next.js 14+ / TypeScript Control Plane
├── services/
│   └── api/                  # FastAPI 0.115+ Orchestration & Gateway
├── packages/
│   └── shared-types/         # Typed contracts shared between Backend & UI
├── prometheus_ai/            # Core AI Engineering Subsystems
│   ├── agents/               # LangGraph state machine & reasoning nodes
│   ├── tools/                # Type-safe agent tool protocols
│   ├── memory/               # Checkpoint state persistence
│   ├── execution/            # Security guards & sandbox runners
│   ├── models/               # Multi-vendor LLM routing abstraction
│   ├── research/             # Scientific hypothesis generation
│   ├── evaluation/           # SWE-bench & benchmark metrics
│   ├── learning/             # Grounded ML training & fine-tuning pipelines
│   └── observability/        # OpenTelemetry tracing instrumentation
├── migrations/               # Alembic database migrations
├── tests/
│   ├── unit/                 # Fast, isolated unit tests
│   ├── integration/          # Service integration tests
│   ├── e2e/                  # End-to-end workflow tests
│   └── security/             # Path traversal & sandbox isolation tests
├── benchmarks/
│   ├── tasks/                # SWE-bench task definitions & fixtures
│   └── results/              # Verifiable benchmark output artifacts
├── scripts/                  # Development & CI automation scripts
├── docs/                     # Architectural & research documentation
│   ├── RESEARCH.md           # Technology evaluation & trade-offs
│   ├── ARCHITECTURE.md       # Modular monolith topology & sequence diagrams
│   ├── IMPLEMENTATION_PLAN.md# Phased milestone execution roadmap
│   ├── THREAT_MODEL.md       # STRIDE threat model & sandbox defense
│   └── EVALUATION_PLAN.md    # SWE-bench methodology & learning definitions
├── docker-compose.yml        # PostgreSQL 16, pgvector & Jaeger local setup
└── pyproject.toml            # Python 3.12 dependencies, ruff, mypy, pytest
```

---

## 3. Prerequisites

- **OS:** Linux (Ubuntu 22.04 / 24.04 recommended) or macOS
- **Python:** `3.12.x`
- **Node.js:** `v20.x` or `v22.x` (npm `v10+`)
- **Docker:** Docker Engine `24.0+` (optional for local mock dev, required for sandbox verification)
- **RAM:** Minimum 8 GB RAM

---

## 4. Quickstart & Installation

### Step 1: Clone and Configure Environment
```bash
git clone https://github.com/your-org/PROMETHEUS.git
cd PROMETHEUS

# Copy configuration template
cp .env.example .env
```

### Step 2: Set Up Python Backend Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

### Step 3: Set Up Frontend Packages
```bash
# Build shared types
cd packages/shared-types
npm install
npm run build

# Install dashboard dependencies
cd ../../apps/dashboard
npm install
cd ../..
```

### Step 4: Launch Local PostgreSQL (Optional)
```bash
docker compose up -d postgres
```

---

## 5. Development & Running Services

### Start the FastAPI Backend
```bash
source .venv/bin/activate
uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --reload
```
The API is now live at:
- Swagger Documentation: `http://localhost:8000/docs`
- Health Probe: `http://localhost:8000/api/v1/health`

### Start the Next.js Dashboard
In a separate terminal:
```bash
cd apps/dashboard
npm run dev
```
The control plane is live at `http://localhost:3000`.

---

## 6. Testing, Linting & Type Checking

Run the automated validation script to verify all layers:
```bash
./scripts/test_all.sh
```

Or run individual test suites:

### Python Checks
```bash
source .venv/bin/activate

# Format and linting
ruff check .
ruff format --check .

# Strict static type check
mypy services prometheus_ai tests

# Run unit and security tests
pytest -v
```

### Frontend Checks
```bash
cd apps/dashboard

# Linting
npm run lint

# TypeScript compilation
npm run type-check

# Vitest frontend tests
npm run test

# Production build check
npm run build
```

---

## 7. Security Policy

- **No Secrets in Source:** API keys, database credentials, and session tokens must reside exclusively in `.env` (which is ignored by Git).
- **Execution Isolation:** Untrusted repository code is executed strictly within capability-stripped containers (`--cap-drop=ALL`) with `--network=none`.
- **Path Sanitization:** File operations resolve against worktree roots via `validate_safe_path()` to prevent traversal attacks.
