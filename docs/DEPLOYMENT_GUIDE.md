# PROMETHEUS Deployment & Operations Guide

This guide provides reproducible deployment instructions for PROMETHEUS across local development, containerized Docker Compose setups, and production environments.

---

## 1. Prerequisites

### Local Hardware & OS
- **Operating System:** Linux (Ubuntu 22.04 LTS / 24.04 LTS recommended) or macOS (Apple Silicon / Intel).
- **CPU:** 4+ cores recommended.
- **RAM:** Minimum 8 GB (16 GB recommended when running Docker sandboxes and ML Lab pipelines concurrently).
- **Disk Space:** 15 GB free space for Docker images, database volumes, and sandbox worktrees.

### Software Dependencies
- **Docker Engine:** `v24.0+` with Docker Compose `v2.20+` (`docker compose`).
- **Python:** `v3.12.x` (if running locally outside containers).
- **Node.js:** `v20.x` or `v22.x` (npm `v10+`).
- **PostgreSQL Client Tools:** `pg_dump`, `pg_restore`, `psql` (optional, for backup/restore verification).

---

## 2. Environment Configuration

PROMETHEUS enforces environment validation via Pydantic (`services/api/config.py`). Development and production configurations are strictly separated.

### Development Environment Setup
Copy the template to `.env`:
```bash
cp .env.example .env
```

Default development settings (`.env`):
```ini
PROMETHEUS_ENV=development
LOG_LEVEL=INFO

# Networking & Secrets
API_SECRET_KEY=dev-insecure-secret-key-change-in-prod-32chars!
ADMIN_SECRET_KEY=dev-admin-insecure-secret-key-32chars!
REQUIRE_AUTH=false
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

# Database Connection
DATABASE_URL=postgresql+asyncpg://prometheus:prometheus@localhost:5432/prometheus_db

# Sandbox & Execution
SANDBOX_PROVIDER=docker
DOCKER_HOST=unix:///var/run/docker.sock
SANDBOX_DEFAULT_TIMEOUT=120
SANDBOX_MAX_CONCURRENT=4
WORKTREE_BASE_DIR=/tmp/prometheus_worktrees

# AI & Model Routing
PRIMARY_MODEL_PROVIDER=mock
PRIMARY_MODEL_NAME=mock-model
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Vector & Memory
EMBEDDING_PROVIDER=mock
VECTOR_DB_PROVIDER=pgvector
VECTOR_SIMILARITY_THRESHOLD=0.75
```

### Production Environment Requirements
In production (`PROMETHEUS_ENV=production`), the application **refuses to start** unless:
1. `API_SECRET_KEY` is at least 32 characters and does **not** contain `dev-` or `insecure`.
2. `ADMIN_SECRET_KEY` is at least 32 characters and does **not** contain `dev-` or `insecure`.
3. `REQUIRE_AUTH=true`.
4. `CORS_ORIGINS` is explicitly defined and does not contain `*`.

---

## 3. Local Deployment via Docker Compose

PROMETHEUS provides a 5-tier containerized stack managed via `docker-compose.yml`:
1. `postgres`: PostgreSQL 16 with `pgvector` extension.
2. `api`: FastAPI 0.115+ orchestration gateway.
3. `worker`: Asynchronous task execution and sandbox orchestrator daemon.
4. `dashboard`: Next.js 14+ control plane.
5. `jaeger`: Distributed OpenTelemetry tracing collector.

### Starting the Stack
```bash
# Build and launch all services in detached mode
docker compose up -d --build
```

### Checking Service Health
```bash
docker compose ps
```
All services should report `Up (healthy)`.

