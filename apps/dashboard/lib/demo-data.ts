/**
 * Realistic Sample Data for Labeled DEMO MODE.
 * Used exclusively when the user toggles Demo Mode or when the backend is offline.
 * Clearly labeled to avoid fabricating fake metrics in production.
 */

import type {
  EvaluationDataset,
  EvaluationRun,
  ExecutionRun,
  ExperimentDefinition,
  ExperimentResult,
  MemoryRecord,
  ModelConfiguration,
  PatchReviewItem,
  Project,
  RunEventResponse,
  Task,
} from "@prometheus/shared-types";

export const DEMO_PROJECTS: Project[] = [
  {
    id: "proj-core-001",
    name: "Prometheus Engineering Monorepo",
    slug: "prometheus-core",
    description: "Autonomous debugging engine, tree-sitter symbol indexing, and Docker sandbox execution plane.",
    repository_url: "https://github.com/prometheus/sample-workspace.git",
    default_branch: "main",
    created_at: "2026-10-01T08:00:00Z",
    updated_at: "2026-10-10T12:00:00Z",
  },
  {
    id: "proj-django-002",
    name: "Django Web Framework Target",
    slug: "django-eval",
    description: "SWE-bench benchmark target repository for evaluating query serialization and ORM bug fixing.",
    repository_url: "https://github.com/django/django.git",
    default_branch: "main",
    created_at: "2026-10-02T10:30:00Z",
    updated_at: "2026-10-09T18:45:00Z",
  },
];

export const DEMO_TASKS: Task[] = [
  {
    id: "task-ast-101",
    project_id: "proj-core-001",
    title: "Fix off-by-one token boundary in session expiration validator",
    problem_statement:
      "Sessions expiring exactly at boundary timestamps are rejected prematurely. The comparison in auth/tokens.py line 45 should use <= instead of <. Reproduction test fails with premature 401 Unauthorized.",
    task_type: "BUG_FIX",
    status: "RESOLVED",
    priority: "HIGH",
    base_commit: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
    reproduce_command: "pytest tests/test_tokens.py -k test_boundary_expiry",
    metadata: { component: "auth_service", severity: "P1" },
    created_at: "2026-10-10T10:15:00Z",
    updated_at: "2026-10-10T10:45:00Z",
    runs_count: 2,
    latest_run_status: "RESOLVED",
  },
  {
    id: "task-ast-102",
    project_id: "proj-core-001",
    title: "Tree-sitter AST visitor omits inner class method definitions",
    problem_statement:
      "AST symbol indexer fails to record nested method declarations inside subclasses. Call hierarchy graph is incomplete when analyzing complex OOP models in Python and TypeScript.",
    task_type: "BUG_FIX",
    status: "IN_PROGRESS",
    priority: "CRITICAL",
    base_commit: "c3d4e5f60718293a4b5c6d7e8f9012345678a1b2",
    reproduce_command: "pytest tests/test_ast_parser.py -k test_nested_classes",
    metadata: { component: "code_intel", severity: "P0" },
    created_at: "2026-10-10T11:00:00Z",
    updated_at: "2026-10-10T11:30:00Z",
    runs_count: 1,
    latest_run_status: "RUNNING",
  },
  {
    id: "task-ast-103",
    project_id: "proj-django-002",
    title: "Django query compiler drops nested exclude filters across M2M relationships",
    problem_statement:
      "When compiling queryset with multiple negated conditions across ManyToMany relations, SQL generator drops the second JOIN clause, returning incorrect row sets.",
    task_type: "BUG_FIX",
    status: "OPEN",
    priority: "HIGH",
    base_commit: "e5f60718293a4b5c6d7e8f9012345678a1b2c3d4",
    reproduce_command: "python tests/runtests.py queries.test_m2m_exclude",
    metadata: { benchmark: "swe_bench_verified", instance_id: "django__django-11099" },
    created_at: "2026-10-10T12:00:00Z",
    updated_at: "2026-10-10T12:00:00Z",
    runs_count: 0,
    latest_run_status: null,
  },
  {
    id: "task-ast-104",
    project_id: "proj-core-001",
    title: "Implement jittered exponential backoff for LLM provider socket timeouts",
    problem_statement:
      "Network calls to Anthropic Messages API throw abrupt socket timeouts during peak hours. Need robust retry handler with full jitter and max 3 attempts before fallback.",
    task_type: "FEATURE",
    status: "RESOLVED",
    priority: "MEDIUM",
    base_commit: "f60718293a4b5c6d7e8f9012345678a1b2c3d4e5",
    reproduce_command: "pytest tests/test_model_providers.py -k test_socket_timeout",
    metadata: { component: "model_router" },
    created_at: "2026-10-09T14:00:00Z",
    updated_at: "2026-10-09T15:20:00Z",
    runs_count: 1,
    latest_run_status: "RESOLVED",
  },
];

