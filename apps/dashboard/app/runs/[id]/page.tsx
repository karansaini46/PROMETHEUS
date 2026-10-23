"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { cancelRun, getRun, getRunEvents } from "../../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../../components/UIStates";
import { DiffViewer } from "../../components/DiffViewer";
import {
  IconArrowRight,
  IconCheck,
  IconChevronDown,
  IconChevronUp,
  IconCopy,
  IconRefresh,
  IconTerminal,
  IconX,
  IconZap,
} from "../../components/Icons";
import type { ExecutionRun, RunEventResponse, RunStatus } from "@prometheus/shared-types";

export default function RunInspectorPage() {
  const params = useParams();
  const runId = params.id as string;

  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [events, setEvents] = useState<RunEventResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Navigation during long runs
  const [filterType, setFilterType] = useState<string>("ALL");
  const [searchEvent, setSearchEvent] = useState<string>("");
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});
  const [showPatchPreview, setShowPatchPreview] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [copiedId, setCopiedId] = useState(false);

  const loadRunData = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const [runData, eventsData] = await Promise.all([
        getRun(runId),
        getRunEvents(runId),
      ]);
      setRun(runData);
      setEvents(eventsData);

      // Default expand the last 3 events
      const initExpanded: Record<string, boolean> = {};
      eventsData.forEach((ev, idx) => {
        if (idx >= eventsData.length - 3 || ev.event_type === "TOOL_INVOCATION") {
          initExpanded[ev.event_id] = true;
        }
      });
      setExpandedEvents(initExpanded);
    } catch (err: any) {
      setError(err?.message || "Failed to load execution run details.");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (runId) {
      loadRunData();
    }
  }, [runId, loadRunData]);

  const handleCancel = async () => {
    if (!run || !confirm(`Cancel execution run ${run.id}?`)) return;
    setCancelling(true);
    try {
      const updated = await cancelRun(run.id);
      setRun(updated);
    } catch (err: any) {
      alert(`Failed to cancel run: ${err?.message || err}`);
    } finally {
      setCancelling(false);
    }
  };

  const copyRunId = () => {
    if (!run) return;
    navigator.clipboard.writeText(run.id);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1800);
  };

  const toggleEvent = (eventId: string) => {
    setExpandedEvents((prev) => ({
      ...prev,
      [eventId]: !prev[eventId],
    }));
  };

  const toggleAllEvents = (expand: boolean) => {
    const updated: Record<string, boolean> = {};
    events.forEach((e) => {
      updated[e.event_id] = expand;
    });
    setExpandedEvents(updated);
  };

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

  if (loading) return <LoadingState message={`Inspecting execution run ${runId}...`} />;
  if (error || !run) return <ErrorState title="Run Not Available" message={error || "Run not found."} onRetry={loadRunData} />;

  // Filter events
  const filteredEvents = events.filter((ev) => {
    if (filterType !== "ALL" && ev.event_type !== filterType) {
      return false;
    }
    if (searchEvent.trim()) {
      const q = searchEvent.toLowerCase();
      const str = JSON.stringify(ev.data).toLowerCase();
      if (!str.includes(q)) return false;
    }
    return true;
  });

  // Calculate elapsed time
  let elapsedTime = "N/A";
  if (run.created_at) {
    const start = new Date(run.started_at || run.created_at).getTime();
    const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
    const diffSec = Math.max(0, Math.floor((end - start) / 1000));
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    elapsedTime = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  }

  return (
    <div>
      {/* Top Header */}
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <Link href="/runs" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: "0.9rem" }}>
              ← Runs
            </Link>
            <span style={{ color: "var(--border-medium)" }}>/</span>
            <span className="table-mono" style={{ fontSize: "1.2rem", fontWeight: 700, color: "var(--text-primary)" }}>
              {run.id}
            </span>
            <button
              type="button"
              className="copy-pill"
              onClick={copyRunId}
              title="Copy Run ID"
              aria-label="Copy Run ID"
            >
              {copiedId ? <IconCheck size={11} color="var(--success)" /> : <IconCopy size={11} />}
            </button>
            {getStatusBadge(run.status)}
          </div>
          <p className="page-description">
            Target Task:{" "}
            <Link href={`/tasks`} className="table-mono" style={{ color: "var(--accent)", textDecoration: "none" }}>
              {run.task_id}
            </Link>{" "}
            | Model: <span className="table-mono">{run.model_provider}</span>
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadRunData}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
          >
            <IconRefresh size={13} /> Refresh Events
          </button>
          {(run.status === "RUNNING" || run.status === "PENDING") && (
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={handleCancel}
              disabled={cancelling}
            >
              {cancelling ? "Cancelling..." : "Cancel Run"}
            </button>
          )}
          {run.patch_diff && (
            <Link
              href={`/patch-review`}
              className="btn btn-primary btn-sm"
              style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
            >
              Review Generated Patch <IconArrowRight size={13} />
            </Link>
          )}
        </div>
      </div>

      {/* Metrics Row */}
      <section className="metrics-row" aria-label="Execution Telemetry">
        <div className="metric-card">
          <div className="metric-label">Iterations</div>
          <div className="metric-value">{run.iteration_count}</div>
          <div className="metric-subtext">Current step: {run.current_step || "IDLE"}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Token Footprint</div>
          <div className="metric-value">{(run.total_tokens || 0).toLocaleString()}</div>
          <div className="metric-subtext">
            Prompt: {(run.prompt_tokens || 0).toLocaleString()} | Comp: {(run.completion_tokens || 0).toLocaleString()}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Estimated Cost</div>
          <div className="metric-value" style={{ color: "var(--success)" }}>
            ${(run.cost_estimate_usd || 0).toFixed(4)}
          </div>
          <div className="metric-subtext">Authoritative token rating</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Duration</div>
          <div className="metric-value">{elapsedTime}</div>
          <div className="metric-subtext">
            {run.completed_at ? `Completed at ${new Date(run.completed_at).toLocaleTimeString()}` : "Active in sandbox"}
          </div>
        </div>
      </section>

      {/* Patch Preview Accordion (if present) */}
      {run.patch_diff && (
        <div style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <h2 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>
              Synthesized Patch Solution
            </h2>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => setShowPatchPreview(!showPatchPreview)}
            >
              {showPatchPreview ? "Hide Inline Diff" : "Preview Diff"}
            </button>
          </div>
          {showPatchPreview && (
            <DiffViewer
              diff={run.patch_diff}
              filename="solution_patch.diff"
            />
          )}
        </div>
      )}

      {/* Ordered Execution Events Inspector */}
      <div className="table-container">
        <div className="table-header-bar">
          <div>
            <h2 className="table-title">Ordered Execution Events ({filteredEvents.length} of {events.length})</h2>
            <span style={{ fontSize: "0.775rem", color: "var(--text-muted)" }}>
              Synchronized agent thoughts, sandbox tool invocations, observations, and telemetry
            </span>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
            {/* Type Filter */}
            <select
              className="form-select"
              style={{ width: "auto", fontSize: "0.8rem", padding: "0.3rem 0.6rem" }}
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              aria-label="Filter events by type"
            >
              <option value="ALL">All Event Types</option>
              <option value="AGENT_STEP">Agent Reasoning Steps</option>
              <option value="TOOL_INVOCATION">Tool Invocations</option>
              <option value="AUDIT_EVENT">Audit Events</option>
            </select>

            {/* Jump to Step selector */}
            <select
              className="form-select"
              style={{ width: "auto", fontSize: "0.8rem", padding: "0.3rem 0.6rem" }}
              onChange={(e) => {
                const targetId = e.target.value;
                if (targetId) {
                  document.getElementById(`event-${targetId}`)?.scrollIntoView({ behavior: "smooth" });
                }
              }}
              aria-label="Jump to event step"
            >
              <option value="">Jump to Step...</option>
              {events.map((ev) => (
                <option key={ev.event_id} value={ev.event_id}>
                  #{ev.sequence} - {ev.event_type} {((ev.data as any).step_name || (ev.data as any).tool_name || "")}
                </option>
              ))}
            </select>

            {/* Search filter in event logs */}
            <input
              type="search"
              className="form-input"
              style={{ width: "160px", fontSize: "0.8rem", padding: "0.3rem 0.6rem" }}
              placeholder="Filter text..."
              value={searchEvent}
              onChange={(e) => setSearchEvent(e.target.value)}
              aria-label="Search within events"
            />

            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => toggleAllEvents(true)}
            >
              Expand All
            </button>
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => toggleAllEvents(false)}
            >
              Collapse All
            </button>
          </div>
        </div>

        {filteredEvents.length === 0 ? (
          <div style={{ padding: "3rem 1rem" }}>
            <EmptyState
              title="No events matching criteria"
              description="Adjust the event type filter or search keyword to view records."
            />
          </div>
        ) : (
          <div style={{ padding: "1.5rem" }}>
            <div className="timeline">
              {filteredEvents.map((ev) => {
                const isExpanded = !!expandedEvents[ev.event_id];
                const data = (ev.data || {}) as Record<string, any>;
                const isError =
                  data.status === "FAILURE" ||
                  data.status === "ERROR" ||
                  data.exit_code !== undefined && data.exit_code !== 0;

                return (
                  <div
                    key={ev.event_id}
                    id={`event-${ev.event_id}`}
                    className={`timeline-item ${isError ? "error" : "success"}`}
                  >
                    <div className="timeline-dot" aria-hidden="true" />
                    <div className="timeline-card">
                      <div className="timeline-header">
                        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                          <span
                            className="table-mono"
                            style={{ fontWeight: 700, color: "var(--accent)" }}
                          >
                            #{ev.sequence}
                          </span>

                          <span
                            className={`badge ${
                              ev.event_type === "AGENT_STEP"
                                ? "badge-pending"
                                : ev.event_type === "TOOL_INVOCATION"
                                ? "badge-open"
                                : "badge-resolved"
                            }`}
                          >
                            {ev.event_type}
                          </span>

                          {data.step_name && (
                            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                              {data.step_name}
                            </span>
                          )}

                          {data.tool_name && (
                            <span
                              className="table-mono"
                              style={{
                                color: "#38bdf8",
                                backgroundColor: "rgba(56, 189, 248, 0.1)",
                                padding: "0.15rem 0.45rem",
                                borderRadius: "4px",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.3rem",
                              }}
                            >
                              <IconTerminal size={12} /> {data.tool_name}
                            </span>
                          )}
                        </div>

                        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                          {data.tokens_used !== undefined && (
                            <span className="table-mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {data.tokens_used} tokens
                            </span>
                          )}
                          {data.duration_ms !== undefined && (
                            <span className="table-mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {data.duration_ms}ms
                            </span>
                          )}
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {new Date(ev.timestamp).toLocaleTimeString()}
                          </span>
                          <button
                            type="button"
                            className="btn btn-sm btn-secondary"
                            style={{ padding: "0.2rem 0.45rem", fontSize: "0.7rem", display: "inline-flex", alignItems: "center" }}
                            onClick={() => toggleEvent(ev.event_id)}
                            aria-expanded={isExpanded}
                            title={isExpanded ? "Collapse item" : "Expand item"}
                          >
                            {isExpanded ? <IconChevronUp size={12} /> : <IconChevronDown size={12} />}
                          </button>
                        </div>
                      </div>

                      {/* Summary line */}
                      {data.thought && (
                        <div
                          style={{
                            fontSize: "0.85rem",
                            color: "var(--text-primary)",
                            marginBottom: isExpanded ? "0.5rem" : 0,
                          }}
                        >
                          {data.thought}
                        </div>
                      )}

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div style={{ marginTop: "0.75rem" }}>
                          {/* Tool Parameters */}
                          {data.parameters && (
                            <div style={{ marginBottom: "0.5rem" }}>
                              <div style={{ fontSize: "0.725rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                                Tool Parameters
                              </div>
                              <pre className="timeline-code">
                                {JSON.stringify(data.parameters, null, 2)}
                              </pre>
                            </div>
                          )}

                          {/* Tool Result / Observation */}
                          {data.result && (
                            <div style={{ marginBottom: "0.5rem" }}>
                              <div style={{ fontSize: "0.725rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>
                                Sandbox Observation
                              </div>
                              <pre
                                className="timeline-code"
                                style={{
                                  borderColor: isError ? "var(--danger)" : "var(--border-subtle)",
                                  backgroundColor: isError ? "rgba(239, 68, 68, 0.05)" : "#0b0e14",
                                }}
                              >
                                {typeof data.result === "string"
                                  ? data.result
                                  : JSON.stringify(data.result, null, 2)}
                              </pre>
                            </div>
                          )}

                          {/* Raw Event Data for Audit */}
                          {!data.parameters && !data.result && (
                            <pre className="timeline-code">
                              {JSON.stringify(data, null, 2)}
                            </pre>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
