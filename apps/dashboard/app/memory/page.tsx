"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getMemoryRecords } from "../../lib/api";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { MemoryRecord } from "@prometheus/shared-types";
import { IconCopy, IconMemory, IconSearch } from "../components/Icons";

export default function MemoryExplorerPage() {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter & Search
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedRecord, setSelectedRecord] = useState<MemoryRecord | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const loadMemory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemoryRecords();
      setRecords(data);
      if (data.length > 0 && !selectedRecord) {
        setSelectedRecord(data[0]);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load memory records.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMemory();
  }, []);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(text);
    setTimeout(() => setCopiedKey(null), 1800);
  };

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

  const memoryTypes = Array.from(new Set(records.map((r) => r.memory_type)));

  return (
    <div>
      <div className="page-header">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
            <h1 className="page-title">Memory Explorer</h1>
            <span className="badge badge-resolved">
              PGVECTOR MEMORY
            </span>
          </div>
          <p className="page-description">
            Inspect long-term episodic lessons, failure patterns, and architectural heuristics learned from solved tasks.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadMemory}>
            Refresh Memory
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
        <div className="chip-group">
          <button
            type="button"
            className={`chip ${typeFilter === "" ? "active" : ""}`}
            onClick={() => setTypeFilter("")}
          >
            All Types <span className="chip-count">{records.length}</span>
          </button>
          {memoryTypes.map((type) => {
            const count = records.filter((r) => r.memory_type === type).length;
            return (
              <button
                key={type}
                type="button"
                className={`chip ${typeFilter === type ? "active" : ""}`}
                onClick={() => setTypeFilter(typeFilter === type ? "" : type)}
              >
                {type} <span className="chip-count">{count}</span>
              </button>
            );
          })}
        </div>

        <div style={{ position: "relative" }}>
          <input
            type="search"
            className="form-input"
            style={{ width: "260px", paddingLeft: "2rem" }}
            placeholder="Search patterns, keys, text..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search memory experiences"
          />
          <span
            style={{
              position: "absolute",
              left: "0.65rem",
              top: "50%",
              transform: "translateY(-50%)",
              opacity: 0.5,
              display: "flex",
              alignItems: "center",
            }}
          >
            <IconSearch size={14} />
          </span>
        </div>
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
        <div style={{ display: "grid", gridTemplateColumns: selectedRecord ? "1fr 380px" : "1fr", gap: "1.5rem" }}>
          {/* Main Records Table */}
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
                  <th scope="col">Source Task</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((rec) => {
                  const meta = (rec.metadata_json || {}) as Record<string, any>;
                  const taskId = meta.task_id || rec.key.split(":")[0];
                  const isSelected = selectedRecord?.id === rec.id;

                  return (
                    <tr
                      key={rec.id}
                      style={{
                        backgroundColor: isSelected ? "var(--bg-hover)" : "inherit",
                      }}
                    >
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <span className="table-mono" style={{ fontWeight: 600, color: "var(--accent)" }}>
                            {rec.key}
                          </span>
                          <button
                            type="button"
                            className="copy-pill"
                            onClick={() => copyToClipboard(rec.key)}
                            title="Copy key"
                          >
                            {copiedKey === rec.key ? "✓" : <IconCopy size={12} />}
                          </button>
                        </div>
                        <div className="table-mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                          {rec.id.slice(0, 18)}...
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-open" style={{ fontSize: "0.7rem" }}>
                          {rec.memory_type}
                        </span>
                      </td>
                      <td style={{ maxWidth: "360px" }}>
                        <div
                          style={{
                            fontSize: "0.825rem",
                            color: "var(--text-primary)",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            lineHeight: 1.45,
                          }}
                        >
                          {rec.content}
                        </div>
                      </td>
                      <td>
                        {taskId && (
                          <Link
                            href={`/tasks`}
                            className="table-mono"
                            style={{ color: "var(--accent)", textDecoration: "none", fontSize: "0.775rem" }}
                          >
                            {taskId}
                          </Link>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-sm btn-secondary"
                          onClick={() => setSelectedRecord(rec)}
                        >
                          Inspect →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Selected Record Drawer */}
          {selectedRecord && (
            <div className="metric-card" style={{ height: "fit-content", position: "sticky", top: "80px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <IconMemory size={18} color="var(--accent)" />
                  <h3 style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Memory Payload
                  </h3>
                </div>
                <button
                  type="button"
                  className="btn btn-sm btn-secondary"
                  onClick={() => setSelectedRecord(null)}
                >
                  ✕
                </button>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", fontSize: "0.825rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Pattern Key:</span>
                  <span className="table-mono" style={{ color: "var(--accent)", fontWeight: 600 }}>{selectedRecord.key}</span>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Memory Type:</span>
                  <span className="badge badge-open">{selectedRecord.memory_type}</span>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Lesson Content:</span>
                  <div
                    style={{
                      background: "var(--bg-card)",
                      padding: "0.85rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      fontSize: "0.8rem",
                      lineHeight: 1.5,
                      color: "var(--text-primary)",
                    }}
                  >
                    {selectedRecord.content}
                  </div>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Metadata & Vector Embeddings:</span>
                  <pre
                    style={{
                      background: "var(--bg-base)",
                      padding: "0.75rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.725rem",
                      overflowX: "auto",
                      color: "#e2e8f0",
                    }}
                  >
                    {JSON.stringify(selectedRecord.metadata_json || {}, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