export const DEMO_RUNS: ExecutionRun[] = [
  {
    id: "run_94a8f102c91448b18a38b1d9",
    task_id: "task-ast-101",
    status: "RESOLVED",
    model_provider: "anthropic/claude-3-5-sonnet-20241022",
    iteration_count: 2,
    total_tokens: 18450,
    prompt_tokens: 14200,
    completion_tokens: 4250,
    cost_estimate_usd: 0.106,
    current_step: "VERIFY_PATCH",
    patch_diff: `--- a/auth/tokens.py
+++ b/auth/tokens.py
@@ -42,7 +42,7 @@ def verify_session_token(token: str, current_time: int) -> bool:
     payload = decode_jwt_payload(token)
     expires_at = payload.get("exp", 0)
-    if current_time >= expires_at:
+    if current_time > expires_at:
         return False
     return True`,
    error_message: null,
    started_at: "2026-10-10T10:20:00Z",
    completed_at: "2026-10-10T10:24:12Z",
    created_at: "2026-10-10T10:20:00Z",
    updated_at: "2026-10-10T10:24:12Z",
  },
  {
    id: "run_b219084cf730419ea78b1932",
    task_id: "task-ast-102",
    status: "RUNNING",
    model_provider: "anthropic/claude-3-5-sonnet-20241022",
    iteration_count: 1,
    total_tokens: 9820,
    prompt_tokens: 8100,
    completion_tokens: 1720,
    cost_estimate_usd: 0.050,
    current_step: "SYNTHESIZE_PATCH",
    patch_diff: null,
    error_message: null,
    started_at: "2026-10-10T11:10:00Z",
    completed_at: null,
    created_at: "2026-10-10T11:10:00Z",
    updated_at: "2026-10-10T11:15:20Z",
  },
  {
    id: "run_c848102a901f4810819fa104",
    task_id: "task-ast-104",
    status: "RESOLVED",
    model_provider: "openai/gpt-4o-2024-08-06",
    iteration_count: 1,
    total_tokens: 12150,
    prompt_tokens: 9500,
    completion_tokens: 2650,
    cost_estimate_usd: 0.050,
    current_step: "VERIFY_PATCH",
    patch_diff: `--- a/services/models/router.py
+++ b/services/models/router.py
@@ -104,6 +104,12 @@ async def call_provider_with_retry(prompt: str, max_retries: int = 3):
+    for attempt in range(max_retries):
+        try:
+            return await execute_call(prompt)
+        except (TimeoutError, SocketError) as exc:
+            delay = (2 ** attempt) + random.uniform(0, 1)
+            await asyncio.sleep(delay)`,
    error_message: null,
    started_at: "2026-10-09T14:10:00Z",
    completed_at: "2026-10-09T14:13:45Z",
    created_at: "2026-10-09T14:10:00Z",
    updated_at: "2026-10-09T14:13:45Z",
  },
];

