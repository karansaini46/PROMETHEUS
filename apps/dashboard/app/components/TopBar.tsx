"use client";

import React, { useEffect, useState } from "react";
import { getHealth, isDemoMode, setDemoMode } from "../../lib/api";
import type { HealthResponse } from "@prometheus/shared-types";

export function TopBar() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demoActive, setDemoActive] = useState<boolean>(false);

  useEffect(() => {
    setDemoActive(isDemoMode());
    getHealth().then(setHealth).catch(() => {});

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

  return (
    <>
      {demoActive && (
        <div className="demo-banner" role="status">
          <span>
            ⚠️ <strong>DEMO MODE ACTIVE</strong>: Displaying realistic sample engineering evidence. Live backend metrics are bypassed.
          </span>
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={handleToggleDemo}
            aria-label="Switch back to live backend API"
          >
            Switch to Live API
          </button>
        </div>
      )}

      <header className="topbar">
        <div className="topbar-left">
          <div className="badge badge-pending" title="Current Subsystem">
            CONTROL PLANE v0.1.0
          </div>
        </div>

        <div className="topbar-right">
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={handleToggleDemo}
            title="Toggle between live backend API and sample demo mode"
          >
            {demoActive ? "✓ Demo Mode Active" : "Enable Demo Mode"}
          </button>

          <div
            className={`badge ${isHealthy ? "badge-resolved" : "badge-running"}`}
            title={`Database: ${health?.database || "probing"}, Sandbox: ${health?.sandbox_available ? "ready" : "standby"}`}
          >
            <span className="badge-dot" aria-hidden="true" />
            <span>
              {health?.status ? `SYSTEM: ${health.status.toUpperCase()}` : "CONNECTING..."}
            </span>
          </div>
        </div>
      </header>
    </>
  );
}
