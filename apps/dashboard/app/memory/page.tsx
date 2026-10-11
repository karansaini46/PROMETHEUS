"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getMemoryRecords } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { MemoryRecord } from "@prometheus/shared-types";

export default function MemoryExplorerPage() {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter & Search
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecord | null>(null);

  const loadMemory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryRecords();
      setRecords(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load memory records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemory();
  }, []);

  if (loading) return <LoadingState message="Querying agent episodic and semantic memory..." />;
  if (error) return <ErrorState title="Memory Subsystem Offline" message={error} onRetry={loadMemory} />;

  // Filtered records
  const filtered = records.filter((rec) => {
    if (typeFilter && rec.memory_type !== typeFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const inKey = rec.key.toLowerCase().includes(q);
      const inContent = rec.content.toLowerCase().includes(q);
      if (!inKey && !inContent) return false;
    }
    return true;
  });

  // Unique memory types
  const memoryTypes = Array.from(new Set(records.map((r) => r.memory_type)));

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Memory Explorer</h1>
          <p className="page-description">
            Inspect long-term episodic lessons, failure patterns, and architectural heuristics learned from solved tasks.
          </p>
        </div>
        <div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadMemory}>
            ↻ Refresh Memory
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
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
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <label htmlFor="filter-mem-type" className="form-label" style={{ margin: 0 }}>
            Memory Type:
          </label>
          <select
            id="filter-mem-type"
            className="form-select"
            style={{ width: "auto" }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All Memory Types</option>
            {memoryTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>

        <input
          type="search"
          className="form-input"
          style={{ width: "260px" }}
          placeholder="Search patterns, keys, text..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          aria-label="Search memory experiences"
        />
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No memory experiences found"
          description={
            typeFilter || searchQuery
              ? "No stored memory records match your filter criteria."
              : "No experiences recorded yet. Memories are indexed after successful task resolutions."
          }
        />
      ) : (
        <div className="table-container">
          <div className="table-header-bar">
            <h2 className="table-title">Stored Experiences ({filtered.length})</h2>
          </div>

          <table className="eng-table" aria-label="Memory Records Table">
            <thead>
              <tr>
                <th scope="col">Pattern Key</th>
                <th scope="col">Memory Type</th>
                <th scope="col">Experience / Lesson Learned</th>
                <th scope="col">Source Task / Run</th>
                <th scope="col">Indexed</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rec) => {
                const meta = (rec.metadata_json || {}) as Record<string, any>;
                const taskId = meta.task_id || rec.key.split(":")[0];
                const runId = rec.run_id || meta.run_id;

                return (
                  <tr key={rec.id}>
                    <td>
                      <span className="table-mono" style={{ fontWeight: 600, color: "var(--accent)" }}>
                        {rec.key}
                      </span>
                      <div className="table-mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                        {rec.id}
                      </div>
                    </td>
                    <td>
                      <span
                        className="badge badge-open"
                        style={{ fontSize: "0.7rem" }}
                      >
                        {rec.memory_type}
                      </span>
                    </td>
                    <td style={{ maxWidth: "440px" }}>
                      <div
                        style={{
                          fontSize: "0.825rem",
                          color: "var(--text-primary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                        }}
                      >
                        {rec.content}
                      </div>
                    </td>
                    <td>
                      {taskId && (
                        <div>
                          <Link
                            href="/tasks"
                            className="table-mono"
                            style={{ fontSize: "0.75rem", color: "var(--accent)", textDecoration: "none" }}
                          >
                            Task: {taskId}
                          </Link>
                        </div>
                      )}
                      {runId && (
                        <div>
                          <Link
                            href={`/runs/${runId}`}
                            className="table-mono"
                            style={{ fontSize: "0.75rem", color: "var(--text-secondary)", textDecoration: "none" }}
                          >
                            Run: {runId}
                          </Link>
                        </div>
                      )}
                    </td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {new Date(rec.created_at).toLocaleDateString()}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => setSelectedRecord(rec)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Memory Record Detail Modal */}
      {selectedRecord && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="mem-dialog-title"
        >
          <div className="form-card" style={{ width: "100%", maxWidth: "600px", margin: "1rem" }}>
            <h2 id="mem-dialog-title" style={{ fontSize: "1.1rem", marginBottom: "0.25rem" }}>
              Memory Experience Detail
            </h2>
            <div className="table-mono" style={{ fontSize: "0.8rem", color: "var(--accent)", marginBottom: "1rem" }}>
              Key: {selectedRecord.key}
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Extracted Lesson & Reasoning
              </div>
              <div
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  padding: "0.85rem",
                  borderRadius: "6px",
                  fontSize: "0.85rem",
                  color: "var(--text-primary)",
                  marginTop: "0.4rem",
                  whiteSpace: "pre-wrap",
                }}
              >
                {selectedRecord.content}
              </div>
            </div>

            {selectedRecord.metadata_json && Object.keys(selectedRecord.metadata_json).length > 0 && (
              <div style={{ marginBottom: "1.25rem" }}>
                <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                  Metadata JSON
                </div>
                <pre className="timeline-code" style={{ marginTop: "0.4rem" }}>
                  {JSON.stringify(selectedRecord.metadata_json, null, 2)}
                </pre>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setSelectedRecord(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