export const DEMO_RUN_EVENTS: Record<string, RunEventResponse[]> = {
  run_94a8f102c91448b18a38b1d9: [
    {
      event_id: "ev-01",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "AGENT_STEP",
      sequence: 1,
      timestamp: "2026-10-10T10:20:05Z",
      data: {
        step_number: 1,
        step_name: "INITIALIZED",
        thought: "Ingested problem statement. Inspecting auth/tokens.py and reproduction test suite.",
        status: "COMPLETED",
        tokens_used: 120,
        latency_ms: 180,
      },
    },
    {
      event_id: "ev-02",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "TOOL_INVOCATION",
      sequence: 2,
      timestamp: "2026-10-10T10:20:12Z",
      data: {
        tool_name: "grep_search",
        parameters: { query: "verify_session_token", path: "auth/" },
        result: { matches: 1, file: "auth/tokens.py", line: 42 },
        status: "SUCCESS",
        duration_ms: 45,
      },
    },
    {
      event_id: "ev-03",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "AGENT_STEP",
      sequence: 3,
      timestamp: "2026-10-10T10:21:00Z",
      data: {
        step_number: 2,
        step_name: "LOCALIZE_FAULT",
        thought: "Found expiry comparison check: 'if current_time >= expires_at:'. Equality comparison causes premature expiry on the exact boundary second.",
        status: "COMPLETED",
        tokens_used: 3450,
        latency_ms: 2100,
      },
    },
    {
      event_id: "ev-04",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "TOOL_INVOCATION",
      sequence: 4,
      timestamp: "2026-10-10T10:21:40Z",
      data: {
        tool_name: "docker_sandbox_exec",
        parameters: { command: "pytest tests/test_tokens.py -k test_boundary_expiry" },
        result: { exit_code: 1, stdout: "FAILED tests/test_tokens.py::test_boundary_expiry - AssertionError" },
        status: "SUCCESS",
        duration_ms: 1250,
      },
    },
    {
      event_id: "ev-05",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "AGENT_STEP",
      sequence: 5,
      timestamp: "2026-10-10T10:22:30Z",
      data: {
        step_number: 3,
        step_name: "SYNTHESIZE_PATCH",
        thought: "Generated unified diff changing `>=` to `>`. Applying diff to isolated git worktree.",
        status: "COMPLETED",
        tokens_used: 4200,
        latency_ms: 3200,
      },
    },
    {
      event_id: "ev-06",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "TOOL_INVOCATION",
      sequence: 6,
      timestamp: "2026-10-10T10:23:45Z",
      data: {
        tool_name: "docker_sandbox_exec",
        parameters: { command: "pytest tests/test_tokens.py", network: "none" },
        result: { exit_code: 0, stdout: "14 passed in 0.42s" },
        status: "SUCCESS",
        duration_ms: 1890,
      },
    },
    {
      event_id: "ev-07",
      run_id: "run_94a8f102c91448b18a38b1d9",
      event_type: "AUDIT_EVENT",
      sequence: 7,
      timestamp: "2026-10-10T10:24:12Z",
      data: {
        action: "RUN_RESOLVED",
        actor: "prometheus-orchestrator",
        details: { pass_rate: "100%", all_tests_passed: true },
      },
    },
  ],
};

export const DEMO_MODELS: ModelConfiguration[] = [
  {
    id: "model-claude-35",
    name: "claude-3-5-sonnet",
    provider: "anthropic",
    model_name: "claude-3-5-sonnet-20241022",
    api_base_url: null,
    temperature: 0.0,
    max_tokens: 8192,
    context_window: 200000,
    cost_per_million_input_tokens: 3.0,
    cost_per_million_output_tokens: 15.0,
    is_active: true,
    settings: { stream: true, tool_choice: "auto" },
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-10T00:00:00Z",
  },
  {
    id: "model-gpt-4o",
    name: "gpt-4o",
    provider: "openai",
    model_name: "gpt-4o-2024-08-06",
    api_base_url: null,
    temperature: 0.0,
    max_tokens: 4096,
    context_window: 128000,
    cost_per_million_input_tokens: 2.5,
    cost_per_million_output_tokens: 10.0,
    is_active: true,
    settings: { json_mode: true },
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-10T00:00:00Z",
  },
  {
    id: "model-qwen-local",
    name: "qwen2.5-coder-local",
    provider: "local",
    model_name: "qwen2.5-coder:7b",
    api_base_url: "http://localhost:11434/v1",
    temperature: 0.0,
    max_tokens: 4096,
    context_window: 32768,
    cost_per_million_input_tokens: 0.0,
    cost_per_million_output_tokens: 0.0,
    is_active: true,
    settings: { offline_mode: true },
    created_at: "2026-10-05T00:00:00Z",
    updated_at: "2026-10-10T00:00:00Z",
  },
];

