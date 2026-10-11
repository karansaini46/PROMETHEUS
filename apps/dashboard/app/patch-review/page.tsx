"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getPatchReviews } from "../../lib/api";
import { DiffViewer } from "../components/DiffViewer";
import { EmptyState, ErrorState, LoadingState } from "../components/UIStates";
import type { PatchReviewItem } from "@prometheus/shared-types";

export default function PatchReviewPage() {
  const [patches, setPatches] = useState<PatchReviewItem[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Approval state overrides
  const [approvalStatus, setApprovalStatus] = useState<Record<string, "APPROVED" | "REJECTED" | "PENDING">>({});
  const [feedback, setFeedback] = useState<string>("");
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const loadPatches = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPatchReviews();
      setPatches(data);
      const initialStatus: Record<string, "APPROVED" | "REJECTED" | "PENDING"> = {};
      data.forEach((p) => {
        initialStatus[p.run_id] = p.approved ? "APPROVED" : "PENDING";
      });
      setApprovalStatus(initialStatus);
    } catch (err: any) {
      setError(err?.message || "Failed to load patch reviews.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPatches();
  }, []);

  const currentPatch = patches[selectedIdx] || null;

  const handleApprove = (runId: string) => {
    setApprovalStatus((prev) => ({ ...prev, [runId]: "APPROVED" }));
    setActionNotice(`Patch for ${runId} explicitly APPROVED for branch integration.`);
  };

  const handleReject = (runId: string) => {
    setApprovalStatus((prev) => ({ ...prev, [runId]: "REJECTED" }));
    setActionNotice(`Patch for ${runId} REJECTED. Review notes recorded.`);
  };

  const handleDownloadPatch = (patch: PatchReviewItem) => {
    const element = document.createElement("a");
    const file = new Blob([patch.patch_diff], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = `${patch.task_id}_patch_${patch.run_id}.diff`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  if (loading) return <LoadingState message="Fetching synthesized patch reviews..." />;
  if (error) return <ErrorState title="Failed to Load Patches" message={error} onRetry={loadPatches} />;

  if (patches.length === 0) {
    return (
      <div>
        <div className="page-header">
          <div>
            <h1 className="page-title">Patch Review</h1>
            <p className="page-description">
              Unified diffs, verification test reports, and explicit approval controls.
            </p>
          </div>
        </div>
        <EmptyState
          title="No candidate patches ready for review"
          description="Patches will appear here once autonomous execution runs verify an issue resolution."
          actionLabel="View Execution Runs"
          onAction={() => (window.location.href = "/runs")}
        />
      </div>
    );
  }

  const currentStatus = currentPatch ? approvalStatus[currentPatch.run_id] || "PENDING" : "PENDING";

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Patch Review & Verification</h1>
          <p className="page-description">
            Inspect autonomous git diffs, affected file changes, test verification outcomes, and approve integration.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadPatches}>
            ↻ Refresh Patches
          </button>
        </div>
      </div>

      {actionNotice && (
        <div
          className="state-box"
          style={{
            padding: "0.85rem 1.25rem",
            marginBottom: "1.5rem",
            borderColor: currentStatus === "APPROVED" ? "var(--success)" : "var(--danger)",
          }}
          role="status"
        >
          <p
            style={{
              color: currentStatus === "APPROVED" ? "var(--success)" : "var(--danger)",
              fontWeight: 600,
            }}
          >
            {actionNotice}
          </p>
        </div>
      )}

      {/* Patch Selector Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0.5rem",
          overflowX: "auto",
          marginBottom: "1.5rem",
          paddingBottom: "0.5rem",
        }}
        role="tablist"
        aria-label="Patches"
      >
        {patches.map((p, idx) => {
          const isSelected = idx === selectedIdx;
          const status = approvalStatus[p.run_id] || "PENDING";

          return (
            <button
              key={p.run_id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              className="btn"
              style={{
                backgroundColor: isSelected ? "var(--bg-elevated)" : "var(--bg-surface)",
                borderColor: isSelected ? "var(--accent)" : "var(--border-subtle)",
                color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                padding: "0.5rem 0.85rem",
                borderRadius: "6px",
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
                gap: "0.2rem",
                minWidth: "220px",
              }}
              onClick={() => setSelectedIdx(idx)}
            >
              <div style={{ display: "flex", width: "100%", justifyContent: "space-between", alignItems: "center" }}>
                <span className="table-mono" style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                  {p.task_id}
                </span>
                <span
                  className={`badge ${
                    status === "APPROVED"
                      ? "badge-resolved"
                      : status === "REJECTED"
                      ? "badge-failed"
                      : "badge-running"
                  }`}
                  style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem" }}
                >
                  {status}
                </span>
              </div>
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-secondary)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: "200px",
                }}
              >
                {p.task_title}
              </div>
            </button>
          );
        })}
      </div>

      {currentPatch && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "1.5rem", alignItems: "start" }}>
          {/* Main Diff Area */}
          <div>
            <div style={{ marginBottom: "1rem" }}>
              <DiffViewer
                diff={currentPatch.patch_diff}
                filename={currentPatch.affected_files.join(", ") || "patch.diff"}
              />
            </div>
          </div>

          {/* Verification & Approval Sidebar */}
          <div>
            {/* Metadata Card */}
            <div className="metric-card" style={{ marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-primary)" }}>
                Patch Audit Telemetry
              </h2>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.8rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Target Task: </span>
                  <Link href="/tasks" className="table-mono" style={{ color: "var(--accent)", textDecoration: "none" }}>
                    {currentPatch.task_id}
                  </Link>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)" }}>Execution Run: </span>
                  <Link href={`/runs/${currentPatch.run_id}`} className="table-mono" style={{ color: "var(--accent)", textDecoration: "none" }}>
                    {currentPatch.run_id}
                  </Link>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)" }}>Verification Test Status: </span>
                  <span
                    className={`badge ${
                      currentPatch.test_status === "PASSED" ? "badge-resolved" : "badge-failed"
                    }`}
                    style={{ fontSize: "0.7rem" }}
                  >
                    ✓ {currentPatch.test_status}
                  </span>
                </div>

                <div>
                  <span style={{ color: "var(--text-muted)" }}>Approval Status: </span>
                  <span
                    className={`badge ${
                      currentStatus === "APPROVED"
                        ? "badge-resolved"
                        : currentStatus === "REJECTED"
                        ? "badge-failed"
                        : "badge-running"
                    }`}
                    style={{ fontSize: "0.7rem" }}
                  >
                    {currentStatus}
                  </span>
                </div>
              </div>
            </div>

            {/* Affected Files */}
            <div className="metric-card" style={{ marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.5rem", color: "var(--text-primary)" }}>
                Affected Files ({currentPatch.affected_files.length})
              </h2>
              <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                {currentPatch.affected_files.map((file, idx) => (
                  <li key={idx} className="table-mono" style={{ fontSize: "0.775rem", color: "var(--text-secondary)" }}>
                    📄 {file}
                  </li>
                ))}
              </ul>
            </div>

            {/* Explicit Approval Controls */}
            <div className="metric-card">
              <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem", color: "var(--text-primary)" }}>
                Explicit Gatekeeper Controls
              </h2>
              <p style={{ fontSize: "0.775rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                Engineering sign-off required prior to committing changes into target repository.
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  style={{ width: "100%", justifyContent: "center" }}
                  onClick={() => handleApprove(currentPatch.run_id)}
                  disabled={currentStatus === "APPROVED"}
                >
                  {currentStatus === "APPROVED" ? "✓ Patch Approved" : "Approve & Permit Merge"}
                </button>

                <button
                  type="button"
                  className="btn btn-danger"
                  style={{ width: "100%", justifyContent: "center" }}
                  onClick={() => handleReject(currentPatch.run_id)}
                  disabled={currentStatus === "REJECTED"}
                >
                  {currentStatus === "REJECTED" ? "✕ Patch Rejected" : "Reject Patch"}
                </button>

                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ width: "100%", justifyContent: "center" }}
                  onClick={() => handleDownloadPatch(currentPatch)}
                >
                  ⇣ Export .patch File
                </button>
              </div>

              {/* Feedback text */}
              <div style={{ marginTop: "1rem" }}>
                <label htmlFor="patch-feedback" className="form-label">
                  Reviewer Notes / Feedback:
                </label>
                <textarea
                  id="patch-feedback"
                  className="form-textarea"
                  rows={2}
                  placeholder="Optional review observations..."
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
