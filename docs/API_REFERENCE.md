# PROMETHEUS REST API Reference

**API Version:** `0.1.0`  
**Base URL:** `http://localhost:8001`  
**API Prefix:** `/api/v1`  
**Interactive OpenAPI UI:** `http://localhost:8001/docs`  
**Alternative ReDoc:** `http://localhost:8001/redoc`  

---

## 1. Authentication & Security Headers

All requests support both development and production authentication policies.

| Header | Type | Description |
|---|---|---|
| `X-API-Key` | String | Standard client API key. |
| `Authorization` | String | Standard Bearer token (`Bearer <API_KEY>`). |
| `X-Admin-Key` | String | Dedicated administrative secret key for destructive operations. |
| `X-Action-Approval` | String | Explicit human approval header (`approved` or `true`) required for destructive or deployment operations in production. |
| `X-Correlation-ID` | String | Optional client trace identifier. Returned in all responses for distributed log correlation. |
| `X-Idempotency-Key` | String | Idempotency token preventing duplicate task creation or execution dispatch. |

### Error Envelope

All API errors return a sanitized JSON error payload preventing stack trace disclosure:

```json
{
  "detail": "Descriptive human-readable explanation of error.",
  "correlation_id": "corr-3f82a19b4e72"
}
```

---

## 2. Health & Readiness Probes

### `GET /health` and `GET /api/v1/health`
Inspect overall platform subsystem health, database connectivity, and sandbox Docker availability.

