"use client";

import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { cancelRun, getRuns } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import {
  IconArrowRight,
  IconCheck,
  IconCopy,
  IconRefresh,
  IconRuns,
  IconSearch,
  IconX,
  IconZap,
} from "../components/Icons";
import type { ExecutionRun, RunStatus } from "@prometheus/shared-types";

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

function RunsContent() {
  const searchParams = useSearchParams();
  const initialTaskId = searchParams.get("task_id") || "";

  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>(initialTaskId);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRuns();
      setRuns(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load execution runs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key.toLowerCase() === "r" &&
        !["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement)?.tagName)
      ) {
        loadRuns();
      }
      if (e.key === "Escape") {
        setSearchQuery("");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [loadRuns]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 1800);
  };

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

  const counts = useMemo(() => {
    return {
      all: runs.length,
      running: runs.filter((r) => r.status === "RUNNING" || r.status === "VERIFYING").length,
      resolved: runs.filter((r) => r.status === "RESOLVED").length,
      failed: runs.filter((r) => r.status === "FAILED").length,
      pending: runs.filter((r) => r.status === "PENDING").length,
    };
  }, [runs]);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const matchesStatus =
        statusFilter === "ALL"
          ? true
          : statusFilter === "RUNNING"
          ? run.status === "RUNNING" || run.status === "VERIFYING"
          : run.status === statusFilter;

      const q = searchQuery.toLowerCase().trim();
      const matchesQuery =
        !q ||
        run.id.toLowerCase().includes(q) ||
        run.task_id.toLowerCase().includes(q) ||
        (run.model_provider && run.model_provider.toLowerCase().includes(q));

      return matchesStatus && matchesQuery;
    });
  }, [runs, statusFilter, searchQuery]);

  const totalFilteredTokens = filteredRuns.reduce((acc, r) => acc + (r.total_tokens || 0), 0);
  const totalFilteredCost = filteredRuns.reduce((acc, r) => acc + (r.cost_estimate_usd || 0), 0);

  const getStatusBadge = (status: RunStatus) => {
    switch (status) {
      case "RUNNING":
      case "VERIFYING":
        return (
          <span className="badge badge-running">
            <span className="badge-dot" />
            {status}
          </span>
        );
      case "RESOLVED":
        return (
          <span className="badge badge-resolved">
            <IconCheck size={11} />
            RESOLVED
          </span>
        );
      case "FAILED":
        return (
          <span className="badge badge-failed">
            <IconX size={11} />
            FAILED
          </span>
        );
      case "CANCELLED":
        return <span className="badge badge-cancelled">CANCELLED</span>;
      case "PENDING":
      default:
        return <span className="badge badge-pending">PENDING</span>;
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Execution Runs</h1>
            <span className="badge badge-pending">
              AUDIT TRAIL
            </span>
          </div>
          <p className="page-description">
            Live telemetry, agent problem-solving state transitions, and hardened sandbox verification runs.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadRuns}
            title="Press 'R' to refresh instantly"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
          >
            <IconRefresh size={14} /> Refresh <span style={{ opacity: 0.6, fontSize: "0.7rem" }}>(R)</span>
          </button>
          <Link
            href="/tasks"
            className="btn btn-primary btn-sm"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
          >
            <IconZap size={14} color="#080C14" /> Launch New Run
          </Link>
        </div>
      </div>

      {actionMessage && (
        <div
          className="state-box"
          style={{ padding: "0.85rem 1.25rem", marginBottom: "1.5rem", borderColor: "var(--warning)" }}
          role="status"
        >
          <p style={{ color: "var(--warning)", fontWeight: 600 }}>{actionMessage}</p>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        {/* Status Filter Chips */}
        <div className="chip-group">
          <button
            type="button"
            className={`chip ${statusFilter === "ALL" ? "active" : ""}`}
            onClick={() => setStatusFilter("ALL")}
          >
            All <span className="chip-count">{counts.all}</span>
          </button>
          <button
            type="button"
            className={`chip ${statusFilter === "RESOLVED" ? "active" : ""}`}
            onClick={() => setStatusFilter("RESOLVED")}
          >
            Resolved <span className="chip-count">{counts.resolved}</span>
          </button>
          {counts.running > 0 && (
            <button
              type="button"
              className={`chip ${statusFilter === "RUNNING" ? "active" : ""}`}
              onClick={() => setStatusFilter("RUNNING")}
            >
              Running <span className="chip-count">{counts.running}</span>
            </button>
          )}
          {counts.failed > 0 && (
            <button
              type="button"
              className={`chip ${statusFilter === "FAILED" ? "active" : ""}`}
              onClick={() => setStatusFilter("FAILED")}
            >
              Failed <span className="chip-count">{counts.failed}</span>
            </button>
          )}
          {counts.pending > 0 && (
            <button
              type="button"
              className={`chip ${statusFilter === "PENDING" ? "active" : ""}`}
              onClick={() => setStatusFilter("PENDING")}
            >
              Pending <span className="chip-count">{counts.pending}</span>
            </button>
          )}
        </div>

        {/* Search Input */}
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <span
              style={{
                position: "absolute",
                left: "0.65rem",
                top: "50%",
                transform: "translateY(-50%)",
                opacity: 0.5,
                pointerEvents: "none",
                display: "flex",
                alignItems: "center",
              }}
            >
              <IconSearch size={14} />
            </span>
            <input
              type="text"
              className="form-input"
              style={{ width: "240px", paddingLeft: "2rem" }}
              placeholder="Filter by ID, task, model..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          {searchQuery && (
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setSearchQuery("")}
              title="Clear search (Esc)"
              style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
            >
              <IconX size={12} /> Clear
            </button>
          )}
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div
        style={{
          display: "flex",
          gap: "2rem",
          alignItems: "center",
          padding: "0.75rem 1.25rem",
          background: "var(--bg-surface-solid)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "8px",
          marginBottom: "1.5rem",
          fontSize: "0.825rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <span style={{ color: "var(--text-muted)" }}>Matching Runs: </span>
          <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{filteredRuns.length}</span>
        </div>
        <div>
          <span style={{ color: "var(--text-muted)" }}>Token Volume: </span>
          <span className="table-mono" style={{ fontWeight: 600, color: "var(--text-primary)" }}>
            {totalFilteredTokens.toLocaleString()} tok
          </span>
        </div>
        <div>
          <span style={{ color: "var(--text-muted)" }}>Estimated Cost: </span>
          <span className="table-mono" style={{ fontWeight: 600, color: "var(--success)" }}>
            ${totalFilteredCost.toFixed(4)} USD
          </span>
        </div>
        {runs.length > 0 && (
          <div style={{ marginLeft: "auto", color: "var(--text-muted)" }}>
            Success Rate:{" "}
            <span style={{ color: "var(--accent)", fontWeight: 700 }}>
              {Math.round((counts.resolved / runs.length) * 100)}%
            </span>
          </div>
        )}
      </div>

      {/* Table Content */}
      {loading ? (
        <LoadingState message="Fetching execution run logs..." />
      ) : error ? (
        <ErrorState title="Failed to load runs" message={error} onRetry={loadRuns} />
      ) : filteredRuns.length === 0 ? (
        <EmptyState
          title="No execution runs found"
          description={
            statusFilter !== "ALL" || searchQuery
              ? "No execution runs match your search query or filter criteria."
              : "No agent execution runs have been launched yet."
          }
          actionLabel={statusFilter !== "ALL" || searchQuery ? "Reset Filters" : "View Tasks"}
          onAction={() => {
            if (statusFilter !== "ALL" || searchQuery) {
              setStatusFilter("ALL");
              setSearchQuery("");
            } else {
              window.location.href = "/tasks";
            }
          }}
        />
      ) : (
        <div className="table-container">
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
                <th scope="col">Recorded</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <Link
                        href={`/runs/${run.id}`}
                        className="table-mono"
                        style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}
                      >
                        {run.id.slice(0, 16)}...
                      </Link>
                      <button
                        type="button"
                        className="copy-pill"
                        onClick={() => copyToClipboard(run.id)}
                        title="Copy full Run ID"
                      >
                        {copiedId === run.id ? <IconCheck size={11} color="var(--success)" /> : <IconCopy size={11} />}
                      </button>
                    </div>
                  </td>
                  <td>
                    <span className="table-mono" style={{ color: "var(--text-secondary)" }}>
                      {run.task_id}
                    </span>
                  </td>
                  <td>
                    <span className="table-mono" style={{ fontSize: "0.775rem" }}>
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
                  <td style={{ fontSize: "0.775rem", color: "var(--text-muted)" }} title={run.created_at}>
                    {formatRelativeTime(run.created_at)}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.4rem" }}>
                      <Link
                        href={`/runs/${run.id}`}
                        className="btn btn-sm btn-secondary"
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                        title="Inspect ordered actions, sandbox tests, and tool traces"
                      >
                        Inspect <IconArrowRight size={12} />
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
