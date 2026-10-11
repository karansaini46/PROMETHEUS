"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { cancelRun, getRuns } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { ExecutionRun, RunStatus } from "@prometheus/shared-types";

function RunsContent() {
  const searchParams = useSearchParams();
  const initialTaskId = searchParams.get("task_id") || "";

  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [taskIdFilter, setTaskIdFilter] = useState<string>(initialTaskId);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadRuns = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuns({
        task_id: taskIdFilter || undefined,
        status: statusFilter || undefined,
      });
      setRuns(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load execution runs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, [statusFilter, taskIdFilter]);

  const handleCancelRun = async (runId: string) => {
    if (!confirm(`Are you sure you want to cancel run ${runId}?`)) return;
    try {
      await cancelRun(runId);
      setActionMessage(`Run ${runId} cancelled.`);
      loadRuns();
    } catch (err: any) {
      alert(`Failed to cancel run: ${err?.message || err}`);
    }
  };

  const getStatusBadge = (status: RunStatus) => {
    switch (status) {
      case "RUNNING":
      case "VERIFYING":
        return <span className="badge badge-running"><span className="badge-dot" />{status}</span>;
      case "RESOLVED":
        return <span className="badge badge-resolved">✓ RESOLVED</span>;
      case "FAILED":
        return <span className="badge badge-failed">✕ FAILED</span>;
      case "CANCELLED":
        return <span className="badge badge-cancelled">CANCELLED</span>;
      case "PENDING":
      default:
        return <span className="badge badge-pending">PENDING</span>;
    }
  };

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Execution Runs</h1>
          <p className="page-description">
            Audit logs and telemetry for autonomous agent problem-solving sessions and verification runs.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadRuns}>
            ↻ Refresh Runs
          </button>
        </div>
      </div>

      {actionMessage && (
        <div
          className="state-box"
          style={{ padding: "0.75rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--warning)" }}
          role="status"
        >
          <p style={{ color: "var(--warning)", fontWeight: 600 }}>{actionMessage}</p>
        </div>
      )}

      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: "1rem",
          alignItems: "center",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="filter-status" className="form-label" style={{ margin: 0 }}>
            Status:
          </label>
          <select
            id="filter-status"
            className="form-select"
            style={{ width: "auto" }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="RUNNING">RUNNING</option>
            <option value="RESOLVED">RESOLVED</option>
            <option value="FAILED">FAILED</option>
            <option value="CANCELLED">CANCELLED</option>
            <option value="PENDING">PENDING</option>
          </select>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="filter-task" className="form-label" style={{ margin: 0 }}>
            Task ID:
          </label>
          <input
            id="filter-task"
            type="text"
            className="form-input"
            style={{ width: "180px" }}
            placeholder="e.g. task-ast-101"
            value={taskIdFilter}
            onChange={(e) => setTaskIdFilter(e.target.value)}
          />
          {taskIdFilter && (
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setTaskIdFilter("")}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <LoadingState message="Fetching execution run logs..." />
      ) : error ? (
        <ErrorState title="Failed to load runs" message={error} onRetry={loadRuns} />
      ) : runs.length === 0 ? (
        <EmptyState
          title="No execution runs found"
          description={
            statusFilter || taskIdFilter
              ? "No execution runs match the specified filter criteria."
              : "No agent execution runs have been launched yet."
          }
          actionLabel="View Tasks"
          onAction={() => (window.location.href = "/tasks")}
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Execution Runs ({runs.length})</h2>
          </div>

          <table className="eng-table" aria-label="Execution Runs Table">
            <thead>
              <tr>
                <th scope="col">Run ID</th>
                <th scope="col">Target Task</th>
                <th scope="col">Model Provider</th>
                <th scope="col">Status</th>
                <th scope="col">Iterations</th>
                <th scope="col">Tokens</th>
                <th scope="col">Cost (USD)</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link
                      href={`/runs/${run.id}`}
                      className="table-mono"
                      style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}
                    >
                      {run.id}
                    </Link>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-primary)" }}>
                      {run.task_id}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ fontSize: "0.75rem" }}>
                      {run.model_provider}
                    </span>
                  </td>
                  <td>{getStatusBadge(run.status)}</td>
                  <td>
                    <span className="table-mono">{run.iteration_count}</span>
                  </td>
                  <td>
                    <span className="table-mono">
                      {(run.total_tokens || 0).toLocaleString()}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--success)" }}>
                      ${(run.cost_estimate_usd || 0).toFixed(4)}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.775rem", color: "var(--text-muted)" }}>
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <Link
                        href={`/runs/${run.id}`}
                        className="btn btn-sm btn-primary"
                        title="Inspect ordered actions and tool calls"
                      >
                        Inspect
                      </Link>
                      {(run.status === "RUNNING" || run.status === "PENDING") && (
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => handleCancelRun(run.id)}
                          title="Cancel execution run"
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function RunsListPage() {
  return (
    <Suspense fallback={<LoadingState message="Loading execution runs..." />}>
      <RunsContent />
    </Suspense>
  );
}
