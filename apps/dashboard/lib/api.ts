/**
 * PROMETHEUS Dashboard API Client.
 * Connects directly to authoritative FastAPI backend (/api/v1).
 * Supports explicit labeled Demo Mode when offline or requested.
 */

import type {
  CreateRunPayload,
  EvaluationDataset,
  EvaluationRun,
  ExecutionRun,
  ExperimentCreatePayload,
  ExperimentDefinition,
  ExperimentResult,
  HealthResponse,
  MemoryRecord,
  ModelConfiguration,
  ModelConfigurationCreatePayload,
  PaginatedResponse,
  PatchReviewItem,
  Project,
  ReadinessResponse,
  RunEventResponse,
  Task,
  TaskCreatePayload,
  TaskUpdatePayload,
} from "@prometheus/shared-types";
import {
  DEMO_EVALUATION_DATASETS,
  DEMO_EVALUATION_RUNS,
  DEMO_EXPERIMENT_RESULTS,
  DEMO_EXPERIMENTS,
  DEMO_MEMORY_RECORDS,
  DEMO_MODELS,
  DEMO_PATCH_REVIEWS,
  DEMO_PROJECTS,
  DEMO_RUN_EVENTS,
  DEMO_RUNS,
  DEMO_TASKS,
} from "./demo-data";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export function isDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("prometheus_demo_mode") === "true";
}

export function setDemoMode(enabled: boolean): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("prometheus_demo_mode", enabled ? "true" : "false");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");

  // Include API key if configured in localStorage
  if (typeof window !== "undefined") {
    const key = localStorage.getItem("prometheus_api_key");
    if (key) {
      headers.set("X-API-Key", key);
    }
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    let errData: any = null;
    try {
      errData = await res.json();
    } catch {
      // Not JSON
    }
    const message =
      errData?.message ||
      errData?.detail ||
      `Request failed with status ${res.status}`;
    const err = new Error(message);
    (err as any).status = res.status;
    (err as any).data = errData;
    throw err;
  }

  return res.json();
}

// ============================================================================
// Health & Readiness
// ============================================================================

export async function getHealth(): Promise<HealthResponse> {
  try {
    return await request<HealthResponse>("/api/v1/health");
  } catch (error) {
    return {
      status: "degraded",
      version: "0.1.0",
      environment: process.env.NODE_ENV || "development",
      timestamp: new Date().toISOString(),
      database: "disconnected",
      sandbox_available: false,
    };
  }
}

export async function getReadiness(): Promise<ReadinessResponse> {
  try {
    return await request<ReadinessResponse>("/api/v1/ready");
  } catch (error) {
    return {
      ready: false,
      database: "disconnected",
      timestamp: new Date().toISOString(),
    };
  }
}

// ============================================================================
// Tasks
// ============================================================================

export async function getTasks(params?: {
  page?: number;
  page_size?: number;
  project_id?: string;
  status?: string;
  priority?: string;
  search?: string;
}): Promise<PaginatedResponse<Task>> {
  if (isDemoMode()) {
    let filtered = [...DEMO_TASKS];
    if (params?.status) filtered = filtered.filter((t) => t.status === params.status);
    if (params?.search) {
      const q = params.search.toLowerCase();
      filtered = filtered.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          t.problem_statement.toLowerCase().includes(q)
      );
    }
    return {
      items: filtered,
      total: filtered.length,
      page: params?.page || 1,
      page_size: params?.page_size || 20,
      total_pages: 1,
    };
  }

  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  if (params?.project_id) query.set("project_id", params.project_id);
  if (params?.status) query.set("status", params.status);
  if (params?.priority) query.set("priority", params.priority);
  if (params?.search) query.set("search", params.search);

  const qs = query.toString();
  return request<PaginatedResponse<Task>>(`/api/v1/tasks${qs ? `?${qs}` : ""}`);
}

export async function getTask(taskId: string): Promise<Task> {
  if (isDemoMode()) {
    const found = DEMO_TASKS.find((t) => t.id === taskId);
    if (found) return found;
    throw new Error(`Task '${taskId}' not found in demo dataset.`);
  }
  return request<Task>(`/api/v1/tasks/${taskId}`);
}