export const DEMO_EXPERIMENTS: ExperimentDefinition[] = [
  {
    id: "exp-ast-vs-grep",
    name: "baseline-ast-vs-ripgrep-fault-localization",
    description: "Evaluates token efficiency of AST symbol graphs versus raw lexical ripgrep over 50 Python repositories.",
    hypothesis: "Structural symbol navigation reduces localization prompt tokens by 42% while preserving pass@1 accuracy.",
    model_configuration_id: "model-claude-35",
    parameters: { max_depth: 3, enable_ast: true },
    is_active: true,
    created_at: "2026-10-08T09:00:00Z",
    updated_at: "2026-10-10T09:00:00Z",
  },
  {
    id: "exp-reflection-loop",
    name: "self-reflection-retry-budget-study",
    description: "Ablation on test failure reflection iterations (1 vs 3 vs 5 iterations) on SWE-bench Lite.",
    hypothesis: "Limiting reflection iterations to 3 maximizes cost-adjusted patch accuracy before diminishing returns.",
    model_configuration_id: "model-claude-35",
    parameters: { max_iterations: 3, sandbox_retries: 2 },
    is_active: true,
    created_at: "2026-10-09T14:30:00Z",
    updated_at: "2026-10-10T10:00:00Z",
  },
];

export const DEMO_EXPERIMENT_RESULTS: ExperimentResult[] = [
  {
    id: "res-01",
    experiment_id: "exp-ast-vs-grep",
    metric_name: "token_reduction_pct",
    metric_value: 41.8,
    details: { baseline_tokens: 32000, ast_tokens: 18600, sample_size: 40 },
    created_at: "2026-10-10T09:15:00Z",
  },
  {
    id: "res-02",
    experiment_id: "exp-ast-vs-grep",
    metric_name: "localization_precision_at_3",
    metric_value: 88.5,
    details: { true_positives: 35, false_positives: 5 },
    created_at: "2026-10-10T09:30:00Z",
  },
  {
    id: "res-03",
    experiment_id: "exp-reflection-loop",
    metric_name: "pass_at_1_accuracy",
    metric_value: 38.2,
    details: { resolved_instances: 19, total_instances: 50 },
    created_at: "2026-10-10T10:15:00Z",
  },
];

export const DEMO_EVALUATION_DATASETS: EvaluationDataset[] = [
  {
    id: "ds-swe-lite",
    name: "swe-bench-lite-verified",
    description: "Official 300-instance subset of verified software engineering tasks with test oracles.",
    version: "1.0.0",
    source_url: "https://github.com/princeton-nlp/SWE-bench",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-10T00:00:00Z",
  },
  {
    id: "ds-synthetic-py",
    name: "synthetic-python-syntax-edge-cases",
    description: "Curated 50 synthetic off-by-one, typing, and concurrency bugs in Python 3.12.",
    version: "2.1.0",
    source_url: "https://prometheus.internal/benchmarks/synthetic",
    created_at: "2026-10-05T00:00:00Z",
    updated_at: "2026-10-10T00:00:00Z",
  },
];

export const DEMO_EVALUATION_RUNS: EvaluationRun[] = [
  {
    id: "evalrun-swe-01",
    dataset_id: "ds-swe-lite",
    model_configuration_id: "model-claude-35",
    status: "COMPLETED",
    total_cases: 50,
    passed_cases: 21,
    failed_cases: 29,
    total_cost_usd: 8.45,
    summary_metrics: { pass_at_1: 42.0, avg_time_sec: 145, avg_tokens: 24500 },
    started_at: "2026-10-09T08:00:00Z",
    completed_at: "2026-10-09T11:45:00Z",
    created_at: "2026-10-09T08:00:00Z",
  },
  {
    id: "evalrun-synthetic-02",
    dataset_id: "ds-synthetic-py",
    model_configuration_id: "model-claude-35",
    status: "COMPLETED",
    total_cases: 50,
    passed_cases: 46,
    failed_cases: 4,
    total_cost_usd: 2.15,
    summary_metrics: { pass_at_1: 92.0, avg_time_sec: 42, avg_tokens: 8200 },
    started_at: "2026-10-10T04:00:00Z",
    completed_at: "2026-10-10T05:12:00Z",
    created_at: "2026-10-10T04:00:00Z",
  },
];

