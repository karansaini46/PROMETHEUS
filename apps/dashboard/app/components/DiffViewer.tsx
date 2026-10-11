"use client";

import React, { useState } from "react";

interface DiffViewerProps {
  diff: string;
  filename?: string;
  initialApproved?: boolean;
  onApprovalChange?: (approved: boolean) => void;
}

export function DiffViewer({
  diff,
  filename,
  initialApproved = false,
  onApprovalChange,
}: DiffViewerProps) {
  const [approved, setApproved] = useState(initialApproved);

  const lines = diff.split("\n");

  const handleToggleApproval = () => {
    const nextApproved = !approved;
    setApproved(nextApproved);
    onApprovalChange?.(nextApproved);
  };

  return (
    <div className="diff-container" role="region" aria-label="Unified Diff Viewer">
      <div className="diff-header">
        <span>📄 {filename || "Unified Patch Diff"}</span>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          {onApprovalChange && (
            <button
              type="button"
              className={`btn btn-sm ${approved ? "btn-primary" : "btn-secondary"}`}
              onClick={handleToggleApproval}
              aria-pressed={approved}
            >
              {approved ? "✓ Patch Approved" : "Approve Patch"}
            </button>
          )}
        </div>
      </div>

      <div className="diff-body" tabIndex={0} aria-label="Diff contents">
        {lines.map((line, idx) => {
          let lineType = "context";
          if (line.startsWith("+") && !line.startsWith("+++")) {
            lineType = "add";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            lineType = "del";
          } else if (line.startsWith("@@") || line.startsWith("diff") || line.startsWith("index")) {
            lineType = "meta";
          }

          return (
            <div key={idx} className={`diff-line ${lineType}`}>
              <code>{line || " "}</code>
            </div>
          );
        })}
      </div>
    </div>
  );
}