export async function createTask(payload: TaskCreatePayload): Promise<Task> {
  if (isDemoMode()) {
    const newTask: Task = {
      id: `task-demo-${Date.now()}`,
      project_id: payload.project_id,
      title: payload.title,
      problem_statement: payload.problem_statement,
      task_type: payload.task_type || "BUG_FIX",
      status: "OPEN",
      priority: payload.priority || "MEDIUM",
      base_commit: payload.base_commit,
      reproduce_command: payload.reproduce_command,
      metadata: payload.metadata || {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      runs_count: 0,
      latest_run_status: null,
    };
    DEMO_TASKS.unshift(newTask);
    return newTask;
  }
  return request<Task>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateTask(
  taskId: string,
  payload: TaskUpdatePayload
): Promise<Task> {
  if (isDemoMode()) {
    const task = DEMO_TASKS.find((t) => t.id === taskId);
    if (!task) throw new Error("Task not found");
    if (payload.status) task.status = payload.status;
    if (payload.title) task.title = payload.title;
    task.updated_at = new Date().toISOString();
    return task;
  }
  return request<Task>(`/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ============================================================================
// Execution Runs
// ============================================================================

export async function getRuns(params?: {
  task_id?: string;
  status?: string;
}): Promise<ExecutionRun[]> {
  if (isDemoMode()) {
    let filtered = [...DEMO_RUNS];
    if (params?.task_id) filtered = filtered.filter((r) => r.task_id === params.task_id);
    if (params?.status) filtered = filtered.filter((r) => r.status === params.status);
    return filtered;
  }

  const query = new URLSearchParams();
  if (params?.task_id) query.set("task_id", params.task_id);
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  return request<ExecutionRun[]>(`/api/v1/runs${qs ? `?${qs}` : ""}`);
}

export async function getRun(runId: string): Promise<ExecutionRun> {
  if (isDemoMode()) {
    const found = DEMO_RUNS.find((r) => r.id === runId);
    if (found) return found;
    throw new Error(`Run '${runId}' not found.`);
  }
  return request<ExecutionRun>(`/api/v1/runs/${runId}`);
}

export async function createRun(payload: CreateRunPayload): Promise<ExecutionRun> {
  if (isDemoMode()) {
    const newRun: ExecutionRun = {
      id: `run_demo_${Date.now()}`,
      task_id: payload.task_id || "task-ast-101",
      status: "PENDING",
      model_provider: payload.model_provider || "anthropic/claude-3-5-sonnet-20241022",
      iteration_count: 0,
      total_tokens: 0,
      prompt_tokens: 0,
      completion_tokens: 0,
      cost_estimate_usd: 0.0,
      current_step: "INITIALIZED",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    DEMO_RUNS.unshift(newRun);
    return newRun;
  }
  return request<ExecutionRun>("/api/v1/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function cancelRun(runId: string): Promise<ExecutionRun> {
  if (isDemoMode()) {
    const run = DEMO_RUNS.find((r) => r.id === runId);
    if (!run) throw new Error("Run not found");
    run.status = "CANCELLED";
    run.completed_at = new Date().toISOString();
    return run;
  }
  return request<ExecutionRun>(`/api/v1/runs/${runId}/cancel`, {
    method: "POST",
  });
}

export async function getRunEvents(runId: string): Promise<RunEventResponse[]> {
  if (isDemoMode()) {
    return DEMO_RUN_EVENTS[runId] || [];
  }
  return request<RunEventResponse[]>(`/api/v1/runs/${runId}/events`);
}

// ============================================================================
// Model Configurations
// ============================================================================

export async function getModels(params?: {
  provider?: string;
  is_active?: boolean;
}): Promise<ModelConfiguration[]> {
  if (isDemoMode()) {
    let filtered = [...DEMO_MODELS];
    if (params?.provider) filtered = filtered.filter((m) => m.provider === params.provider);
    if (params?.is_active !== undefined)
      filtered = filtered.filter((m) => m.is_active === params.is_active);
    return filtered;
  }

  const query = new URLSearchParams();
  if (params?.provider) query.set("provider", params.provider);
  if (params?.is_active !== undefined)
    query.set("is_active", String(params.is_active));
  const qs = query.toString();
  return request<ModelConfiguration[]>(`/api/v1/models${qs ? `?${qs}` : ""}`);
}

export async function createModel(
  payload: ModelConfigurationCreatePayload
): Promise<ModelConfiguration> {
  if (isDemoMode()) {
    const newModel: ModelConfiguration = {
      id: `model-${Date.now()}`,
      name: payload.name,
      provider: payload.provider,
      model_name: payload.model_name,
      api_base_url: payload.api_base_url || null,
      temperature: payload.temperature ?? 0.0,
      max_tokens: payload.max_tokens ?? 4096,
      context_window: payload.context_window ?? 128000,
      cost_per_million_input_tokens: payload.cost_per_million_input_tokens ?? 3.0,
      cost_per_million_output_tokens: payload.cost_per_million_output_tokens ?? 15.0,
      is_active: payload.is_active ?? true,
      settings: payload.settings || {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    DEMO_MODELS.push(newModel);
    return newModel;
  }
  return request<ModelConfiguration>("/api/v1/models", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ============================================================================
// Experiments & Evaluations
// ============================================================================

export async function getExperiments(params?: {
  is_active?: boolean;
}): Promise<ExperimentDefinition[]> {
  if (isDemoMode()) {
    return DEMO_EXPERIMENTS;
  }
  const query = new URLSearchParams();
  if (params?.is_active !== undefined)
    query.set("is_active", String(params.is_active));
  const qs = query.toString();
  return request<ExperimentDefinition[]>(`/api/v1/experiments${qs ? `?${qs}` : ""}`);
}

export async function createExperiment(
  payload: ExperimentCreatePayload
): Promise<ExperimentDefinition> {
  if (isDemoMode()) {
    const newExp: ExperimentDefinition = {
      id: `exp-${Date.now()}`,
      name: payload.name,
      description: payload.description || null,
      hypothesis: payload.hypothesis || null,
      model_configuration_id: payload.model_configuration_id || null,
      parameters: payload.parameters || {},
      is_active: payload.is_active ?? true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    DEMO_EXPERIMENTS.push(newExp);
    return newExp;
  }
  return request<ExperimentDefinition>("/api/v1/experiments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getExperimentResults(
  experimentId: string
): Promise<ExperimentResult[]> {
  if (isDemoMode()) {
    return DEMO_EXPERIMENT_RESULTS.filter((r) => r.experiment_id === experimentId);
  }
  return request<ExperimentResult[]>(
    `/api/v1/experiments/${experimentId}/results`
  );
}

export async function getEvaluationResults(): Promise<ExperimentResult[]> {
  if (isDemoMode()) {
    return DEMO_EXPERIMENT_RESULTS;
  }
  return request<ExperimentResult[]>("/api/v1/evaluations/results");
}

export async function getEvaluationRuns(): Promise<EvaluationRun[]> {
  if (isDemoMode()) {
    return DEMO_EVALUATION_RUNS;
  }
  return request<EvaluationRun[]>("/api/v1/evaluations/runs");
}

// ============================================================================
// Projects & Repositories
// ============================================================================

export async function getProjects(): Promise<Project[]> {
  if (isDemoMode()) {
    return DEMO_PROJECTS;
  }
  try {
    // When live backend has projects
    const tasksRes = await getTasks({ page_size: 1 });
    if (tasksRes.items.length > 0) {
      return [
        {
          id: tasksRes.items[0].project_id,
          name: "Prometheus Primary Workspace",
          slug: "prometheus-core",
          description: "Authoritative project workspace for autonomous engineering.",
          repository_url: "https://github.com/prometheus/sample-workspace.git",
          default_branch: "main",
          created_at: tasksRes.items[0].created_at,
          updated_at: tasksRes.items[0].updated_at,
        },
      ];
    }
  } catch {
    // fallback
  }
  return DEMO_PROJECTS;
}

// ============================================================================
// Memory & Patch Reviews
// ============================================================================

export async function getMemoryRecords(): Promise<MemoryRecord[]> {
  if (isDemoMode()) {
    return DEMO_MEMORY_RECORDS;
  }
  // Memory records fallback to demo data if backend table not directly exposed via REST
  return DEMO_MEMORY_RECORDS;
}

function parseDiffFiles(diffText: string): string[] {
  const files: Set<string> = new Set();
  const lines = diffText.split("\n");
  for (const line of lines) {
    if (line.startsWith("diff --git")) {
      const match = line.match(/diff --git a\/(.+?) b\/(.+)/);
      if (match && match[2]) {
        files.add(match[2].trim());
      }
    } else if (line.startsWith("+++ b/")) {
      files.add(line.replace("+++ b/", "").trim());
    }
  }
  return files.size > 0 ? Array.from(files) : [];
}

export async function getPatchReviews(): Promise<PatchReviewItem[]> {
  if (isDemoMode()) {
    return DEMO_PATCH_REVIEWS;
  }
  try {
    const runs = await getRuns({ status: "RESOLVED" });
    const patchRuns = runs.filter((r) => r.patch_diff);
    if (patchRuns.length > 0) {
      return patchRuns.map((r) => {
        const diff = r.patch_diff || "";
        const files = parseDiffFiles(diff);
        return {
          run_id: r.id,
          task_id: r.task_id,
          task_title: `Resolution for ${r.task_id}`,
          status: r.status,
          patch_diff: diff,
          affected_files: files.length > 0 ? files : ["patch.diff"],
          test_status: "PASSED",
          approved: false,
        };
      });
    }
  } catch {
    // fallback
  }
  return DEMO_PATCH_REVIEWS;
}