### Verification Endpoints
- Dashboard UI: [http://localhost:3000](http://localhost:3000)
- API Documentation (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
- API Liveness Probe: `curl http://localhost:8000/health`
- API Readiness Probe: `curl http://localhost:8000/ready`
- Distributed Tracing (Jaeger): [http://localhost:16686](http://localhost:16686)

---

## 4. Database Initialization & Migration Commands

PROMETHEUS uses **Alembic** for schema migrations.

### Running Migrations (Containerized)
```bash
docker compose exec api alembic upgrade head
```

### Running Migrations (Host Environment)
If running locally with a virtualenv:
```bash
source .venv/bin/activate
alembic upgrade head
```

### Checking Current Migration Revision
```bash
alembic current
```
Expected output: `003_add_memory_vector (head)`

### Rolling Back a Migration
```bash
alembic downgrade -1
```

---

## 5. Running Tests

### Running the Full Automated Verification Suite
PROMETHEUS includes a comprehensive unified test runner:
```bash
./scripts/test_all.sh
```
This script executes:
1. Ruff format check
2. Ruff linter check
3. Mypy strict type checks (Python backend)
4. Pytest test suite (unit, integration, security tests)
5. Shared TypeScript types build
6. Next.js ESLint
7. TypeScript compilation check (`tsc --noEmit`)
8. Vitest frontend component tests
9. Next.js production build (`next build`)

### Running Individual Test Suites
```bash
# Unit & integration tests
pytest tests/unit tests/integration -v

# Security isolation tests
pytest tests/security/test_sandbox_security.py -v

# Hardening & auth validation tests
pytest tests/unit/test_hardening_security.py -v

# Frontend tests
cd apps/dashboard && npm run test
```

---

## 6. Running a Sample Debugging Task

You can submit and execute a debugging workflow via the CLI or the REST API.

### Via API (curl)
```bash
# 1. Create a project
PROJECT_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "demo-repo", "git_url": "https://github.com/example/demo.git", "default_branch": "main"}' \
  | jq -r '.id')

# 2. Create a debugging task
TASK_ID=$(curl -s -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT_ID\", \"title\": \"Fix ZeroDivisionError in math_utils.py\", \"description\": \"Calling compute_ratio(10, 0) causes an unhandled ZeroDivisionError.\", \"issue_type\": \"bug\"}" \
  | jq -r '.id')

# 3. Trigger execution run
RUN_ID=$(curl -s -X POST "http://localhost:8000/api/v1/tasks/$TASK_ID/runs" \
  -H "Content-Type: application/json" \
  -d '{"trigger_type": "manual"}' \
  | jq -r '.id')

# 4. Poll execution status
curl -s http://localhost:8000/api/v1/runs/$RUN_ID | jq '.status, .current_phase'
```

---

## 7. Running an Evaluation Benchmark

PROMETHEUS includes an A/B benchmark evaluation harness comparing baseline reasoning against memory-augmented reasoning:

```bash
source .venv/bin/activate
python scripts/run_benchmark.py
```

Outputs are generated at:
- JSON Data: `benchmarks/results/benchmark_report.json`
- Markdown Summary: `benchmarks/results/benchmark_report.md`

---

## 8. Running a Small ML Experiment

PROMETHEUS includes an isolated ML Lab pipeline for training, evaluating, and comparing compact neural architectures:

```bash
source .venv/bin/activate

# 1. Run Baseline Experiment (2 Transformer layers)
python -m prometheus_ai.learning.cli run-experiment \
  --name baseline_2layers \
  --config configs/ml/baseline_2layers.yaml

# 2. Run Variation Experiment (1 Transformer layer)
python -m prometheus_ai.learning.cli run-experiment \
  --name variation_1layer \
  --config configs/ml/variation_1layer.yaml

# 3. Compare Results
python -m prometheus_ai.learning.cli compare \
  --experiments baseline_2layers variation_1layer \
  --output artifacts/ml_lab/comparison.md
```

Artifacts (checkpoints, metrics, charts) are stored in `artifacts/ml_lab/`.

---

## 9. Backup and Restore Procedures

### Database Backup
```bash
# Export compressed PostgreSQL database dump
docker compose exec -T postgres pg_dump -U prometheus -d prometheus_db -F c > backup_$(date +%Y%m%d_%H%M%S).dump
```

### Database Restore
```bash
# 1. Terminate active connections and drop existing database
docker compose exec -T postgres psql -U prometheus -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'prometheus_db';"
docker compose exec -T postgres dropdb -U prometheus prometheus_db
docker compose exec -T postgres createdb -U prometheus prometheus_db

# 2. Restore from dump file
cat backup_YYYYMMDD_HHMMSS.dump | docker compose exec -T postgres pg_restore -U prometheus -d prometheus_db --clean --if-exists
```

---

## 10. Operational Troubleshooting

| Symptom | Probable Cause | Resolution |
|---|---|---|
| API container fails with `ValidationError` | Production environment set without valid secrets | Ensure `API_SECRET_KEY` and `ADMIN_SECRET_KEY` are ≥32 chars and do not contain `dev-` or `insecure`. Set `REQUIRE_AUTH=true`. |
| Sandbox fails with `docker.errors.DockerException` | Docker socket not mounted or permissions error | Check `/var/run/docker.sock` mount in `docker-compose.yml`. Ensure user running worker has read/write permissions to Docker socket. |
| Worker leaves orphaned containers | Task timed out or worker process aborted | The worker automatically prunes containers labeled `prometheus.sandbox=true`. Run `docker container prune --filter "label=prometheus.sandbox=true"`. |
| DB connection error `asyncpg.exceptions.ConnectionDoesNotExistError` | PostgreSQL is initializing or connection pool exhausted | Wait for PostgreSQL healthcheck to succeed (`docker compose ps postgres`). Verify `DATABASE_URL` in `.env`. |
| Dashboard shows 401 Unauthorized | `REQUIRE_AUTH=true` is enabled but no bearer token passed | Pass header `Authorization: Bearer <API_SECRET_KEY>` in requests, or log in via dashboard auth modal. |

---

## 11. Updating the Application

To update an existing installation to a new release:

```bash
# 1. Pull latest code
git pull origin main

# 2. Backup current database
docker compose exec -T postgres pg_dump -U prometheus -d prometheus_db -F c > backup_pre_update.dump

# 3. Rebuild and restart containers
docker compose up -d --build

# 4. Apply database migrations
docker compose exec api alembic upgrade head

# 5. Verify readiness
curl http://localhost:8000/ready
```

---

## 12. Production Deployment Guidance & Security Hardening

For production deployments, apply `docker-compose.prod.yml`:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Security Invariants & Hardening Measures

1. **Non-Root Execution:**
   - The API and Worker containers run as unprivileged user `prometheus:1000`.
   - The Next.js dashboard runs as unprivileged user `nextjs:1001`.
   - The Sandbox execution environment runs as unprivileged user `sandbox:1000`.
   - `no-new-privileges:true` is enforced across all production containers.

2. **Network Isolation & Sandbox Confinement:**
   - **Never expose the Sandbox to the public internet.**
   - Sandboxes run with `--network=none` during code verification and test execution.
   - All Linux capabilities are dropped (`--cap-drop=ALL`).
   - Sandbox memory and CPU quotas are strictly bounded (`--memory=2g`, `--cpus=2.0`, `--pids-limit=128`).

3. **Secret Hygiene:**
   - **Never bake credentials or API keys into Docker images.**
   - All secrets must be injected at runtime via environment variables or secret managers (e.g., AWS Secrets Manager, HashiCorp Vault).
   - `.dockerignore` blocks `.env`, `.git`, `.venv`, and node modules from Docker build contexts.

4. **Administrative & Ingestion Endpoint Protection:**
   - All endpoints under `/api/v1/admin/*` require `X-Admin-Key` authentication.
   - All modification and task endpoints require valid Bearer token authentication when `REQUIRE_AUTH=true`.