**Response `200 OK`:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development",
  "timestamp": "2026-10-22T12:00:00.000000Z",
  "database": "connected",
  "sandbox_available": true,
  "worker": {
    "status": "RUNNING",
    "healthy": true,
    "uptime_seconds": 124.5,
    "heartbeat_age_seconds": 1.2,
    "last_heartbeat": "2026-10-22T12:00:00.000000Z",
    "active_tasks": 0,
    "recovered_tasks": 0,
    "completed_tasks": 1
  }
}
```

### `GET /ready` and `GET /api/v1/ready`
Kubernetes and load-balancer readiness probe.

**Response `200 OK`:**
```json
{
  "ready": true,
  "database": "connected",
  "worker_healthy": true,
  "timestamp": "2026-10-22T12:00:00.000000Z"
}
```
*Note: Returns `503 Service Unavailable` if PostgreSQL is disconnected.*

### `GET /health/worker` and `GET /api/v1/health/worker`
Dedicated health metrics from the background supervisor.

---

## 3. Software Engineering Tasks API (`/api/v1/tasks`)

### `POST /api/v1/tasks`
Register a new engineering bug or task.

**Headers:**
- `X-Idempotency-Key` (Optional)

**Request Body:**
```json
{
  "project_id": "proj-default",
  "title": "Fix calculate_tax operator in calculator.py",
  "problem_statement": "calculate_tax uses addition instead of multiplication.",
  "task_type": "BUG_FIX",
  "priority": "HIGH",
  "base_commit": "HEAD",
  "reproduce_command": "pytest test_calculator.py",
  "metadata": {
    "repo_path": "/workspace/sample-repo"
  }
}
```

**Response `201 Created`:**
```json
{
  "id": "task_4a89bc21",
  "project_id": "proj-default",
  "repository_id": null,
  "title": "Fix calculate_tax operator in calculator.py",
  "problem_statement": "calculate_tax uses addition instead of multiplication.",
  "task_type": "BUG_FIX",
  "status": "OPEN",
  "priority": "HIGH",
  "base_commit": "HEAD",
  "reproduce_command": "pytest test_calculator.py",
  "metadata": {
    "repo_path": "/workspace/sample-repo"
  },
  "created_at": "2026-10-22T12:01:00.000000Z",
  "updated_at": "2026-10-22T12:01:00.000000Z",
  "runs_count": 0,
  "latest_run_status": null
}
```

### `GET /api/v1/tasks`
Paginated task listing with status and text filtering.

**Query Parameters:**
- `page` (int, default: `1`)
- `page_size` (int, default: `20`, max: `100`)
- `status` (string, optional: `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`)
- `priority` (string, optional: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
- `task_type` (string, optional: `BUG_FIX`, `FEATURE`, `REFACTOR`, `INVESTIGATION`)
- `search` (string, optional: full-text title and problem statement match)

---

## 4. Execution Runs API (`/api/v1/runs`)

### `POST /api/v1/runs`
Launch an autonomous debugging or patch synthesis run on an issue.

**Request Body:**
```json
{
  "task_id": "task_4a89bc21",
  "model_provider": "anthropic/claude-3-5-sonnet-20241022",
  "model_configuration_id": null,
  "configuration_snapshot": {
    "temperature": 0.0,
    "max_retries": 3
  }
}
```

**Response `201 Created`:**
```json
{
  "id": "run_9f28cb110a",
  "task_id": "task_4a89bc21",
  "status": "PENDING",
  "model_provider": "anthropic/claude-3-5-sonnet-20241022",
  "current_step": "VALIDATE_TASK",
  "iteration_count": 0,
  "total_tokens": 0,
  "cost_estimate_usd": 0.0,
  "patch_diff": null,
  "started_at": null,
  "completed_at": null,
  "created_at": "2026-10-22T12:02:00.000000Z"
}
```

### `GET /api/v1/runs/{run_id}`
Retrieve live status, token counts, cost estimate, and synthesized patch diff.

### `GET /api/v1/runs/{run_id}/events`
Retrieve chronological sequence of agent steps, tool invocations, and audit logs.

**Response `200 OK`:**
```json
[
  {
    "event_id": "step_1",
    "run_id": "run_9f28cb110a",
    "event_type": "AGENT_STEP",
    "sequence": 1,
    "timestamp": "2026-10-22T12:02:01.000000Z",
    "data": {
      "step_number": 1,
      "step_name": "INSPECT_REPO",
      "status": "COMPLETED",
      "thought": "Inspecting repository files and symbols",
      "tokens_used": 420
    }
  },
  {
    "event_id": "tool_1",
    "run_id": "run_9f28cb110a",
    "event_type": "TOOL_INVOCATION",
    "sequence": 2,
    "timestamp": "2026-10-22T12:02:02.000000Z",
    "data": {
      "tool_name": "run_allowlisted_tests",
      "parameters": {"test_runner": "pytest"},
      "result": {"exit_code": 0, "tests_passed": 1},
      "status": "SUCCESS"
    }
  }
]
```

### `POST /api/v1/runs/{run_id}/cancel`
Cancel an active run and propagate cancellation to execution tokens and containers.

---

## 5. Code Intelligence API (`/api/v1/code-intel`)

### `POST /api/v1/code-intel/index`
Trigger Tree-sitter AST indexing for a local git repository.

**Request Body:**
```json
{
  "repo_path": "/workspace/sample-repo",
  "incremental": true
}
```

### `GET /api/v1/code-intel/search`
Perform hybrid lexical and AST symbol search.

**Query Parameters:**
- `repo_path` (string)
- `query` (string)
- `mode` (`lexical`, `semantic`, `hybrid`, default: `hybrid`)
- `limit` (int, default: `10`, max: `50`)

---

## 6. Memory Subsystem API (`/api/v1/memory`)

### `POST /api/v1/memory`
Record an episodic or procedural debugging memory.

**Request Body:**
```json
{
  "memory_type": "EPISODIC",
  "key": "fix_calculator_operator",
  "content": "Operator mutation in calculator.py resolved by multiplying amount * rate.",
  "task_id": "task_4a89bc21",
  "confidence": 0.95,
  "verification_status": "VERIFIED",
  "evidence": ["test_calculator.py exit_code=0"]
}
```

### `GET /api/v1/memory/search`
Search memory records using vector cosine similarity or lexical fallback.

**Query Parameters:**
- `query` (string)
- `memory_type` (`EPISODIC`, `PROCEDURAL`, `SEMANTIC`, optional)
- `limit` (int, default: `5`)

---

## 7. Model Provider Configuration API (`/api/v1/models`)

### `GET /api/v1/models`
List configured active model providers and pricing tiers.

### `POST /api/v1/models`
Register an LLM routing configuration (Claude 3.5 Sonnet, GPT-4o, Gemini 2.5 Flash, Ollama / vLLM).
