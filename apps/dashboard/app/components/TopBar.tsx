"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getHealth, isDemoMode, setDemoMode } from "../../lib/api";
import type { HealthResponse } from "@prometheus/shared-types";
import { IconCheck, IconRefresh } from "./Icons";

export function TopBar() {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demoActive, setDemoActive] = useState<boolean>(false);
  const [refreshing, setRefreshing] = useState(false);

  const fetchHealth = () => {
    setRefreshing(true);
    getHealth()
      .then(setHealth)
      .catch(() => {})
      .finally(() => setTimeout(() => setRefreshing(false), 500));
  };

  useEffect(() => {
    setDemoActive(isDemoMode());
    fetchHealth();

    const interval = setInterval(() => {
      getHealth().then(setHealth).catch(() => {});
    }, 15000);

    return () => clearInterval(interval);
  }, []);

  const handleToggleDemo = () => {
    const nextState = !demoActive;
    setDemoActive(nextState);
    setDemoMode(nextState);
    window.location.reload();
  };

  const isHealthy = health?.status === "healthy";

  const getBreadcrumbName = () => {
    if (pathname === "/") return "Overview";
    if (pathname.startsWith("/projects")) return "Projects";
    if (pathname.startsWith("/tasks")) return "Task Workspace";
    if (pathname.startsWith("/runs")) return "Execution Runs";
    if (pathname.startsWith("/patch-review")) return "Patch Review";
    if (pathname.startsWith("/models")) return "Model Registry";
    if (pathname.startsWith("/evaluations")) return "Evaluations";
    if (pathname.startsWith("/memory")) return "Memory Graph";
    if (pathname.startsWith("/settings")) return "Settings";
    return "Workbench";
  };

  return (
    <>
      {demoActive && (
        <div
          style={{
            padding: "0.4rem 1.5rem",
            backgroundColor: "#18181b",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "0.8125rem",
            color: "var(--text-secondary)",
          }}
          role="status"
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ color: "var(--warning-text)" }}>●</span>
            <span>
              <strong>Demo Mode</strong> — Mocked telemetry loaded for evaluation.
            </span>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={handleToggleDemo}
            style={{ padding: "0.2rem 0.55rem", fontSize: "0.75rem" }}
          >
            Switch to Live API
          </button>
        </div>
      )}

      <header className="topbar">
        <div className="topbar-left">
          <div className="topbar-breadcrumb">
            <span>PROMETHEUS</span>
            <span className="topbar-breadcrumb-sep">/</span>
            <strong>{getBreadcrumbName()}</strong>
          </div>
        </div>

        <div className="topbar-right">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.25rem 0.55rem",
              fontSize: "0.75rem",
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
              background: "rgba(255, 255, 255, 0.03)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "4px",
            }}
          >
            <span>branch:</span>
            <span style={{ color: "var(--text-primary)" }}>main</span>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.25rem 0.55rem",
              fontSize: "0.75rem",
              fontFamily: "var(--font-mono)",
              color: isHealthy ? "var(--success-text)" : "var(--warning-text)",
              background: isHealthy ? "var(--success-bg)" : "var(--warning-bg)",
              border: `1px solid ${isHealthy ? "var(--success-border)" : "var(--warning-border)"}`,
              borderRadius: "4px",
            }}
            title={isHealthy ? "All subsystems healthy" : "Subsystem degraded"}
          >
            <span className="badge-dot" />
            <span>{isHealthy ? "Operational" : "Degraded"}</span>
          </div>

          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={fetchHealth}
            title="Refresh system probe"
            disabled={refreshing}
          >
            <IconRefresh size={12} className={refreshing ? "spin-icon" : ""} />
          </button>

          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={handleToggleDemo}
            title="Toggle between live API and offline sample mode"
          >
            {demoActive ? (
              <span style={{ color: "var(--success-text)", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                <IconCheck size={11} /> Demo
              </span>
            ) : (
              "Demo"
            )}
          </button>

          <Link href="/tasks" className="btn btn-sm btn-primary">
            + New Task
          </Link>
        </div>
      </header>
    </>
  );
}