export const DEMO_MEMORY_RECORDS: MemoryRecord[] = [
  {
    id: "mem-01",
    project_id: "proj-core-001",
    run_id: "run_94a8f102c91448b18a38b1d9",
    memory_type: "CODE_PATTERN",
    key: "jwt_boundary_condition_pattern",
    content: "When verifying expiration timestamps on JWT tokens, standard specification RFC 7519 requires tokens with current_time equal to exp to be valid until the next second.",
    metadata_json: { standard: "RFC-7519", language: "python" },
    created_at: "2026-10-10T10:25:00Z",
    updated_at: "2026-10-10T10:25:00Z",
  },
  {
    id: "mem-02",
    project_id: "proj-core-001",
    run_id: null,
    memory_type: "FAILURE_MODE",
    key: "tree_sitter_nested_scope_traversal",
    content: "Python grammar in tree-sitter treats inner class function definitions as nested inside block bodies. Using direct child query misses nested methods unless recursing through block statements.",
    metadata_json: { parser: "tree-sitter-python" },
    created_at: "2026-10-09T18:00:00Z",
    updated_at: "2026-10-09T18:00:00Z",
  },
  {
    id: "mem-03",
    project_id: "proj-django-002",
    run_id: null,
    memory_type: "LESSON_LEARNED",
    key: "django_m2m_query_compilation_invariant",
    content: "Negated conditions in django.db.models.sql.compiler require aliasing subqueries with an outer join before applying WHERE NOT IN conditions.",
    metadata_json: { subsystem: "orm_compiler" },
    created_at: "2026-10-08T12:00:00Z",
    updated_at: "2026-10-08T12:00:00Z",
  },
];

export const DEMO_PATCH_REVIEWS: PatchReviewItem[] = [
  {
    run_id: "run_94a8f102c91448b18a38b1d9",
    task_id: "task-ast-101",
    task_title: "Fix off-by-one token boundary in session expiration validator",
    status: "RESOLVED",
    patch_diff: `diff --git a/auth/tokens.py b/auth/tokens.py
index e83b91a..d2a1b94 100644
--- a/auth/tokens.py
+++ b/auth/tokens.py
@@ -40,9 +40,9 @@ def verify_session_token(token: str, current_time: int) -> bool:
     """Validate token validity window against current clock."""
     payload = decode_jwt_payload(token)
     expires_at = payload.get("exp", 0)
-    if current_time >= expires_at:
+    if current_time > expires_at:
         return False
     return True
`,
    affected_files: ["auth/tokens.py"],
    test_status: "PASSED",
    approved: true,
  },
  {
    run_id: "run_c848102a901f4810819fa104",
    task_id: "task-ast-104",
    task_title: "Implement jittered exponential backoff for LLM provider socket timeouts",
    status: "RESOLVED",
    patch_diff: `diff --git a/services/models/router.py b/services/models/router.py
index 920f1a2..184a29c 100644
--- a/services/models/router.py
+++ b/services/models/router.py
@@ -102,6 +102,15 @@ async def call_provider_with_retry(prompt: str, max_retries: int = 3):
     """Route generation call with jittered exponential backoff."""
+    for attempt in range(max_retries):
+        try:
+            return await execute_call(prompt)
+        except (TimeoutError, SocketError) as exc:
+            if attempt == max_retries - 1:
+                raise exc
+            delay = (2 ** attempt) + random.uniform(0.1, 0.5)
+            await asyncio.sleep(delay)
`,
    affected_files: ["services/models/router.py"],
    test_status: "PASSED",
    approved: false,
  },
];
