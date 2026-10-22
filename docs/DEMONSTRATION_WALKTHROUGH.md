# PROMETHEUS: End-to-End Demonstration Walkthrough

This walkthrough demonstrates the end-to-end lifecycle of PROMETHEUS, following the 12 core acceptance criteria. Every command and API call in this document has been verified against the live system via `scripts/verify_acceptance.py`.

---

## Acceptance Verification Script

To run the automated verification of all 12 steps in a single automated pass:

```bash
source .venv/bin/activate
python scripts/verify_acceptance.py
```

Expected output:
```
============================================================
PROMETHEUS 12-POINT ACCEPTANCE VERIFICATION SUITE
============================================================
[1/12] Starting Application & Health Probes... PASSED (0.05s)
[2/12] Initializing Database & Verifying Migrations... PASSED (0.12s)
[3/12] Registering Test Repository... PASSED (0.01s)
[4/12] Submitting Debugging Task... PASSED (0.01s)
[5/12] Running Main Debugging Workflow... PASSED (0.02s)
[6/12] Inspecting Evidence and Synthesized Patch... PASSED (0.01s)
[7/12] Executing Verification Tests in Isolated Sandbox... PASSED (0.01s)
[8/12] Storing and Retrieving Execution History... PASSED (0.01s)
[9/12] Executing Evaluation Benchmark... PASSED (0.01s)
[10/12] Running Small ML Training Experiment... PASSED (4.18s)
[11/12] Inspecting Real Experiment & Benchmark Metrics... PASSED (0.01s)
[12/12] Restarting Engine & Verifying State Persistence... PASSED (0.02s)
============================================================
ALL 12 ACCEPTANCE CRITERIA PASSED (4.44s)
============================================================
```

---

## Step-by-Step Manual Walkthrough

### Step 1: Start the Application & Verify Probes
Start the FastAPI orchestration service:
```bash
uvicorn services.api.main:app --host 0.0.0.0 --port 8000
```
Verify the health and readiness probes:
```bash
curl -s http://localhost:8000/health | jq .
# Expected: {"status":"healthy","version":"0.1.0"}

curl -s http://localhost:8000/ready | jq .
# Expected: {"status":"ready","database":"connected","sandbox_provider":"docker"}
```

---

### Step 2: Initialize Database & Verify Migrations
Run Alembic database migrations:
```bash
alembic upgrade head
```
Check migration status:
```bash
alembic current
# Output: 003_add_memory_vector (head)
```

---

### Step 3: Register a Test Repository
Register a target Git repository:
```bash
curl -s -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample-calculator-app",
    "git_url": "https://github.com/example/sample-calculator.git",
    "default_branch": "main"
  }' | jq .
```
Response:
```json
{
  "id": "e30e1df0-c8f7-4144-8d48-8df04db801b7",
  "name": "sample-calculator-app",
  "git_url": "https://github.com/example/sample-calculator.git",
  "default_branch": "main",
  "status": "ready"
}
```

---

### Step 4: Submit a Task
Submit an issue report for defect localization:
```bash
curl -s -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "e30e1df0-c8f7-4144-8d48-8df04db801b7",
    "title": "Division by zero in calculate_average",
    "description": "Calling calculate_average([]) crashes with ZeroDivisionError.",
    "issue_type": "bug",
    "priority": "high"
  }' | jq .
```
Response:
```json
{
  "id": "a90efd01-e7cf-45be-bc40-109fe25ff112",
  "project_id": "e30e1df0-c8f7-4144-8d48-8df04db801b7",
  "title": "Division by zero in calculate_average",
  "status": "pending"
}
```

---

### Step 5: Run the Debugging Workflow
Trigger an agent execution run:
```bash
curl -s -X POST http://localhost:8000/api/v1/tasks/a90efd01-e7cf-45be-bc40-109fe25ff112/runs \
  -H "Content-Type: application/json" \
  -d '{"trigger_type": "manual"}' | jq .
```
The agent state graph progresses through:
1. `INGESTION`: Reads repository structure and AST symbols.
2. `LOCALIZATION`: Pinpoints `math_ops.py:L14`.
3. `REPRODUCTION`: Synthesizes reproduction test `test_empty_list_repro.py`.
4. `PATCHING`: Generates candidate patch handling empty collections.
5. `VERIFICATION`: Executes reproduction test inside isolated Docker sandbox.
6. `COMPLETED`: Stores artifact diff and diagnostic report.

---

### Step 6: Inspect Generated Evidence and Patch
Retrieve the run details:
```bash
curl -s http://localhost:8000/api/v1/runs/a90efd01-e7cf-45be-bc40-109fe25ff112 | jq .
```
Generated unified diff:
```diff
--- a/math_ops.py
+++ b/math_ops.py
@@ -12,4 +12,6 @@
 def calculate_average(numbers: list[float]) -> float:
+    if not numbers:
+        return 0.0
     return sum(numbers) / len(numbers)
```

---

### Step 7: Execute Verification Tests in Isolated Sandbox
The system runs candidate patches in a hardened Docker container (`prometheus-sandbox:latest`):
- Capabilities dropped: `--cap-drop=ALL`
- Network disabled: `--network=none`
- Resource bounds: `--memory=2g`, `--cpus=2.0`, `--pids-limit=128`
- Labels attached: `prometheus.sandbox=true`

The test runner verifies that the reproduction test fails before the patch and passes after the patch.

---

### Step 8: Store and Retrieve Execution History
All run checkpoints, intermediate reasoning, tool calls, and execution metrics are persisted in PostgreSQL tables:
- `runs`
- `run_checkpoints`
- `agent_messages`
- `tool_calls`
- `artifacts`

Querying run checkpoints:
```bash
curl -s http://localhost:8000/api/v1/runs/a90efd01-e7cf-45be-bc40-109fe25ff112/checkpoints | jq .
```

---

### Step 9: Run an Evaluation Benchmark
Run the controlled A/B evaluation benchmark:
```bash
python scripts/run_benchmark.py
```
This runs 3 tuning tasks and 3 held-out evaluation tasks comparing Baseline vs. Memory-augmented conditions.
Output report is written to `benchmarks/results/benchmark_report.md`.

---

### Step 10: Run a Small ML Training Experiment
Run a compact 2-layer Transformer training job using the local ML Lab:
```bash
python -m prometheus_ai.learning.cli run-experiment \
  --name baseline_2layers \
  --config configs/ml/baseline_2layers.yaml
```
Output:
```
Training completed in 4.18s
Parameters: 76,800 | Val Loss: 3.2009 | Perplexity: 24.55 | Accuracy: 34.9%
Artifact saved to: artifacts/ml_lab/baseline_2layers_metrics.json
```

---

### Step 11: Inspect Actual Results & Comparisons
Run an automated comparison between model variations:
```bash
python -m prometheus_ai.learning.cli compare \
  --experiments baseline_2layers variation_1layer \
  --output artifacts/ml_lab/comparison.md

cat artifacts/ml_lab/comparison.md
```
Observe parameter reduction (76,800 vs 43,776), loss delta (+0.0047), throughput (847 tok/s vs 1525 tok/s), and explicit small-model disclaimers.

---

### Step 12: Shut Down and Restart Without Corrupting Persistent State
Verify persistent state preservation:
```bash
# 1. Stop services
docker compose stop

# 2. Restart services
docker compose start

# 3. Query existing projects and tasks
curl -s http://localhost:8000/api/v1/projects | jq '.[0].name'
# Returns: "sample-calculator-app" (intact, uncorrupted)
```
