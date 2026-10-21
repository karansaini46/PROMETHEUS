# PROMETHEUS — Operational Troubleshooting Guide

This guide provides operational runbooks, diagnostic commands, and recovery procedures for engineers deploying, monitoring, and debugging the PROMETHEUS autonomous software engineering platform.

---

## 1. System Health & Probes

PROMETHEUS exposes three primary health check endpoints:

| Endpoint | Purpose | Healthy Response | Unhealthy Trigger |
| :--- | :--- | :--- | :--- |
| `GET /api/v1/health` | Overall system liveness & supervisor status | `{"status": "healthy", "worker": {...}}` | Database connection lost or worker stopped |
| `GET /api/v1/ready` | Readiness probe for traffic routing | `{"status": "ready"}` | Database pool unreachable |
| `GET /api/v1/health/worker` | Dedicated worker supervisor metrics | Detailed uptime, active tasks, heartbeat timestamp | Heartbeat older than 15 seconds |

### Checking Worker Supervisor Status
```bash
curl -s http://localhost:8000/api/v1/health/worker | jq .
```
Expected output:
```json
{
  "status": "RUNNING",
  "healthy": true,
  "uptime_seconds": 1240.5,
  "heartbeat_age_seconds": 1.2,
  "last_heartbeat": "2026-10-21T11:25:00.000000+00:00",
  "active_tasks": 2,
  "recovered_tasks": 0,
  "completed_tasks": 14
}
```

If `"healthy": false` or `"heartbeat_age_seconds" > 15`:
The worker process event loop is likely blocked or deadlocked by a synchronous operation. Proceed to [Section 5: High CPU / Blocked Event Loop](#5-high-cpu--blocked-event-loop).

---

## 2. Distributed Tracing & Correlation IDs

Every incoming request and agent operation is assigned a unique `X-Correlation-ID`. This ID is:
1. Generated at the API gateway if absent from request headers.
2. Returned in every response header (`X-Correlation-ID`).
3. Embedded into all structured logs (`"correlation_id": "..."`).
4. Propagated through OpenTelemetry spans and context variables across service boundaries.

### Tracing a Request End-to-End
1. Retrieve the Correlation ID from client response headers or error payload:
   ```bash
   curl -i http://localhost:8000/api/v1/tasks
   # Note: X-Correlation-ID: 7a8f3b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c
   ```
2. Grep backend logs for this correlation ID:
   ```bash
   grep "7a8f3b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c" /var/log/prometheus/api.log | jq .
   ```
3. Locate the OpenTelemetry trace in Jaeger / Grafana Tempo using the `trace_id` logged alongside the correlation ID.

---

## 3. Crash Recovery & Orphaned Tasks

When a host restarts or a worker crashes abruptly during task execution, in-flight runs could be left stranded in `RUNNING` or `PENDING` states.

### Automatic Startup Recovery
Upon API startup, the `WorkerManager` automatically executes `recover_interrupted_tasks()`:
- Identifies runs where `status IN ('RUNNING', 'PENDING')`.
- Transitions runs to `FAILED` with details: `"Process terminated abruptly: host restarted or worker crashed during execution."`.
- Resets corresponding tasks from `IN_PROGRESS` back to `OPEN` for safe retry.
- Emits immutable `AuditEvent` records with action `RUN_RECOVERED_AFTER_INTERRUPTION`.

### Manual Recovery Trigger via CLI
If you suspect orphaned runs without restarting the server:
```bash
python -c "
import asyncio
from services.api.db import get_db_session
from services.api.worker import recover_interrupted_tasks

async def run():
    async for db in get_db_session():
        count = await recover_interrupted_tasks(db)
        print(f'Recovered {count} orphaned runs.')

asyncio.run(run())
"
```

---

## 4. Abandoned Resource Pruning (Worktrees & Containers)

If container runners are forcefully terminated, temporary git worktrees or Docker sandbox containers may remain on disk.

### Automatic Cleanup
`WorkerManager.cleanup_abandoned_resources()` runs automatically during graceful worker shutdown (`lifespan` teardown).

### Manual Emergency Cleanup
To manually prune dangling worktrees and containers:
```bash
# 1. Prune dangling Docker sandbox containers
docker ps -a --filter "name=prometheus-sandbox-" -q | xargs -r docker rm -f

# 2. Prune orphaned git worktrees across registered repositories
git worktree prune

# 3. Trigger internal supervisor cleanup routine
python -c "
from services.api.worker import cleanup_abandoned_resources
result = cleanup_abandoned_resources()
print('Cleanup completed:', result)
"
```

---

## 5. Common HTTP Error Codes & Runbooks

### HTTP 401 Unauthorized
- **Cause:** `REQUIRE_AUTH=True` is enabled, but the caller did not supply `X-API-Key` or `Authorization: Bearer <token>`.
- **Resolution:** Provide the configured `API_SECRET_KEY` in the request header:
  ```bash
  curl -H "X-API-Key: $PROMETHEUS_API_KEY" http://localhost:8000/api/v1/tasks
  ```

### HTTP 403 Forbidden
- **Scenario A: Administrative Endpoint Access Denied**
  - **Cause:** Calling an administrative route (e.g. `DELETE /api/v1/memory/{id}`) without administrative credentials.
  - **Resolution:** Supply the dedicated `X-Admin-Key` matching `ADMIN_SECRET_KEY`.
- **Scenario B: Explicit Approval Required**
  - **Cause:** In production environments or when `REQUIRE_APPROVAL_FOR_DESTRUCTIVE=True`, destructive actions require explicit operator sign-off.
  - **Resolution:** Pass the approval header:
    ```bash
    curl -X DELETE \
      -H "X-Admin-Key: $ADMIN_SECRET_KEY" \
      -H "X-Action-Approval: approved" \
      http://localhost:8000/api/v1/memory/rec-12345
    ```

### HTTP 413 Payload Too Large
- **Cause:** Request body exceeds `MAX_REQUEST_BODY_BYTES` (default 10 MB).
- **Resolution:** Ensure large attachments or diffs are compressed or split before upload. Adjust `MAX_REQUEST_BODY_BYTES` in environment configuration if large repository patches are legitimate.

### HTTP 429 Too Many Requests
- **Cause:** Client IP or token exceeded `RATE_LIMIT_PER_MINUTE` (default 300 req/min).
- **Resolution:** Inspect the `Retry-After` response header and implement exponential backoff with jitter in client integrations.

### HTTP 504 Gateway Timeout
- **Cause:** Request processing exceeded `REQUEST_TIMEOUT_SECONDS` (default 60s).
- **Resolution:** For long-running operations (like model generation or sandbox test runs), dispatch tasks asynchronously via the background worker queue rather than synchronously awaiting completion on HTTP endpoints.

---

## 6. Log Redaction Verification

To confirm that sensitive secrets and credentials are not leaking into logs:
```bash
# Test structured log output for secret scrubbing
pytest tests/security/test_model_secrets.py -v
pytest tests/security/test_hardening_security.py -k test_sanitize_message_for_client
```
All bearer tokens, GitHub PATs, and Anthropic/OpenAI API keys will automatically appear as `[REDACTED_SECRET]` or `[REDACTED_KEY]`.
