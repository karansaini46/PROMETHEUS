"use client";

import React from "react";

interface PaginationProps {
  page: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (newPage: number) => void;
}

export function Pagination({
  page,
  totalPages,
  totalItems,
  onPageChange,
}: PaginationProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="pagination" role="navigation" aria-label="Pagination">
      <div>
        Showing page {page} of {totalPages} ({totalItems} total items)
      </div>
      <div className="pagination-controls">
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          ← Previous
        </button>
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          aria-label="Next page"
        >
          Next →
        </button>
      </div>
    </div>
  );
}

export function EmptyState({
  title = "No data found",
  description = "No items have been registered or recorded yet.",
  actionLabel,
  onAction,
}: {
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="state-box" role="status">
      <div className="state-icon" aria-hidden="true">∅</div>
      <h3 className="state-title">{title}</h3>
      <p className="state-desc">{description}</p>
      {actionLabel && onAction && (
        <button type="button" className="btn btn-primary" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}

export function LoadingState({
  message = "Loading engineering data...",
}: {
  message?: string;
}) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      <div className="state-icon" aria-hidden="true">⏳</div>
      <h3 className="state-title">{message}</h3>
      <p className="state-desc">Querying authoritative backend records...</p>
    </div>
  );
}

export function ErrorState({
  title = "Failed to load data",
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-box" role="alert">
      <div className="state-icon" style={{ color: "var(--danger)" }} aria-hidden="true">
        ⚠️
      </div>
      <h3 className="state-title">{title}</h3>
      <p className="state-desc">{message || "A network or server error occurred."}</p>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          ↻ Retry Request
        </button>
      )}
    </div>
  );
}
