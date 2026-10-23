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
import {
  IconArrowRight,
  IconCheck,
  IconCopy,
  IconRefresh,
} from "./components/Icons";
import type {
  ExecutionRun,
  ExperimentResult,
  HealthResponse,
  ModelConfiguration,
  Task,
} from "@prometheus/shared-types";

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (diffSec < 60) return "Just now";
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch {
    return dateString;
  }
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [models, setModels] = useState<ModelConfiguration[]>([]);
  const [evalResults, setEvalResults] = useState<ExperimentResult[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [runFilter, setRunFilter] = useState<string>("ALL");

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
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key.toLowerCase() === "r" &&
        !["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement)?.tagName)
      ) {
        loadData();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 1800);
  };

  if (loading) return <LoadingState message="Connecting to PROMETHEUS control plane..." />;
  if (error) return <ErrorState title="System Overview Offline" message={error} onRetry={loadData} />;

  const totalTokens = runs.reduce((acc, r) => acc + (r.total_tokens || 0), 0);
  const totalCost = runs.reduce((acc, r) => acc + (r.cost_estimate_usd || 0), 0);
  const resolvedCount = runs.filter((r) => r.status === "RESOLVED").length;
  const runningCount = runs.filter((r) => r.status === "RUNNING").length;
  const failedCount = runs.filter((r) => r.status === "FAILED").length;

  const filteredRuns = runs.filter((r) => {
    if (runFilter === "ALL") return true;
    return r.status === runFilter;
  });

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Engineering Overview</h1>
            <span className="badge badge-pending">
              control plane
            </span>
          </div>
          <p className="page-description">
            Autonomous software engineering agent control plane, sandbox execution traces, and verified patch benchmarks.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadData}
            title="Press 'R' to refresh instantly"
          >
            <IconRefresh size={13} />
            <span>Refresh</span>
            <span style={{ opacity: 0.6, fontSize: "0.75rem", fontFamily: "var(--font-mono)" }}>R</span>
          </button>
          <Link href="/tasks" className="btn btn-primary btn-sm">
            + New Task
          </Link>
        </div>
      </div>

      {/* Clean Service Strip */}
      <div className="service-bar">
        <div className="service-item">
          <span>PostgreSQL:</span>
          <span
            className="status-val"
            style={{ color: health?.database === "connected" ? "var(--success-text)" : "var(--danger-text)" }}
          >
            ● {health?.database || "disconnected"}
          </span>
        </div>
        <span style={{ color: "var(--border-strong)" }}>·</span>
        <div className="service-item">
          <span>Docker Sandbox:</span>
          <span
            className="status-val"
            style={{ color: health?.sandbox_available ? "var(--success-text)" : "var(--warning-text)" }}
          >
            ● {health?.sandbox_available ? "ready" : "standby"}
          </span>
        </div>
        <span style={{ color: "var(--border-strong)" }}>·</span>
        <div className="service-item">
          <span>Supervisor Worker:</span>
          <span
            className="status-val"
            style={{ color: health?.worker?.healthy ? "var(--success-text)" : "var(--warning-text)" }}
          >
            ● {health?.worker?.status?.toLowerCase() || "active"}
          </span>
        </div>
        <div style={{ marginLeft: "auto", fontSize: "0.75rem", fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
          env: <span style={{ color: "var(--text-secondary)" }}>{health?.environment || "development"}</span>
        </div>
      </div>

      {/* Metrics Row */}
      <section className="metrics-row" aria-label="System Metrics">
        <div className="metric-card">
          <div className="metric-label">Tracked Issues</div>
          <div className="metric-value">{tasks.length}</div>
          <div className="metric-subtext">{tasks.filter((t) => t.status === "RESOLVED").length} resolved · {tasks.filter((t) => t.status !== "RESOLVED").length} open</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Execution Runs</div>
          <div className="metric-value">{runs.length}</div>
          <div className="metric-subtext">
            {runs.length > 0 ? `${Math.round((resolvedCount / runs.length) * 100)}% pass rate (${resolvedCount} resolved)` : "No runs logged"}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Token Footprint</div>
          <div className="metric-value">
            {totalTokens.toLocaleString()}
            <span className="metric-unit">tok</span>
          </div>
          <div className="metric-subtext">${totalCost.toFixed(4)} estimated spend</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Configured Engines</div>
          <div className="metric-value">{models.length}</div>
          <div className="metric-subtext">Multi-provider router active</div>
        </div>
      </section>

      {/* Recent Execution Runs Table */}
      <div className="table-container">
        <div className="table-header-bar">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <h2 className="table-title">Recent Execution Runs</h2>
            <div className="chip-group">
              <button
                type="button"
                className={`chip ${runFilter === "ALL" ? "active" : ""}`}
                onClick={() => setRunFilter("ALL")}
              >
                All <span className="chip-count">{runs.length}</span>
              </button>
              <button
                type="button"
                className={`chip ${runFilter === "RESOLVED" ? "active" : ""}`}
                onClick={() => setRunFilter("RESOLVED")}
              >
                Resolved <span className="chip-count">{resolvedCount}</span>
              </button>
              {runningCount > 0 && (
                <button
                  type="button"
                  className={`chip ${runFilter === "RUNNING" ? "active" : ""}`}
                  onClick={() => setRunFilter("RUNNING")}
                >
                  Running <span className="chip-count">{runningCount}</span>
                </button>
              )}
              {failedCount > 0 && (
                <button
                  type="button"
                  className={`chip ${runFilter === "FAILED" ? "active" : ""}`}
                  onClick={() => setRunFilter("FAILED")}
                >
                  Failed <span className="chip-count">{failedCount}</span>
                </button>
              )}
            </div>
          </div>

          <Link
            href="/runs"
            style={{
              fontSize: "0.75rem",
              color: "var(--text-secondary)",
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              gap: "0.3rem",
            }}
          >
            <span>View All Runs</span>
            <IconArrowRight size={11} />
          </Link>
        </div>

        {filteredRuns.length === 0 ? (
          <div style={{ padding: "2.5rem 1rem" }}>
            <EmptyState
              title="No execution runs logged"
              description="Dispatch an autonomous agent from the Task Workspace to view telemetry."
              actionLabel="Go to Tasks"
              onAction={() => {
                window.location.href = "/tasks";
              }}
            />
          </div>
        ) : (
          <table className="eng-table" aria-label="Recent Runs Table">
            <thead>
              <tr>
                <th scope="col">Run ID</th>
                <th scope="col">Target Task</th>
                <th scope="col">Status</th>
                <th scope="col">Model Provider</th>
                <th scope="col">Tokens</th>
                <th scope="col">Cost</th>
                <th scope="col">Recorded</th>
                <th scope="col" style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.slice(0, 6).map((run) => (
                <tr key={run.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                      <Link
                        href={`/runs/${run.id}`}
                        className="table-mono"
                        style={{
                          color: "var(--text-primary)",
                          textDecoration: "none",
                          fontWeight: 500,
                        }}
                      >
                        {run.id.slice(0, 16)}...
                      </Link>
                      <button
                        type="button"
                        className="copy-pill"
                        onClick={() => copyToClipboard(run.id)}
                        title="Copy Run ID"
                      >
                        {copiedId === run.id ? (
                          <IconCheck size={11} color="var(--success-text)" />
                        ) : (
                          <IconCopy size={11} />
                        )}
                      </button>
                    </div>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-muted)" }}>
                      {run.task_id}
                    </span>
                  </td>
                  <td>
                    {run.status === "RESOLVED" ? (
                      <span className="badge badge-resolved">
                        <span className="badge-dot" /> RESOLVED
                      </span>
                    ) : run.status === "RUNNING" || run.status === "VERIFYING" ? (
                      <span className="badge badge-running">
                        <span className="badge-dot" /> {run.status}
                      </span>
                    ) : run.status === "FAILED" ? (
                      <span className="badge badge-failed">
                        <span className="badge-dot" /> FAILED
                      </span>
                    ) : run.status === "CANCELLED" ? (
                      <span className="badge badge-cancelled">CANCELLED</span>
                    ) : (
                      <span className="badge badge-pending">PENDING</span>
                    )}
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-secondary)" }}>
                      {run.model_provider}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-secondary)" }}>
                      {(run.total_tokens || 0).toLocaleString()}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-muted)" }}>
                      ${(run.cost_estimate_usd || 0).toFixed(4)}
                    </span>
                  </td>
                  <td style={{ color: "var(--text-muted)", fontSize: "0.75rem" }} title={run.created_at}>
                    {formatRelativeTime(run.created_at)}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <Link
                      href={`/runs/${run.id}`}
                      className="btn btn-sm btn-secondary"
                      style={{ padding: "0.2rem 0.5rem", fontSize: "0.71875rem" }}
                    >
                      Inspect →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Two Column Bento: Configured Models & Evaluation Highlights */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "1rem" }}>
        {/* Models Summary */}
        <div className="table-container" style={{ margin: 0 }}>
          <div className="table-header-bar">
            <h3 className="table-title">Registered Model Providers</h3>
            <Link
              href="/models"
              style={{ fontSize: "0.75rem", color: "var(--text-muted)", textDecoration: "none" }}
            >
              Configure →
            </Link>
          </div>
          <table className="eng-table">
            <thead>
              <tr>
                <th scope="col">Identifier</th>
                <th scope="col">Provider</th>
                <th scope="col">Context</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {models.slice(0, 4).map((m) => (
                <tr key={m.id}>
                  <td>
                    <span className="table-mono" style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                      {m.id}
                    </span>
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>{m.provider}</td>
                  <td>
                    <span className="table-mono" style={{ fontSize: "0.71875rem", color: "var(--text-secondary)" }}>
                      {m.context_window?.toLocaleString()} tok
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-resolved">active</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Evaluation Benchmark Summary */}
        <div className="table-container" style={{ margin: 0 }}>
          <div className="table-header-bar">
            <h3 className="table-title">Recent Evaluation Results</h3>
            <Link
              href="/evaluations"
              style={{ fontSize: "0.75rem", color: "var(--text-muted)", textDecoration: "none" }}
            >
              Laboratory →
            </Link>
          </div>
          {evalResults.length === 0 ? (
            <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78125rem" }}>
              No evaluation results recorded yet. Launch benchmark evaluations in the Evaluation Lab.
            </div>
          ) : (
            <table className="eng-table">
              <thead>
                <tr>
                  <th scope="col">Experiment ID</th>
                  <th scope="col">Metric</th>
                  <th scope="col">Score</th>
                </tr>
              </thead>
              <tbody>
                {evalResults.slice(0, 4).map((ev) => (
                  <tr key={ev.id}>
                    <td>
                      <span className="table-mono" style={{ color: "var(--text-primary)" }}>
                        {ev.id.slice(0, 16)}...
                      </span>
                    </td>
                    <td style={{ color: "var(--text-muted)" }}>{ev.metric_name}</td>
                    <td>
                      <span className="table-mono" style={{ color: "var(--success-text)", fontWeight: 600 }}>
                        {typeof ev.metric_value === "number" ? ev.metric_value.toFixed(2) : String(ev.metric_value)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>

            </table>
          )}
        </div>
      </div>
    </div>
  );
}
