"use client";

import React, { useMemo, useState } from "react";
import { IconCheck, IconCopy } from "./Icons";

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
  const [copied, setCopied] = useState(false);

  const lines = useMemo(() => (diff ? diff.split("\n") : []), [diff]);

  const stats = useMemo(() => {
    let adds = 0;
    let dels = 0;
    lines.forEach((l) => {
      if (l.startsWith("+") && !l.startsWith("+++")) adds++;
      if (l.startsWith("-") && !l.startsWith("---")) dels++;
    });
    return { adds, dels };
  }, [lines]);

  const handleToggleApproval = () => {
    const nextApproved = !approved;
    setApproved(nextApproved);
    onApprovalChange?.(nextApproved);
  };

  const handleCopyDiff = () => {
    navigator.clipboard.writeText(diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="diff-container" role="region" aria-label="Unified Diff Viewer">
      <div className="diff-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <span style={{ opacity: 0.7 }}>📄</span>
            <span className="table-mono" style={{ fontWeight: 600 }}>{filename || "Unified Patch Diff"}</span>
          </span>
          <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.8125rem", fontFamily: "var(--font-mono)" }}>
            <span style={{ color: "var(--success)", fontWeight: 700 }}>+{stats.adds}</span>
            <span style={{ color: "var(--danger)", fontWeight: 700 }}>-{stats.dels}</span>
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={handleCopyDiff}
            title="Copy raw unified diff"
          >
            {copied ? (
              <>
                <IconCheck size={14} color="var(--success)" />
                <span>Copied</span>
              </>
            ) : (
              <>
                <IconCopy size={14} />
                <span>Copy Diff</span>
              </>
            )}
          </button>

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
        {lines.length === 0 ? (
          <div style={{ padding: "1.5rem", color: "var(--text-muted)", textAlign: "center" }}>
            Empty diff payload
          </div>
        ) : (
          lines.map((line, idx) => {
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
                <span
                  style={{
                    display: "inline-block",
                    width: "38px",
                    userSelect: "none",
                    opacity: 0.45,
                    fontSize: "0.75rem",
                    textAlign: "right",
                    marginRight: "1rem",
                  }}
                >
                  {idx + 1}
                </span>
                <code>{line || " "}</code>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
