"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  getEvaluationResults,
  getHealth,
  getModels,
  getRuns,
  getTasks,
} from "../lib/api";
import { EmptyState, ErrorState, LoadingState } from "./components/UIStates";
import type {
  ExecutionRun,
  ExperimentResult,
  HealthResponse,
  ModelConfiguration,
  Task,
} from "@prometheus/shared-types";

export default function OverviewPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [evalResults, setEvalResults] = useState<ExperimentResult[]>([]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, t, r, m, e] = await Promise.all([
        getHealth(),
        getTasks({ page_size: 10 }),
        getRuns(),
        getModels(),
        getEvaluationResults(),
      ]);
      setHealth(h);
      setTasks(t.items);
      setRuns(r);
      setModels(m);
      setEvalResults(e);
    } catch (err: any) {
      setError(err?.message || "Failed to load engineering overview data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) return <LoadingState message="Connecting to PROMETHEUS control plane..." />;
  if (error) return <ErrorState title="System Overview Offline" message={error} onRetry={loadData} />;

  const totalTokens = runs.reduce((acc, r) => acc + (r.total_tokens || 0), 0);
  const totalCost = runs.reduce((acc, r) => acc + (r.cost_estimate_usd || 0), 0);
  const resolvedCount = runs.filter((r) => r.status === "RESOLVED").length;
  const runningCount = runs.filter((r) => r.status === "RUNNING").length;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Engineering Overview</h1>
          <p className="page-description">
            Telemetry, task lifecycles, and evaluation metrics from the authoritative backend.
          </p>
        </div>
        <div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadData}>
            ↻ Refresh Metrics
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <section className="metrics-row" aria-label="System Metrics">
        <div className="metric-card">
          <div className="metric-label">Registered Tasks</div>
          <div className="metric-value">{tasks.length}</div>
          <div className="metric-subtext">Active engineering targets</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Execution Runs</div>
          <div className="metric-value">
            {runs.length}
            {runningCount > 0 && (
              <span className="metric-unit" style={{ color: "var(--warning)" }}>
                ({runningCount} running)
              </span>
            )}
          </div>
          <div className="metric-subtext">{resolvedCount} resolved patches verified</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Cumulative Tokens</div>
          <div className="metric-value">
            {totalTokens.toLocaleString()}
            <span className="metric-unit">tok</span>
          </div>
          <div className="metric-subtext">Est. Cost: ${totalCost.toFixed(4)} USD</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Model Configurations</div>
          <div className="metric-value">{models.length}</div>
          <div className="metric-subtext">Active routing providers</div>
        </div>
      </section>

      {/* Recent Executions Table */}
      <section className="table-container" aria-label="Recent Execution Runs">
        <div className="table-header-bar">
          <h2 className="table-title">Recent Execution Runs</h2>
          <Link href="/runs" className="btn btn-sm btn-secondary">
            View All Runs →
          </Link>
        </div>

        {runs.length === 0 ? (
          <EmptyState
            title="No execution runs recorded"
            description="Start a debugging execution from the Task Workspace to see live traces."
          />
        ) : (
          <table className="eng-table">
            <thead>
              <tr>
                <th>Run Identifier</th>
                <th>Target Task</th>
                <th>Status</th>
                <th>Model Provider</th>
                <th>Tokens</th>
                <th>Cost</th>
                <th>Last Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 5).map((run) => (
                <tr key={run.id}>
                  <td className="table-mono">
                    <Link
                      href={`/runs/${run.id}`}
                      style={{ color: "var(--accent)", textDecoration: "none" }}
                    >
                      {run.id.slice(0, 16)}...
                    </Link>
                  </td>
                  <td className="table-mono">{run.task_id}</td>
                  <td>
                    <span
                      className={`badge badge-${run.status.toLowerCase()}`}
                    >
                      <span className="badge-dot" aria-hidden="true" />
                      {run.status}
                    </span>
                  </td>
                  <td>{run.model_provider}</td>
                  <td className="table-mono">
                    {(run.total_tokens || 0).toLocaleString()}
                  </td>
                  <td className="table-mono">
                    ${(run.cost_estimate_usd || 0).toFixed(4)}
                  </td>
                  <td className="table-mono" style={{ color: "var(--text-muted)" }}>
                    {new Date(run.updated_at).toLocaleTimeString()}
                  </td>
                  <td>
                    <Link
                      href={`/runs/${run.id}`}
                      className="btn btn-sm btn-secondary"
                    >
                      Inspect
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Two Column Section: Models & Evaluation Results */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1.5rem" }}>
        {/* Model Configurations */}
        <section className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Registered Model Providers</h2>
            <Link href="/models" className="btn btn-sm btn-secondary">
              Configure →
            </Link>
          </div>
          <table className="eng-table">
            <thead>
              <tr>
                <th>Identifier</th>
                <th>Provider</th>
                <th>Context Window</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.id}>
                  <td className="table-mono" style={{ fontWeight: 600 }}>{m.name}</td>
                  <td>{m.provider}</td>
                  <td className="table-mono">{m.context_window.toLocaleString()} tok</td>
                  <td>
                    <span className="badge badge-resolved">
                      <span className="badge-dot" aria-hidden="true" />
                      ACTIVE
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* Evaluation Results */}
        <section className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Recent Evaluation Results</h2>
            <Link href="/evaluations" className="btn btn-sm btn-secondary">
              Laboratory →
            </Link>
          </div>
          {evalResults.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
              No evaluation results recorded yet. Launch benchmark evaluations in the Evaluation Lab.
            </div>
          ) : (
            <table className="eng-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Value</th>
                  <th>Recorded At</th>
                </tr>
              </thead>
              <tbody>
                {evalResults.slice(0, 5).map((e) => (
                  <tr key={e.id}>
                    <td className="table-mono">{e.metric_name}</td>
                    <td className="table-mono" style={{ color: "var(--accent)", fontWeight: 700 }}>
                      {e.metric_value}
                    </td>
                    <td className="table-mono" style={{ color: "var(--text-muted)" }}>
                      {new Date(e.created_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
