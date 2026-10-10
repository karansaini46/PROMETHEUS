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

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  version: string;
  environment: string;
  timestamp: string;
  database: "connected" | "disconnected" | "disabled";
  sandbox_available: boolean;
}

export interface Issue {
  id: string;
  repository_url: string;
  base_commit: string;
  problem_statement: string;
  reproduce_hints?: string;
  created_at: string;
}

export interface DebuggingRun {
  id: string;
  issue_id: string;
  status: RunStatus;
  model_provider: string;
  iteration_count: number;
  total_tokens: number;
  cost_estimate_usd: number;
  current_step?: string;
  created_at: string;
  updated_at: string;
}

export interface PatchCandidate {
  id: string;
  run_id: string;
  iteration: number;
  unified_diff: string;
  modified_files: string[];
  test_command?: string;
  test_exit_code?: number;
  test_stdout?: string;
  test_stderr?: string;
  verified: boolean;
  created_at: string;
}

export interface AgentStreamEvent {
  event_id: string;
  run_id: string;
  timestamp: string;
  step_type: "PLAN" | "TOOL_CALL" | "TOOL_RESULT" | "TEST_RUN" | "DIFF" | "ERROR";
  content: string;
  metadata?: Record<string, unknown>;
}
