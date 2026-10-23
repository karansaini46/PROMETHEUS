/**
 * Shared Type Definitions for PROMETHEUS Autonomous AI Engineering Platform
 */

export type RunStatus =
  | "PENDING"
  | "RUNNING"
  | "PAUSED"
  | "VERIFYING"
  | "RESOLVED"
  | "FAILED"
  | "CANCELLED";

export type TaskStatus =
  | "OPEN"
  | "IN_PROGRESS"
  | "RESOLVED"
  | "CLOSED"
  | "CANCELLED";

export type TaskType =
  | "BUG_FIX"
  | "FEATURE"
  | "REFACTOR"
  | "BENCHMARK_EVAL";

export type TaskPriority =
  | "LOW"
  | "MEDIUM"
  | "HIGH"
  | "CRITICAL";

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  environment: string;
  timestamp: string;
  database: "connected" | "disconnected" | "disabled";
  sandbox_available: boolean;
  worker?: {
    status?: string;
    healthy?: boolean;
    uptime_seconds?: number;
    heartbeat_age_seconds?: number;
    active_tasks?: number;
    [key: string]: unknown;
  } | null;
}

export interface ReadinessResponse {
  ready: boolean;
  database: string;
  timestamp: string;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  repository_url?: string | null;
  default_branch: string;
  created_at: string;
  updated_at: string;
}

export interface RepositoryRegistration {
  id: string;
  project_id: string;
  name: string;
  repo_url: string;
  default_branch: string;
  auth_type: string;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  project_id: string;
  repository_id?: string | null;
  title: string;
  problem_statement: string;
  task_type: TaskType;
  status: TaskStatus;
  priority: TaskPriority;
  base_commit?: string | null;
  reproduce_command?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  runs_count?: number;
  latest_run_status?: RunStatus | null;
}

export interface TaskCreatePayload {
  project_id: string;
  title: string;
  problem_statement: string;
  task_type?: TaskType;
  priority?: TaskPriority;
  repository_id?: string | null;
  base_commit?: string | null;
  reproduce_command?: string | null;
  metadata?: Record<string, unknown>;
}

export interface TaskUpdatePayload {
  title?: string;
  problem_statement?: string;
  task_type?: TaskType;
  status?: TaskStatus;
  priority?: TaskPriority;
  base_commit?: string | null;
  reproduce_command?: string | null;
  metadata?: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ExecutionRun {
  id: string;
  task_id: string;
  issue_id?: string;
  model_configuration_id?: string | null;
  status: RunStatus;
  model_provider: string;
  iteration_count: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate_usd: number;
  current_step?: string | null;
  patch_diff?: string | null;
  error_message?: string | null;
  configuration_snapshot?: Record<string, unknown>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateRunPayload {
  task_id?: string;
  issue_id?: string;
  model_configuration_id?: string | null;
  model_provider?: string;
  configuration_snapshot?: Record<string, unknown>;
}

export interface RunEventResponse {
  event_id: string;
  run_id: string;
  event_type: "AGENT_STEP" | "TOOL_INVOCATION" | "AUDIT_EVENT" | string;
  sequence: number;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface ModelConfiguration {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  api_base_url?: string | null;
  temperature: number;
  max_tokens: number;
  context_window: number;
  cost_per_million_input_tokens: number;
  cost_per_million_output_tokens: number;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ModelConfigurationCreatePayload {
  name: string;
  provider: string;
  model_name: string;
  api_base_url?: string | null;
  temperature?: number;
  max_tokens?: number;
  context_window?: number;
  cost_per_million_input_tokens?: number;
  cost_per_million_output_tokens?: number;
  is_active?: boolean;
  settings?: Record<string, unknown>;
}

export interface ExperimentDefinition {
  id: string;
  name: string;
  description?: string | null;
  hypothesis?: string | null;
  model_configuration_id?: string | null;
  parameters: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExperimentCreatePayload {
  name: string;
  description?: string | null;
  hypothesis?: string | null;
  model_configuration_id?: string | null;
  parameters?: Record<string, unknown>;
  is_active?: boolean;
}

export interface ExperimentResult {
  id: string;
  experiment_id: string;
  evaluation_run_id?: string | null;
  run_id?: string | null;
  metric_name: string;
  metric_value: number;
  details: Record<string, unknown>;
  created_at: string;
}

export interface EvaluationDataset {
  id: string;
  name: string;
  description?: string | null;
  version: string;
  source_url?: string | null;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface EvaluationCase {
  id: string;
  dataset_id: string;
  instance_id: string;
  repository_name: string;
  base_commit: string;
  problem_statement: string;
  test_patch?: string | null;
  reference_patch?: string | null;
  hints_text?: string | null;
  created_at: string;
}

export interface EvaluationRun {
  id: string;
  dataset_id: string;
  model_configuration_id?: string | null;
  status: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  total_cost_usd: number;
  summary_metrics: Record<string, unknown>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface MemoryRecord {
  id: string;
  project_id?: string | null;
  run_id?: string | null;
  memory_type: string;
  key: string;
  content: string;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  run_id?: string | null;
  action: string;
  actor: string;
  resource_type?: string | null;
  resource_id?: string | null;
  ip_address?: string | null;
  correlation_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface PatchReviewItem {
  run_id: string;
  task_id: string;
  task_title: string;
  status: RunStatus;
  patch_diff: string;
  affected_files: string[];
  test_status: "PASSED" | "FAILED" | "PENDING";
  approved?: boolean;
}

export interface SystemSettings {
  api_url: string;
  theme: "dark" | "system";
  telemetry_enabled: boolean;
  default_model: string;
  execution_timeout_seconds: number;
  sandbox_memory_limit: string;
  sandbox_cpu_limit: number;
  require_auth: boolean;
  api_key?: string;
  demo_mode: boolean;
}
